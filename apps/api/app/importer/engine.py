"""The import itself (docs/IMPORT.md): old snapshot -> new database, in the caller's transaction.

`Importer.run` only flushes: the caller commits (`--apply`) or rolls back (`--dry-run`). Every
created row gets `legacy_ref`; a row found by it is left alone, so a second run adds nothing, and
rows without `legacy_ref` are never changed or deleted.
"""

import re
import uuid
from calendar import monthrange
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.cohorts.schedule import check_room_free, lesson_dates, local_dt
from app.cohorts.status import (
    ACTIVE,
    CANCELLED,
    COMPLETED,
    DONE,
    GRADUATE,
    RECRUITING,
    reevaluate,
    status_for,
    sync_status,
)
from app.cohorts.status import today as today_local
from app.core.errors import DomainError
from app.importer import parse as p
from app.importer.report import Recon, Report
from app.leads.hygiene import neutral
from app.metrics import enrollment_counts, student_counts
from app.metrics.money import cohort_periods, income_total
from app.metrics.reports import graduate_count
from app.models import (
    AppUser,
    Attendance,
    Branch,
    Campaign,
    Cohort,
    Course,
    Enrollment,
    Grade,
    InstructorPayout,
    Lead,
    Lesson,
    Payment,
    Role,
    Room,
    Student,
)

Row = dict[str, Any]
Snapshot = dict[str, list[Row]]

NS = uuid.UUID("0b1f4c7e-5a52-4c0e-9a55-3f4a0a6f1d11")
UNUSABLE_HASH = "!imported-no-password"  # not an argon2 hash: nobody can sign in until activation
CITIES = {"душанбе": "Душанбе", "истаравшан": "Истаравшан"}
WEEKDAYS = {"Пн": 1, "Вт": 2, "Ср": 3, "Чт": 4, "Пт": 5, "Сб": 6, "Вс": 7}
COHORT_STATUS = {"Набор": RECRUITING, "Активный": ACTIVE, "Завершён": DONE, "Отменён": CANCELLED}
STATUS_RANK = {"Отменён": 0, "Набор": 1, "Завершён": 2, "Активный": 3}
ENROLL_STATUS = {
    "Активный": "активный",
    "Ожидает": "активный",
    "Завершил": "завершил",
    "Отчислен": "отчислен",
}
ENROLL_RANK = {"выпускник": 3, "завершил": 2, "активный": 1, "отчислен": 0}
METHODS = {"alif": "alif", "payvand": "payvand", "наличные": "наличные"}
LEAD_STATUS = {
    "Новый": "новый",
    "Заинтересован": "заинтересован",
    "Отказ": "отказ",
    "Оплатил": "записан",
}
CALL_STATUS = {
    "Новый": "не звонили",
    "Не ответил": "не ответил",
    "Позвонили": "позвонили",
    "Отказ": "позвонили",
}
LEAD_SOURCE = {
    "Платный": "Facebook",
    "Instagram": "Instagram",
    "Telegram": "Telegram",
    "Рекомендация": "рекомендация",
    "Электронная почта": "другое",
}
CAMPAIGN_STATUS = {"Завершена": "завершена", "Активна": "активна"}
DEFAULT_CAPACITY = 20
PLACEHOLDER_ROOM_CAPACITY = 30
PLACEHOLDER_DAYS = [1, 3, 5]
PLACEHOLDER_TIMES = (time(9, 0), time(10, 30))
PASS_TOTAL = 70
BATCH = 1500


def add_months(start: date, months: int) -> date:
    index = start.year * 12 + start.month - 1 + months
    year, month = divmod(index, 12)
    return date(year, month + 1, min(start.day, monthrange(year, month + 1)[1]))


def noon(day: date) -> datetime:
    return datetime.combine(day, time(12, 0), tzinfo=p.TZ)


def first(rows: list[Row], key: str) -> str:
    for r in rows:
        if p.text(r.get(key)):
            return p.text(r.get(key))
    return ""


@dataclass
class Person:
    """One real student: old rows folded together by phone, or by name and city."""

    idx: int
    key: str
    rows: list[Row] = field(default_factory=list)
    name: str = ""
    phone: str | None = None
    ref: str = ""
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    branch: str = ""


@dataclass
class EnrollPlan:
    person: Person
    cohort_old: str
    rows: list[Row] = field(default_factory=list)
    status: str = "активный"
    manual: bool = False
    homework: int | None = None
    final: int | None = None
    old_total: Decimal | None = None
    enrolled_at: datetime | None = None
    ref: str = ""
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class InstrPerson:
    key: str
    name: str
    rows: list[Row]
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    branch: str = ""
    created: bool = False


@dataclass
class CohortCtx:
    old_id: str
    obj: Cohort
    branch: str
    created: bool
    status_old: str = ""


class Importer:
    def __init__(self, db: AsyncSession, snapshot: Snapshot, report: Report) -> None:
        self.db, self.snap, self.rep = db, snapshot, report
        self.today = today_local()
        self.branches: dict[str, uuid.UUID] = {}
        self.branch_names: dict[uuid.UUID, str] = {}
        self.refs: dict[str, dict[str, uuid.UUID]] = {}
        self.rooms: dict[tuple[uuid.UUID, str], uuid.UUID] = {}
        self.course_by_name: dict[str, uuid.UUID] = {}  # exact names already in the database
        self.logins: set[str] = set()
        self.phones: set[str] = set()
        self.course_lookup: dict[str, uuid.UUID] = {}  # normalised name / name + level -> course
        self.course_old: dict[str, uuid.UUID] = {}
        self.course_info: dict[uuid.UUID, tuple[Decimal, int]] = {}
        self.instr_by_key: dict[str, InstrPerson] = {}
        self.instr_by_id: dict[str, set[str]] = defaultdict(set)
        self.cohorts: dict[str, CohortCtx] = {}
        self.persons: list[Person] = []
        self.plans: dict[tuple[int, str], EnrollPlan] = {}
        self.lessons: dict[tuple[uuid.UUID, date], uuid.UUID] = {}
        self.placeholder_rooms: dict[str, uuid.UUID] = {}
        self.role_id: uuid.UUID | None = None
        self.created_cohorts: list[uuid.UUID] = []

    # ---- plumbing -------------------------------------------------------------------------

    def rows(self, sheet: str) -> list[Row]:
        rows = self.snap.get(sheet, [])
        self.rep.read[sheet] += len(rows)
        return rows

    async def _refs(self, model: Any) -> dict[str, uuid.UUID]:
        found = await self.db.execute(
            select(model.legacy_ref, model.id).where(model.legacy_ref.is_not(None))
        )
        return {ref: i for ref, i in found.all()}

    async def _load(self) -> None:
        for b in (await self.db.execute(select(Branch))).scalars():
            self.branches[b.name] = b.id
            self.branch_names[b.id] = b.name
        for model in (
            Room, Course, AppUser, Cohort, Lesson, Student, Enrollment, Payment, InstructorPayout,
            Campaign, Lead,
        ):  # fmt: skip
            self.refs[model.__tablename__] = await self._refs(model)
        for r in (await self.db.execute(select(Room))).scalars():
            self.rooms[(r.branch_id, r.name)] = r.id
        for c in (await self.db.execute(select(Course))).scalars():
            self.course_by_name[c.name] = c.id
            self.course_info[c.id] = (c.default_price_month, c.duration_months)
        for login, phone in (await self.db.execute(select(AppUser.login, AppUser.phone))).all():
            self.logins.add(str(login).lower())
            if phone:
                self.phones.add(phone)
        self.role_id = (
            await self.db.execute(select(Role.id).where(Role.code == "instructor"))
        ).scalar_one()

    def branch_of(self, city: str) -> str | None:
        return CITIES.get(p.norm_name(city))

    def _is_new(self, table: str, ref: str) -> bool:
        return ref not in self.refs[table]

    # ---- run ------------------------------------------------------------------------------

    async def run(self) -> None:
        await self._load()
        await self._courses()
        await self._instructors()
        await self._cohorts()
        await self._lessons_index()
        await self._students_and_enrollments()
        await self._grades()
        await self._payments()
        await self._attendance()
        await self._marketing()
        await self._leads()
        await self._payouts()
        await self._close_cohorts()
        await self._reconcile()

    # ---- COURSES --------------------------------------------------------------------------

    async def _courses(self) -> None:
        rep = self.rep
        groups: dict[str, list[Row]] = defaultdict(list)
        for r in self.rows("COURSES"):
            name, _ = p.name_of(r.get("course_name"))
            if not p.text(r.get("course_name")) or not p.text(r.get("course_id")):
                rep.drop("COURSES", "нет названия или ID", p.text(r.get("course_id")))
                continue
            groups[p.norm_name(name)].append(r)
        for norm, rows in groups.items():
            rep.merged["COURSES"] += len(rows) - 1
            head = rows[0]
            name = p.name_of(head.get("course_name"))[0]
            old_id = p.text(head.get("course_id"))
            ref = p.make_ref("COURSES", old_id)
            price = next(
                (d for r in rows if (d := p.to_decimal(r.get("price_per_month"))) is not None),
                None,
            )
            months = next(
                (n for r in rows if (n := p.to_int(r.get("duration_months"))) is not None), None
            )
            if price is None or price < 0:
                rep.flag("COURSES", "цена не указана, поставлена 0", old_id, course=name)
                price = Decimal(0)
            if months is None or not 1 <= months <= 36:
                rep.flag(
                    "COURSES", "длительность не указана, поставлено 3 мес.", old_id, course=name
                )
                months = 3
            fmt = "online" if "онлайн" in p.text(head.get("format")).lower() else "offline"
            if ref in self.refs["course"]:
                cid = self.refs["course"][ref]
                rep.existing["COURSES"] += 1
            elif name in self.course_by_name:
                cid = self.course_by_name[name]
                rep.existing["COURSES"] += 1
                rep.note("курс с таким названием уже был в базе, использован он")
            else:
                cid = uuid.uuid4()
                self.db.add(
                    Course(
                        id=cid,
                        name=name,
                        direction=None,
                        default_price_month=price,
                        duration_months=months,
                        format=fmt,
                        legacy_ref=ref,
                    )  # fmt: skip
                )
                self.refs["course"][ref] = cid
                self.course_by_name[name] = cid
                self.course_info[cid] = (price, months)
                rep.imported["COURSES"] += 1
            for r in rows:
                self.course_old[p.text(r.get("course_id"))] = cid
                level = p.text(r.get("level"))
                self.course_lookup[norm] = self.course_lookup.get(norm, cid)
                self.course_lookup[p.norm_name(f"{name} {level}")] = cid
                if p.text(r.get("city")) == "Оба":
                    rep.note("курс для обоих городов (курсы общие)")
        await self.db.flush()

    def course_for_text(self, text: str) -> uuid.UUID | None:
        """A course by the cohort's `course_name` prefix (before « (Mon)»)."""
        prefix = re.sub(r"\s*\([^)]*\).*$", "", text)
        return self.course_lookup.get(p.norm_name(prefix))

    # ---- INSTRUCTORS ----------------------------------------------------------------------

    def _login_for(self, name: str) -> str:
        base = p.slug(name) or "instructor"
        if len(base) < 3:
            base = f"instructor.{base}"
        login, n = base, 1
        while login.lower() in self.logins:
            n += 1
            login = f"{base}{n}"
        self.logins.add(login.lower())
        return login

    async def _instructors(self) -> None:
        rep = self.rep
        groups: dict[str, list[Row]] = defaultdict(list)
        for r in self.rows("INSTRUCTORS"):
            if not p.text(r.get("full_name")):
                rep.drop("INSTRUCTORS", "нет ФИО", p.text(r.get("instructor_id")))
            elif p.text(r.get("status")) == "Удалён":
                rep.drop("INSTRUCTORS", "статус Удалён", p.text(r.get("instructor_id")))
            else:
                groups[p.translit_key(r.get("full_name"))].append(r)
        for key, rows in groups.items():
            rep.merged["INSTRUCTORS"] += len(rows) - 1
            old_id = p.text(rows[0].get("instructor_id"))
            name, bad_name = p.name_of(rows[0].get("full_name"))
            ref = p.make_ref("INSTRUCTORS", old_id, key)
            person = InstrPerson(key, name, rows)
            city = first(rows, "city")
            person.branch = self.branch_of(city) or ""
            if bad_name:
                rep.flag("INSTRUCTORS", "ФИО с лишними символами, очищено", old_id, name=name)
            if ref in self.refs["app_user"]:
                person.id = self.refs["app_user"][ref]
                rep.existing["INSTRUCTORS"] += 1
            else:
                rate = Decimal(0)
                for r in rows:
                    value = p.to_decimal(r.get("salary_per_month"))
                    if value is not None and value > 1:
                        rate = value
                        break
                    if value is not None:
                        rep.flag(
                            "INSTRUCTORS",
                            "ставка 1 — не настоящая, поставлена 0",
                            old_id,
                            name=name,
                        )
                phone, raw = p.phone_of(first(rows, "phone"))
                if raw and phone is None:
                    rep.flag("INSTRUCTORS", "телефон не распознан", old_id, name=name, phone=raw)
                if phone and phone in self.phones:
                    rep.flag(
                        "INSTRUCTORS", "телефон уже занят, не записан", old_id, name=name, phone=raw
                    )
                    phone = None
                if phone:
                    self.phones.add(phone)
                if not city or not person.branch:
                    rep.flag("INSTRUCTORS", "город не указан", old_id, name=name)
                email = neutral(first(rows, "email"))
                self.db.add(
                    AppUser(
                        id=person.id,
                        login=self._login_for(name),
                        full_name=name,
                        phone=phone,
                        email=email,
                        branch_id=self.branches.get(person.branch),
                        role_id=self.role_id,
                        is_active=False,
                        password_hash=UNUSABLE_HASH,
                        must_change_password=True,
                        default_rate=rate,
                        legacy_ref=ref,
                    )  # fmt: skip
                )
                self.refs["app_user"][ref] = person.id
                person.created = True
                rep.imported["INSTRUCTORS"] += 1
            self.instr_by_key[key] = person
            for r in rows:
                self.instr_by_id[p.text(r.get("instructor_id"))].add(key)
        await self.db.flush()

    def instructor_of(self, old_id: str, name: str) -> InstrPerson | None:
        key = p.translit_key(name) if name else ""
        if key in self.instr_by_key:
            return self.instr_by_key[key]
        keys = self.instr_by_id.get(old_id, set())
        if len(keys) == 1:
            return self.instr_by_key[next(iter(keys))]
        return None

    # ---- COHORTS + lessons ----------------------------------------------------------------

    async def _room(self, branch_id: uuid.UUID, name: str) -> uuid.UUID:
        key = (branch_id, name)
        if key not in self.rooms:
            rid = uuid.uuid4()
            ref = p.make_ref("ROOMS", name, self.branch_names[branch_id])
            self.db.add(
                Room(
                    id=rid,
                    branch_id=branch_id,
                    name=name,
                    capacity=DEFAULT_CAPACITY,
                    legacy_ref=ref,
                )
            )
            self.rooms[key] = rid
            self.refs["room"][ref] = rid
            self.rep.note("аудитория создана из названия в листе (вместимость 20 — уточнить)")
            await self.db.flush()
        return self.rooms[key]

    async def _placeholder_room(self, branch_id: uuid.UUID, old_id: str) -> uuid.UUID:
        """The cohort has no (free) room: its own stand-in, so the lessons stay valid (#7)."""
        if old_id not in self.placeholder_rooms:
            rid = uuid.uuid4()
            name = f"Без аудитории ({old_id})"
            self.db.add(
                Room(
                    id=rid,
                    branch_id=branch_id,
                    name=name,
                    capacity=PLACEHOLDER_ROOM_CAPACITY,
                    legacy_ref=p.make_ref("ROOMS", name, self.branch_names[branch_id]),
                )  # fmt: skip
            )
            self.placeholder_rooms[old_id] = rid
            self.rooms[(branch_id, name)] = rid
            await self.db.flush()
        return self.placeholder_rooms[old_id]

    @staticmethod
    def _room_name(raw: str) -> str:
        name = re.sub(r"\s+", " ", raw).strip()
        return re.sub(r"(?i)^istaravshan", "Истаравшан", name)

    async def _cohorts(self) -> None:
        rep = self.rep
        groups: dict[str, list[Row]] = defaultdict(list)
        for r in self.rows("COHORTS"):
            cid = p.text(r.get("cohort_id"))
            if not cid:
                rep.drop("COHORTS", "нет ID", "")
            elif p.text(r.get("status")) == "Удалён":
                rep.drop("COHORTS", "статус Удалён", cid)
            else:
                groups[cid].append(r)
        for old_id, rows in groups.items():
            rep.merged["COHORTS"] += len(rows) - 1
            rows = sorted(rows, key=lambda r: -STATUS_RANK.get(p.text(r.get("status")), 0))
            await self._cohort(old_id, rows)
        await self.db.flush()

    async def _cohort(self, old_id: str, rows: list[Row]) -> None:
        rep = self.rep
        ref = p.make_ref("COHORTS", old_id)
        status_old = first(rows, "status")
        if ref in self.refs["cohort"]:
            obj = (
                await self.db.execute(select(Cohort).where(Cohort.id == self.refs["cohort"][ref]))
            ).scalar_one()
            self.cohorts[old_id] = CohortCtx(
                old_id, obj, self.branch_names[obj.branch_id], False, status_old
            )
            rep.existing["COHORTS"] += 1
            return
        # course
        course_text = first(rows, "course_name")
        course_id = self.course_old.get(first(rows, "course_id"))
        if course_id is None:
            course_id = self.course_for_text(course_text)
        cost = p.to_decimal(first(rows, "cost"))
        if course_id is None:
            if not course_text:
                rep.drop("COHORTS", "курс не определить", old_id)
                return
            course_id = await self._new_course_from_cohort(old_id, course_text, rows, cost)
        price_default, months = self.course_info[course_id]
        # dates
        start = p.parse_date(first(rows, "start_date"))
        if start is None:
            rep.drop("COHORTS", "нет даты начала", old_id)
            rep.flag("COHORTS", "поток не перенесён: нет даты начала", old_id, course=course_text)
            return
        end = p.parse_date(first(rows, "end_date"))
        if end is None or end <= start:
            end = add_months(start, months) - timedelta(days=1)
            rep.flag("COHORTS", "дата окончания не указана, по длительности курса", old_id)
        if end > p.MAX_DATE:
            rep.drop("COHORTS", "дата окончания вне 2020–2035", old_id)
            return
        # instructor and branch
        instr = self.instructor_of(first(rows, "instructor_id"), first(rows, "instructor_name"))
        if instr is None and (first(rows, "instructor_id") or first(rows, "instructor_name")):
            rep.flag("COHORTS", "инструктор не найден в листе INSTRUCTORS", old_id)
        city, room_raw = first(rows, "city"), self._room_name(first(rows, "room"))
        branch = self.branch_of(city)
        if branch is None and room_raw.startswith("Истаравшан"):
            branch = "Истаравшан"
        if branch is None and instr and instr.branch:
            branch = instr.branch
        if branch is None:
            branch = "Душанбе"
            rep.flag("COHORTS", "город не указан, поставлен Душанбе", old_id)
        branch_id = self.branches[branch]
        # room
        if not room_raw:
            room_id = await self._placeholder_room(branch_id, old_id)
            rep.flag("COHORTS", "аудитория не указана", old_id)
        elif room_raw == "Работа":
            room_id = await self._placeholder_room(branch_id, old_id)
            rep.flag("COHORTS", "аудитория «Работа» — не аудитория", old_id)
        else:
            room_id = await self._room(branch_id, room_raw)
        # schedule
        days = [
            WEEKDAYS[w]
            for w in first(rows, "schedule").replace(" ", "").split("/")
            if w in WEEKDAYS
        ]
        t_start, t_end = (
            p.parse_clock(first(rows, "start_time")),
            p.parse_clock(first(rows, "end_time")),
        )
        has_schedule = bool(days) and p.lesson_window_ok(t_start, t_end)
        if has_schedule:
            assert t_start is not None and t_end is not None  # noqa: S101
        else:
            reason = "время уроков вне 07:00–22:00 или длительность не 30–240 мин (#6)"
            if not days:
                reason = "расписание (дни) не указано"
            elif t_start is None or t_end is None:
                reason = "время уроков не разобрать (дата 1899 / пусто)"
            rep.flag(
                "COHORTS", f"{reason}: поток без расписания, подставлено Пн/Ср/Пт 09:00–10:30",
                old_id,
            )  # fmt: skip
            days, (t_start, t_end) = days or PLACEHOLDER_DAYS, PLACEHOLDER_TIMES
        assert t_start is not None and t_end is not None  # noqa: S101
        capacity = p.to_int(first(rows, "max_students"))
        if capacity is None or not 1 <= capacity <= 100:
            capacity = DEFAULT_CAPACITY
        price = cost if cost is not None and cost >= 0 else price_default
        status = CANCELLED if status_old == "Отменён" else status_for(start, end, self.today)
        obj = Cohort(
            id=uuid.uuid4(), course_id=course_id, branch_id=branch_id,
            instructor_id=instr.id if instr else None, room_id=room_id, start_date=start,
            end_date=end, weekdays=days, start_time=t_start, end_time=t_end, capacity=capacity,
            price_month=price, status=status, legacy_ref=ref,
            instructor_rate=(
                (await self.db.execute(select(AppUser.default_rate).where(AppUser.id == instr.id)))
                .scalar_one()
                if instr
                else Decimal(0)
            ),
        )  # fmt: skip
        self.db.add(obj)
        await self.db.flush()
        self.refs["cohort"][ref] = obj.id
        self.created_cohorts.append(obj.id)
        rep.imported["COHORTS"] += 1
        self.cohorts[old_id] = CohortCtx(old_id, obj, branch, True, status_old)
        if has_schedule:
            await self._generate_lessons(self.cohorts[old_id])
        else:
            rep.note("поток без расписания: уроки не созданы")
        if p.text(rows[0].get("status")) == "Отменён" or status_old == "Отменён":
            rep.note("поток отменён (статус сохранён)")

    async def _new_course_from_cohort(
        self, old_id: str, course_text: str, rows: list[Row], cost: Decimal | None
    ) -> uuid.UUID:
        name = p.name_of(course_text)[0]
        norm = p.norm_name(name)
        if norm in self.course_lookup:
            return self.course_lookup[norm]
        if name in self.course_by_name:
            cid = self.course_by_name[name]
        else:
            m = re.search(r"(\d+)\s*(мес|недел)", first(rows, "duration"))
            months = 3
            if m:
                months = int(m.group(1)) if m.group(2) == "мес" else -(-int(m.group(1)) // 4)
            months = min(36, max(1, months))
            price = cost if cost is not None and cost > 0 else Decimal(0)
            cid = uuid.uuid4()
            self.db.add(
                Course(
                    id=cid,
                    name=name,
                    default_price_month=price,
                    duration_months=months,
                    format="offline",
                    legacy_ref=p.make_ref("COHORTS-COURSE", norm),
                )  # fmt: skip
            )
            self.course_by_name[name] = cid
            self.course_info[cid] = (price, months)
            await self.db.flush()
            self.rep.note(
                "курс создан из названия потока (его нет в COURSES) — проверить цену и длительность"
            )
        self.course_lookup[norm] = cid
        self.rep.flag(
            "COHORTS", "курс создан из названия потока (нет в COURSES)", old_id, course=name
        )
        return cid

    async def _generate_lessons(self, ctx: CohortCtx) -> None:
        cohort = ctx.obj
        days = lesson_dates(cohort.start_date, cohort.end_date, cohort.weekdays)
        windows = [(local_dt(d, cohort.start_time), local_dt(d, cohort.end_time)) for d in days]
        room_id = cohort.room_id
        try:
            await check_room_free(self.db, room_id, windows)
        except DomainError as busy:
            room_id = await self._placeholder_room(cohort.branch_id, ctx.old_id)
            cohort.room_id = room_id
            await self.db.flush()
            self.rep.flag(
                "COHORTS", "аудитория занята другим потоком (#7): поставлена «Без аудитории»",
                ctx.old_id, room=str(busy.params.get("cohort", "")),
            )  # fmt: skip
        lessons = [
            Lesson(
                id=uuid.uuid4(),
                cohort_id=cohort.id,
                room_id=room_id,
                lesson_date=day,
                starts_at=s,
                ends_at=e,
                source="generated",
                legacy_ref=p.make_ref("LESSONS", ctx.old_id, day.isoformat()),
            )  # fmt: skip
            for day, (s, e) in zip(days, windows, strict=True)
        ]
        self.db.add_all(lessons)
        await self.db.flush()
        self.rep.note("урок создан из расписания потока", len(lessons))

    async def _lessons_index(self) -> None:
        ids = [c.obj.id for c in self.cohorts.values()]
        if not ids:
            return
        found = await self.db.execute(
            select(Lesson.id, Lesson.cohort_id, Lesson.lesson_date).where(Lesson.cohort_id.in_(ids))
        )
        for lid, cid, day in found.all():
            self.lessons[(cid, day)] = lid

    # ---- STUDENTS + ENROLLMENTS -----------------------------------------------------------

    def _build_persons(self) -> dict[str, Person]:
        rep = self.rep
        by_key: dict[str, Person] = {}
        for r in self.rows("STUDENTS"):
            sid = p.text(r.get("student_id"))
            if not p.text(r.get("full_name")):
                rep.drop("STUDENTS", "нет ФИО", sid)
                continue
            nm = p.norm_name(r.get("full_name"))
            ph = p.phone9(r.get("phone"))
            city = self.branch_of(p.text(r.get("city"))) or ""
            key = f"p:{ph}" if ph else f"n:{nm}|{city}"
            person = by_key.get(key)
            if person is None:
                person = by_key[key] = Person(len(by_key), key)
            person.rows.append(r)
        for person in by_key.values():
            rows = person.rows
            rep.merged["STUDENTS"] += len(rows) - 1
            person.name = p.name_of(rows[0].get("full_name"))[0]
            old_id = p.text(rows[0].get("student_id"))
            person.ref = p.make_ref("STUDENTS", old_id or "—", person.key)
            ids = {p.text(r.get("student_id")) for r in rows}
            if person.key.startswith("n:") and len(rows) > 1 and len(ids) > 1:
                rep.flag(
                    "STUDENTS", "проверить слияние: то же ФИО без телефона, разные ID", old_id,
                    name=person.name, ids=", ".join(sorted(ids)),
                )  # fmt: skip
            if person.key.startswith("p:"):
                toks = [set(p.norm_name(r.get("full_name")).split()) for r in rows]
                if len(rows) > 1 and not set.intersection(*toks):
                    rep.flag(
                        "STUDENTS", "проверить слияние: один телефон, совсем разные ФИО", old_id,
                        names=" / ".join(sorted({p.name_of(r.get("full_name"))[0] for r in rows})),
                    )  # fmt: skip
        return by_key

    def _index_persons(self, persons: list[Person]) -> None:
        self.by_pair: dict[tuple[str, str], Person] = {}
        self.by_name: dict[str, list[Person]] = defaultdict(list)
        self.by_sid: dict[str, list[Person]] = defaultdict(list)
        for person in persons:
            for r in person.rows:
                sid, nm = p.text(r.get("student_id")), p.norm_name(r.get("full_name"))
                self.by_pair.setdefault((sid, nm), person)
                if person not in self.by_name[nm]:
                    self.by_name[nm].append(person)
                if sid and person not in self.by_sid[sid]:
                    self.by_sid[sid].append(person)

    def person_of(self, sid: str, name: str) -> Person | None:
        """Old student ids repeat for different people: the id plus the name decide (#14)."""
        nm = p.norm_name(name)
        if (sid, nm) in self.by_pair:
            return self.by_pair[(sid, nm)]
        if len(self.by_name.get(nm, [])) == 1:
            return self.by_name[nm][0]
        if len(self.by_sid.get(sid, [])) == 1:
            return self.by_sid[sid][0]
        return None

    async def _students_and_enrollments(self) -> None:
        rep = self.rep
        persons = list(self._build_persons().values())
        self.persons = persons
        self._index_persons(persons)
        # enrollment plans
        groups: dict[tuple[int, str], EnrollPlan] = {}
        self.enr_drops: Counter[str] = Counter()
        self.enr_active_rows = 0
        for r in self.rows("ENROLLMENTS"):
            eid = p.text(r.get("enrollment_id"))
            is_active = p.text(r.get("status")) == "Активный"
            self.enr_active_rows += is_active
            if not eid or not p.text(r.get("student_id")) or not p.text(r.get("cohort_id")):
                rep.drop("ENROLLMENTS", "пустой ID", eid)
                self.enr_drops["пустой ID"] += is_active
                continue
            person = self.person_of(p.text(r.get("student_id")), p.text(r.get("student_name")))
            if person is None:
                rep.drop("ENROLLMENTS", "студент не найден в STUDENTS", eid)
                self.enr_drops["студент не найден в STUDENTS"] += is_active
                rep.flag(
                    "ENROLLMENTS",
                    "студент не найден в STUDENTS",
                    eid,
                    name=p.text(r.get("student_name")),
                )
                continue
            cohort_old = p.text(r.get("cohort_id"))
            if cohort_old not in self.cohorts:
                rep.drop("ENROLLMENTS", "поток удалён или не перенесён", eid)
                self.enr_drops["поток удалён или не перенесён"] += is_active
                continue
            key = (person.idx, cohort_old)
            plan = groups.get(key)
            if plan is None:
                plan = groups[key] = EnrollPlan(person, cohort_old)
            plan.rows.append(r)
        for plan in groups.values():
            self._finish_plan(plan)
        self.plans = groups
        # students: branch from the city, else from a cohort they study in
        for person in persons:
            city = self.branch_of(first(person.rows, "city"))
            if city is None:
                for (pidx, cohort_old), _ in groups.items():
                    if pidx == person.idx:
                        city = self.cohorts[cohort_old].branch
                        break
            if city is None:
                city = "Душанбе"
                rep.flag(
                    "STUDENTS",
                    "город не указан, поставлен Душанбе",
                    first(person.rows, "student_id"),
                    name=person.name,
                )
            person.branch = city
            if person.ref in self.refs["student"]:
                person.id = self.refs["student"][person.ref]
                rep.existing["STUDENTS"] += 1
                continue
            phone, raw = p.phone_of(first(person.rows, "phone"))
            old_id = first(person.rows, "student_id")
            if not raw:
                rep.flag("STUDENTS", "заполнить телефон", old_id, name=person.name)
            elif phone is None:
                rep.flag("STUDENTS", "телефон не распознан", old_id, name=person.name, phone=raw)
            if p.name_of(person.rows[0].get("full_name"))[1]:
                rep.flag("STUDENTS", "ФИО с лишними символами, очищено", old_id, name=person.name)
            person.phone = phone
            gender = {"муж": "male", "жен": "female"}.get(first(person.rows, "gender"))
            created = [d for r in person.rows if (d := p.parse_dt(r.get("registration_date")))]
            self.db.add(
                Student(
                    id=person.id,
                    full_name=person.name,
                    gender=gender,
                    phone=phone,
                    branch_id=self.branches[person.branch],
                    created_at=min(created) if created else datetime.now(UTC),
                    legacy_ref=person.ref,
                )  # fmt: skip
            )
            self.refs["student"][person.ref] = person.id
            rep.imported["STUDENTS"] += 1
        await self.db.flush()
        for plan in groups.values():
            cohort = self.cohorts[plan.cohort_old].obj
            if plan.ref in self.refs["enrollment"]:
                plan.id = self.refs["enrollment"][plan.ref]
                rep.existing["ENROLLMENTS"] += 1
                continue
            when = plan.enrolled_at or noon(cohort.start_date)
            self.db.add(
                Enrollment(
                    id=plan.id,
                    cohort_id=cohort.id,
                    student_id=plan.person.id,
                    status=plan.status,
                    enrolled_at=when,
                    status_manual=plan.manual,
                    legacy_ref=plan.ref,
                )  # fmt: skip
            )
            self.refs["enrollment"][plan.ref] = plan.id
            rep.imported["ENROLLMENTS"] += 1
        await self.db.flush()

    def _finish_plan(self, plan: EnrollPlan) -> None:
        rep = self.rep
        rows = plan.rows
        rep.merged["ENROLLMENTS"] += len(rows) - 1
        statuses = [ENROLL_STATUS.get(p.text(r.get("status")), "") for r in rows]
        statuses = [s for s in statuses if s]
        plan.status = max(statuses, key=lambda s: ENROLL_RANK[s]) if statuses else "активный"
        dates = [d for r in rows if (d := p.parse_dt(r.get("enrollment_date")))]
        plan.enrolled_at = min(dates) if dates else None
        old_id = p.text(rows[0].get("enrollment_id"))
        plan.ref = p.make_ref("ENROLLMENTS", old_id, plan.person.ref, plan.cohort_old)
        # grades: the last row that has any
        for r in reversed(rows):
            score = next(
                (
                    s
                    for k in ("certificate_issued", "employed_3m", "")
                    if (s := p.parse_score(r.get(k))) is not None
                ),
                None,
            )
            if score is not None:
                _, hw, fin = score
                if hw > p.OLD_HOMEWORK_MAX or fin > p.OLD_FINAL_MAX:
                    rep.flag("ENROLLMENTS", "оценки score: выше шкалы, обрезаны", old_id)
                plan.homework = p.rescale(min(hw, p.OLD_HOMEWORK_MAX), p.OLD_HOMEWORK_MAX)
                plan.final = p.rescale(min(fin, p.OLD_FINAL_MAX), p.OLD_FINAL_MAX)
                rep.note("оценки Д/З и финал пересчитаны из строки score: на шкалу 0–40")
                break
        for r in reversed(rows):
            total = p.to_decimal(r.get("final_score"))
            if total is not None:
                plan.old_total = total
                break
        if plan.old_total is not None and plan.homework is None:
            rep.note("зачисление только с итоговым баллом (Д/З и финал пусты)")
        # a finished cohort: the old total decides the graduate (>= 70), as the new rule does
        ctx = self.cohorts[plan.cohort_old]
        if (
            plan.old_total is not None
            and plan.old_total >= PASS_TOTAL
            and plan.homework is None
            and plan.status in ("активный", "завершил")
            and ctx.obj.status == DONE
        ):
            plan.status, plan.manual = GRADUATE, True
            rep.note("выпускник по итоговому баллу ≥ 70 из старой системы (статус зафиксирован)")

    # ---- GRADES ---------------------------------------------------------------------------

    def plan_of(self, sid: str, name: str, cohort_old: str) -> EnrollPlan | None:
        person = self.person_of(sid, name)
        return self.plans.get((person.idx, cohort_old)) if person else None

    async def _grades(self) -> None:
        rep = self.rep
        extra: dict[uuid.UUID, EnrollPlan] = {}
        for r in self.rows("GRADES"):
            gid = p.text(r.get("grade_id"))
            plan = self.plan_of(
                p.text(r.get("student_id")),
                p.text(r.get("student_name")),
                p.text(r.get("cohort_id")),
            )
            score = p.to_int(r.get("score"))
            if plan is None or score is None:
                rep.drop("GRADES", "зачисление не найдено или нет оценки", gid)
                rep.flag(
                    "GRADES",
                    "оценка не привязана к зачислению",
                    gid,
                    name=p.text(r.get("student_name")),
                )
                continue
            kind = p.text(r.get("assessment_type"))
            default_max = p.OLD_FINAL_MAX if kind == "final_work" else p.OLD_HOMEWORK_MAX
            top = p.to_int(r.get("max_score")) or default_max
            value = p.rescale(min(score, top), top)
            if kind == "homework":
                plan.homework = value if plan.homework is None else plan.homework
            elif kind == "final_work":
                plan.final = value if plan.final is None else plan.final
            else:
                rep.drop("GRADES", "неизвестный тип оценки", gid)
                continue
            extra[plan.id] = plan
            rep.imported["GRADES"] += 1
        existing = set((await self.db.execute(select(Grade.enrollment_id))).scalars())
        rows = [
            {"enrollment_id": plan.id, "homework": plan.homework, "final": plan.final}
            for plan in self.plans.values()
            if (plan.homework is not None or plan.final is not None) and plan.id not in existing
        ]
        for i in range(0, len(rows), BATCH):
            await self.db.execute(
                pg_insert(Grade).values(rows[i : i + BATCH]).on_conflict_do_nothing()
            )
        rep.note("строк grade записано", len(rows))

    # ---- PAYMENTS -------------------------------------------------------------------------

    def _ledger(self, kind: str, label: str, confirmed: bool, amount: Decimal | None) -> None:
        """Counts and confirmed money per outcome: the sheet total must balance to the dirham."""
        line = self.pay_ledger[kind].setdefault(label, [0, Decimal(0)])
        line[0] += 1
        if confirmed and amount:
            line[1] += amount

    async def _restore_enrollment(
        self, person: Person, cohort_old: str, pid: str, name: str, amount: str
    ) -> EnrollPlan:
        """A payment whose student and cohort both exist but which has no enrollment: the money
        is real, so the enrollment is made from it (and flagged)."""
        ctx = self.cohorts[cohort_old]
        plan = EnrollPlan(person, cohort_old)
        plan.status = "завершил" if ctx.obj.status == DONE else "активный"
        plan.manual = True
        plan.ref = p.make_ref("ENROLLMENTS", "from-payment", person.ref, cohort_old)
        if plan.ref in self.refs["enrollment"]:
            plan.id = self.refs["enrollment"][plan.ref]
            self.rep.existing["ENROLLMENTS"] += 1
        else:
            self.db.add(
                Enrollment(
                    id=plan.id,
                    cohort_id=ctx.obj.id,
                    student_id=person.id,
                    status=plan.status,
                    enrolled_at=noon(ctx.obj.start_date),
                    status_manual=True,
                    legacy_ref=plan.ref,
                )
            )
            self.refs["enrollment"][plan.ref] = plan.id
            self.rep.imported["ENROLLMENTS"] += 1
            self.rep.note("зачисление восстановлено из оплаты")
            self.rep.flag(
                "PAYMENTS", "зачисление восстановлено из оплаты", pid, name=name, amount=amount
            )
            await self.db.flush()
        self.plans[(person.idx, cohort_old)] = plan
        return plan

    async def _payments(self) -> None:
        rep = self.rep
        self.pay_ledger: dict[str, dict[str, list[Any]]] = {"drop": {}, "merge": {}, "in": {}}
        self.pay_rows, self.pay_total = 0, Decimal(0)
        seen: set[tuple[Any, ...]] = set()
        batch: list[Payment] = []
        for r in self.rows("PAYMENTS"):
            pid = p.text(r.get("payment_id"))
            sid, name, cohort_old = (
                p.text(r.get("student_id")),
                p.text(r.get("student_name")),
                p.text(r.get("cohort_id")),
            )
            amount = p.to_decimal(r.get("amount"))
            paid = p.parse_date(r.get("payment_date"))
            method = METHODS.get(p.text(r.get("payment_method")).lower())
            verified = p.text(r.get("verified")) == "Да"
            self.pay_rows += 1
            if verified and amount:
                self.pay_total += amount

            def drop(
                reason: str,
                flag: str,
                pid: str = pid,
                r: Row = r,
                amount: Decimal | None = amount,
                verified: bool = verified,
            ) -> None:
                rep.drop("PAYMENTS", reason, pid)
                self._ledger("drop", reason, verified, amount)
                rep.flag(
                    "PAYMENTS", flag, pid, name=p.text(r.get("student_name")),
                    amount=p.text(r.get("amount")),
                )  # fmt: skip

            plan = self.plan_of(sid, name, cohort_old)
            if plan is None:
                person = self.person_of(sid, name)
                if person is None:
                    drop("студент не найден", "оплата: студент не найден — не перенесена (#5)")
                    continue
                if cohort_old not in self.cohorts:
                    drop("поток не перенесён (удалён или пуст)", "оплата: поток не перенесён")
                    continue
                if amount is not None and amount > 0 and paid and method:
                    plan = await self._restore_enrollment(
                        person, cohort_old, pid, name, p.text(r.get("amount"))
                    )
            if plan is None:
                if amount is None or amount <= 0:
                    drop("нет суммы", "оплата без суммы — не перенесена")
                elif paid is None:
                    drop("дата пустая или вне 2020–2035", "дата оплаты не разобрана")
                else:
                    drop("нет способа оплаты", "нет способа оплаты — не перенесена")
                continue
            if amount is None or amount <= 0:
                drop("нет суммы", "оплата без суммы — не перенесена")
                continue
            if paid is None:
                drop("дата пустая или вне 2020–2035", "дата оплаты не разобрана — не перенесена")
                continue
            if method is None:
                drop("нет способа оплаты", "нет способа оплаты — не перенесена")
                continue
            kind = p.text(r.get("payment_type"))
            note_parts = []
            if kind == "Помесячно":
                month = p.to_int(r.get("month_number"))
                month = month if month and month >= 1 else 1
            else:
                month = 1
                note_parts.append(kind or "без типа")
            for extra in (r.get("notes"), r.get("screenshot_link")):
                if neutral(p.text(extra)):
                    note_parts.append(neutral(p.text(extra)) or "")
            # only a row identical in EVERY field (old payment id included) is a repeat
            key = tuple(p.text(v) for k, v in r.items() if k != "_rowIndex")
            if key in seen:
                rep.merged["PAYMENTS"] += 1
                self._ledger("merge", "точные повторы строки (все поля, вкл. ID)", verified, amount)
                continue
            seen.add(key)
            ref = p.make_ref("PAYMENTS", pid, plan.ref, *key)
            if ref in self.refs["payment"]:
                rep.existing["PAYMENTS"] += 1
                self._ledger("in", "уже были в базе", verified, amount)
                continue
            batch.append(
                Payment(
                    id=uuid.uuid4(),
                    enrollment_id=plan.id,
                    month_no=month,
                    amount=amount,
                    method=method,
                    paid_at=paid,
                    status="подтверждено" if verified else "ожидает",
                    confirmed_at=noon(paid) if verified else None,
                    note="; ".join(note_parts) or None,
                    idempotency_key=uuid.uuid5(NS, ref),
                    legacy_ref=ref,
                )  # fmt: skip
            )
            self.refs["payment"][ref] = batch[-1].id
            rep.imported["PAYMENTS"] += 1
            self._ledger("in", "перенесено", verified, amount)
        self.db.add_all(batch)
        await self.db.flush()

    # ---- ATTENDANCE -----------------------------------------------------------------------

    async def _manual_lesson(self, ctx: CohortCtx, day: date) -> uuid.UUID:
        cohort = ctx.obj
        starts, ends = local_dt(day, cohort.start_time), local_dt(day, cohort.end_time)
        room_id = cohort.room_id
        try:
            await check_room_free(self.db, room_id, [(starts, ends)])
        except DomainError:
            room_id = await self._placeholder_room(cohort.branch_id, ctx.old_id)
        lesson = Lesson(
            id=uuid.uuid4(), cohort_id=cohort.id, room_id=room_id, lesson_date=day,
            starts_at=starts, ends_at=ends, source="manual",
            legacy_ref=p.make_ref("LESSONS", ctx.old_id, day.isoformat()),
        )  # fmt: skip
        self.db.add(lesson)
        await self.db.flush()
        self.lessons[(cohort.id, day)] = lesson.id
        self.rep.note("ручной урок создан: в расписании нет урока на дату отметки")
        return lesson.id

    async def _attendance(self) -> None:
        rep = self.rep
        groups: dict[tuple[uuid.UUID, str, date], list[tuple[bool, str, str]]] = {}
        order: list[tuple[uuid.UUID, str, date]] = []
        plan_of_key: dict[tuple[uuid.UUID, str, date], EnrollPlan] = {}
        for r in self.rows("ATTENDANCE"):
            aid = p.text(r.get("attendance_id"))
            status = p.text(r.get("status"))
            if status not in ("Присутствовал", "Отсутствовал"):
                rep.drop("ATTENDANCE", "статус пустой", aid)
                continue
            plan = self.plan_of(
                p.text(r.get("student_id")),
                p.text(r.get("student_name")),
                p.text(r.get("cohort_id")),
            )
            if plan is None:
                rep.drop("ATTENDANCE", "зачисление не найдено", aid)
                continue
            day = p.parse_date(r.get("lesson_date"))
            if day is None:
                rep.drop("ATTENDANCE", "дата урока пустая или вне 2020–2035", aid)
                continue
            key = (plan.id, plan.cohort_old, day)
            if key not in groups:
                groups[key] = []
                order.append(key)
                plan_of_key[key] = plan
            groups[key].append((status == "Присутствовал", p.text(r.get("instructor_note")), aid))
        values: list[dict[str, Any]] = []
        for key in order:
            rows = groups[key]
            rep.merged["ATTENDANCE"] += len(rows) - 1
            present_noted = [x for x in rows if x[0] and x[1]]
            if len({x[0] for x in rows}) > 1:
                rep.note("конфликт отметок (присутствовал/отсутствовал на один урок)")
                chosen = present_noted[-1] if present_noted else rows[-1]
            else:
                chosen = rows[-1]
            present, note, _ = chosen
            enr_id, cohort_old, day = key
            ctx = self.cohorts[cohort_old]
            lesson_id = self.lessons.get((ctx.obj.id, day))
            if lesson_id is None:
                lesson_id = await self._manual_lesson(ctx, day)
            reason = None if present else neutral(note)
            values.append(
                {
                    "lesson_id": lesson_id,
                    "enrollment_id": enr_id,
                    "present": present,
                    "reason": reason,
                }
            )
        for i in range(0, len(values), BATCH):
            done = await self.db.execute(
                pg_insert(Attendance).values(values[i : i + BATCH]).on_conflict_do_nothing()
            )
            added = int(done.rowcount)  # type: ignore[attr-defined]
            rep.imported["ATTENDANCE"] += added
            rep.existing["ATTENDANCE"] += len(values[i : i + BATCH]) - added

    # ---- MARKETING ------------------------------------------------------------------------

    async def _marketing(self) -> None:
        rep = self.rep
        seen: set[str] = set()
        for r in self.rows("MARKETING"):
            cid = p.text(r.get("campaign_id"))
            title = p.text(r.get("course_name"))
            if "тест" in title.lower():
                rep.drop("MARKETING", "тестовая кампания", cid)
                rep.flag("MARKETING", "кампания «тест» — не перенесена", cid, course=title)
                continue
            start = p.parse_date(r.get("start_date"))
            if start is None:
                rep.drop("MARKETING", "дата начала пустая или вне 2020–2035", cid)
                continue
            budget = p.to_decimal(r.get("budget_tjs"))
            if budget is None or budget < 0:
                rep.flag("MARKETING", "бюджет не указан, поставлен 0", cid, course=title)
                budget = Decimal(0)
            end = p.parse_date(r.get("end_date"))
            if end is not None and end < start:
                end = None
            ref = p.make_ref("MARKETING", cid or "—", title, start)
            if ref in seen:
                rep.merged["MARKETING"] += 1
                continue
            seen.add(ref)
            if ref in self.refs["campaign"]:
                rep.existing["MARKETING"] += 1
                continue
            branch = self.branch_of(p.text(r.get("city")))
            if branch is None:
                branch = "Душанбе"
                rep.flag("MARKETING", "город не указан, поставлен Душанбе", cid, course=title)
            ctx = self.cohorts.get(p.text(r.get("cohort_id")))
            course_id = ctx.obj.course_id if ctx else self.course_for_text(title)
            platform = "Facebook Ads" if p.text(r.get("platform")) == "Facebook Ads" else "другое"
            status = CAMPAIGN_STATUS.get(p.text(r.get("status")), "завершена")
            if any(p.parse_dt(r.get(k)) for k in ("cost_per_lead", "cost_per_student")):
                rep.note(
                    "кампания с повреждёнными метриками (даты вместо чисел): пересчитаны заново"
                )
            campaign = Campaign(
                id=uuid.uuid4(), name=neutral(title) or cid or "Кампания", course_id=course_id,
                branch_id=self.branches[branch], platform=platform, start_date=start, end_date=end,
                budget=budget, status=status, legacy_ref=ref,
            )  # fmt: skip
            self.db.add(campaign)
            self.refs["campaign"][ref] = campaign.id
            rep.imported["MARKETING"] += 1
        await self.db.flush()

    # ---- LEADS ----------------------------------------------------------------------------

    async def _leads(self) -> None:
        rep = self.rep
        seen: set[tuple[str, date | None]] = set()
        for r in self.rows("LEADS"):
            lid = p.text(r.get("lead_id"))
            if not p.text(r.get("full_name")):
                rep.drop("LEADS", "нет ФИО", lid)
                continue
            moment = p.parse_dt(r.get("timestamp"))
            if moment is not None and not p.MIN_DATE <= moment.date() <= p.MAX_DATE:
                moment = None
            phone, raw = p.phone_of(r.get("phone"))
            name, name_bad = p.name_of(r.get("full_name"))
            key = (p.phone9(raw) or f"n:{p.norm_name(name)}", moment.date() if moment else None)
            if key in seen:
                rep.merged["LEADS"] += 1
                continue
            seen.add(key)
            ref = p.make_ref("LEADS", lid or "—", *key)
            if ref in self.refs["lead"]:
                rep.existing["LEADS"] += 1
                continue
            review = name_bad
            if name_bad:
                rep.flag("LEADS", "ФИО с лишними символами, очищено", lid, name=name)
            if not raw:
                rep.flag("LEADS", "заполнить телефон", lid, name=name)
                review = True
            elif phone is None:
                rep.flag("LEADS", "телефон не распознан", lid, name=name, phone=raw)
                review = True
            if moment is None:
                rep.flag(
                    "LEADS",
                    "дата пустая или вне 2020–2035, поставлена дата переноса",
                    lid,
                    name=name,
                )
                review = True
            branch = self.branch_of(p.text(r.get("city")))
            if branch is None:
                branch = "Душанбе"
                rep.flag("LEADS", "город не указан, поставлен Душанбе", lid, name=name)
                review = True
            source_raw = p.text(r.get("source"))
            comment_parts = [neutral(p.text(r.get("comments")))]
            if source_raw == "Электронная почта":
                comment_parts.append("источник в старой системе: электронная почта")
            course_text = p.text(r.get("Название компании"))
            lead = Lead(
                id=uuid.uuid4(), full_name=name, raw_name=p.text(r.get("full_name")),
                phone=phone or (raw or None), phone_raw=raw or None,
                course_id=self.course_lookup.get(p.norm_name(course_text)) if course_text else None,
                source=LEAD_SOURCE.get(source_raw, "другое"), branch_id=self.branches[branch],
                call_status=CALL_STATUS.get(p.text(r.get("call_status")), "не звонили"),
                status=LEAD_STATUS.get(p.text(r.get("client_status")), "новый"),
                comment="; ".join(c for c in comment_parts if c) or None, needs_review=review,
                created_at=moment or datetime.now(UTC), legacy_ref=ref,
            )  # fmt: skip
            self.db.add(lead)
            self.refs["lead"][ref] = lead.id
            rep.imported["LEADS"] += 1
        await self.db.flush()

    # ---- INSTRUCTOR_PAYMENTS (columns shifted by one) -------------------------------------

    async def _payouts(self) -> None:
        rep = self.rep
        used: set[tuple[uuid.UUID, uuid.UUID, date]] = set()
        seen_refs: set[str] = set()
        for iid, cid, period in (
            await self.db.execute(
                select(
                    InstructorPayout.instructor_id,
                    InstructorPayout.cohort_id,
                    InstructorPayout.period,
                )
            )
        ).all():
            used.add((iid, cid, period))
        for r in self.rows("INSTRUCTOR_PAYMENTS"):
            pid = p.text(r.get("payment_id"))
            # the old export shifted the columns: instructor_id holds the cohort id,
            # instructor_name the instructor id, cohort_id the instructor name, cohort_name the
            # month number, month the amount and year the date
            cohort_old, instr_old = p.text(r.get("instructor_id")), p.text(r.get("instructor_name"))
            name, month_no = p.text(r.get("cohort_id")), p.text(r.get("cohort_name"))
            amount, paid = p.to_decimal(r.get("month")), p.parse_date(r.get("year"))
            if not pid or not cohort_old:
                rep.drop("INSTRUCTOR_PAYMENTS", "пустой ID", pid)
                continue
            ctx = self.cohorts.get(cohort_old)
            person = self.instructor_of(instr_old, name)
            if ctx is None:
                rep.drop("INSTRUCTOR_PAYMENTS", "поток не найден", pid)
                rep.flag(
                    "INSTRUCTOR_PAYMENTS",
                    "поток не найден",
                    pid,
                    cohort=cohort_old,
                    instructor=name,
                )
                continue
            if person is None or ctx.obj.instructor_id != person.id:
                rep.drop("INSTRUCTOR_PAYMENTS", "инструктор не совпал с инструктором потока", pid)
                rep.flag(
                    "INSTRUCTOR_PAYMENTS",
                    "инструктор не совпал с инструктором потока",
                    pid,
                    cohort=cohort_old,
                    instructor=name,
                    amount=str(amount),
                )
                continue
            if amount is None or amount <= 0 or paid is None:
                rep.drop("INSTRUCTOR_PAYMENTS", "нет суммы или даты", pid)
                rep.flag(
                    "INSTRUCTOR_PAYMENTS",
                    "нет суммы или даты выплаты",
                    pid,
                    cohort=cohort_old,
                    instructor=name,
                )
                continue
            # the work month: the cohort's n-th month; without a usable n, the month of payment
            periods = cohort_periods(ctx.obj.start_date, ctx.obj.end_date)
            n = p.to_int(month_no)
            period = periods[n - 1] if n and 1 <= n <= len(periods) else paid.replace(day=1)
            ref = p.make_ref("INSTRUCTOR_PAYMENTS", pid, cohort_old, person.key, period)
            if ref in seen_refs:
                rep.merged["INSTRUCTOR_PAYMENTS"] += 1
                continue
            seen_refs.add(ref)
            if ref in self.refs["instructor_payout"]:
                rep.existing["INSTRUCTOR_PAYMENTS"] += 1
                continue
            if (person.id, ctx.obj.id, period) in used:
                rep.drop("INSTRUCTOR_PAYMENTS", "вторая выплата за тот же месяц потока", pid)
                rep.flag(
                    "INSTRUCTOR_PAYMENTS",
                    "вторая выплата за тот же месяц — не перенесена",
                    pid,
                    cohort=cohort_old,
                    instructor=name,
                    amount=str(amount),
                )
                continue
            used.add((person.id, ctx.obj.id, period))
            payout = InstructorPayout(
                id=uuid.uuid4(), instructor_id=person.id, cohort_id=ctx.obj.id, period=period,
                amount=amount, paid_at=paid, method="наличные",
                note=f"перенос; способ неизвестен; месяц потока {month_no}".strip(),
                legacy_ref=ref,
            )  # fmt: skip
            self.db.add(payout)
            self.refs["instructor_payout"][ref] = payout.id
            rep.imported["INSTRUCTOR_PAYMENTS"] += 1
        await self.db.flush()

    # ---- statuses and numbers -------------------------------------------------------------

    async def _close_cohorts(self) -> None:
        """#11 + #20 for the cohorts this run created: the same code path as the daily job."""
        done = [c for c in self.cohorts.values() if c.created and c.obj.status == DONE]
        for ctx in done:
            await sync_status(self.db, ctx.obj, None, self.today)
        await self.db.flush()
        for ctx in done:
            rows = (
                (
                    await self.db.execute(
                        select(Enrollment).where(
                            Enrollment.cohort_id == ctx.obj.id, Enrollment.status == COMPLETED
                        )
                    )
                )
                .scalars()
                .all()
            )
            for enrollment in rows:
                await reevaluate(self.db, enrollment, ctx.obj, None)
        await self.db.flush()

    async def _reconcile(self) -> None:
        rep = self.rep
        imported_student: list[ColumnElement[bool]] = [Student.legacy_ref.is_not(None)]
        imported_cohort: list[ColumnElement[bool]] = [Cohort.legacy_ref.is_not(None)]
        students = await student_counts(self.db, imported_student)
        enrolls = await enrollment_counts(self.db, imported_cohort)
        income = await income_total(self.db, imported_cohort)
        graduates = await graduate_count(self.db, [Enrollment.status == GRADUATE, *imported_cohort])
        old = self.snap
        old_students = sum(1 for r in old.get("STUDENTS", []) if p.text(r.get("student_id")))
        old_active = sum(
            1 for r in old.get("ENROLLMENTS", []) if p.text(r.get("status")) == "Активный"
        )
        old_money = sum(
            (p.to_decimal(r.get("amount")) or Decimal(0))
            for r in old.get("PAYMENTS", [])
            if p.text(r.get("verified")) == "Да"
        )
        old_grads = sum(
            1
            for r in old.get("ENROLLMENTS", [])
            if (t := p.to_decimal(r.get("final_score"))) is not None and t >= PASS_TOTAL
        )
        rep.recon += [
            Recon(
                "Студентов (всего)",
                str(students["всего"]),
                f"{old_students} строк в листе; интерфейс: 783 / 931 / 965",
                "строки сливаются в людей по телефону и ФИО (#4, #14); в листе много дублей ID",
            ),
            Recon(
                "Активных студентов",
                str(students["активный"]),
                "—",
                "студент активен, если есть активное зачисление в незавершённом потоке",
            ),
            Recon(
                "Активных зачислений",
                str(enrolls["активный"]),
                f"{old_active} строк в листе",
                "повторы слиты, активные зачисления завершённых потоков закрыты (#11)",
            ),
            Recon(
                "Сумма подтверждённых оплат, TJS",
                f"{income:.2f}",
                f"{old_money:.2f} по листу",
                "точные повторы оплат отброшены, оплаты без зачисления не перенесены (#5)",
            ),
            Recon(
                "Выпускников",
                str(graduates),
                f"{old_grads} с итогом ≥ 70 в листе; интерфейс: 390 / 400 / 451",
                "выпускник = итог ≥ 70 у зачисления завершённого потока, дубли слиты",
            ),
        ]
        rep.recon.append(
            Recon(
                "Зачислений всего / завершил / отчислен",
                f"{enrolls['всего']} / {enrolls['завершил']} / {enrolls['отчислен']}",
                "—",
                "",
            )
        )

        await self._ledgers(income)

    async def _ledgers(self, income: Decimal) -> None:
        """The balance sheets of the money and of the active enrollments (they must add up)."""
        rep = self.rep
        led = self.pay_ledger
        n0, total = self.pay_rows, self.pay_total
        lines: list[tuple[str, str, str]] = [
            ("Лист PAYMENTS: все строки / подтверждённая сумма", str(n0), f"{total:.2f}")
        ]
        left_n, left_sum = n0, total
        for kind, sign in (("drop", "− отброшено: "), ("merge", "− слито: ")):
            for label, (n, amount) in sorted(led[kind].items()):
                lines.append((sign + label, str(n), f"{amount:.2f}"))
                left_n, left_sum = left_n - n, left_sum - amount
        lines.append(("= перенесено (расчёт)", str(left_n), f"{left_sum:.2f}"))
        lines.append(("перенесено по `app/metrics` (income_total)", "", f"{income:.2f}"))
        lines.append(("разница (должна быть 0)", "", f"{left_sum - income:.2f}"))
        rep.ledgers.append(("Сверка денег", lines))
        # active enrollments
        plans = [
            pl
            for pl in self.plans.values()
            if any(p.text(r.get("status")) == "Активный" for r in pl.rows)
        ]
        merged = sum(
            sum(1 for r in pl.rows if p.text(r.get("status")) == "Активный") - 1 for pl in plans
        )
        status = {
            i: st
            for i, st in (
                await self.db.execute(
                    select(Enrollment.id, Enrollment.status).where(
                        Enrollment.id.in_([pl.id for pl in plans])
                    )
                )
            ).all()
        }
        by_status = Counter(status.values())
        enr: list[tuple[str, str, str]] = [
            ("Лист ENROLLMENTS: строки со статусом «Активный»", str(self.enr_active_rows), "")
        ]
        for label, n in sorted(self.enr_drops.items()):
            enr.append((f"− отброшено: {label}", str(n), ""))
        enr.append(("− слито повторов (то же зачисление студент+поток)", str(merged), ""))
        enr.append(("= зачислений из активных строк", str(len(plans)), ""))
        names = {
            "активный": "остались активными",
            "выпускник": "стали выпускниками (поток завершён, итог ≥ 70)",
            "завершил": "закрыты как «завершил» (поток завершён, #11)",
            "отчислен": "отчислены (старший статус в слитых строках)",
        }
        for st, label in names.items():
            enr.append((f"  из них {label}", str(by_status.get(st, 0)), ""))
        rep.ledgers.append(("Сверка активных зачислений", enr))
