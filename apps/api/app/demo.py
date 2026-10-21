"""A fake dataset for demos: `python -m app.cli seed-demo` / `wipe-demo`.

Every invented row gets an id inside one reserved range (`DEMO_PREFIX`), and nothing else ever
does (real ids are random v4), so `wipe_demo` removes exactly what `seed_demo` made and nothing
that was entered by hand afterwards. Names and phones are invented; the demo users share one
password that `seed_demo` returns (shown once by the CLI).
"""

import random
import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import record
from app.cohorts.schedule import generate_lessons
from app.cohorts.status import status_for, today
from app.core.security import hash_password, temp_password
from app.metrics.money import cohort_periods
from app.models import (
    AppUser,
    Attendance,
    Campaign,
    Cohort,
    Course,
    Enrollment,
    Grade,
    InstructorPayout,
    Lead,
    Payment,
    Room,
    Student,
)

DEMO_PREFIX = "de000000-0000-4000-"
LOGIN_PREFIX = "demo_"
BRANCHES = ("Душанбе", "Истаравшан")
FIRST = (
    "Азим",
    "Бахор",
    "Далер",
    "Зарина",
    "Ильхом",
    "Лола",
    "Мехр",
    "Нодира",
    "Орзу",
    "Рустам",
    "Сабо",
    "Тахмина",
    "Умед",
    "Фируза",
    "Шахло",
    "Эмин",
)
LAST = (
    "Тестов",
    "Образцов",
    "Примеров",
    "Макетов",
    "Вымышленов",
    "Условный",
    "Пробников",
    "Демонов",
)
COURSES = (
    ("Демо: веб-разработка", "IT", "600", 3, "offline"),
    ("Демо: дизайн интерфейсов", "Дизайн", "500", 3, "offline"),
    ("Демо: английский онлайн", "Языки", "350", 3, "online"),
)
PLATFORMS = ("Facebook Ads", "Instagram", "TikTok", "Telegram")
SOURCES = ("Facebook", "Instagram", "TikTok", "Telegram", "сайт", "рекомендация", "звонок")
LEAD_STATUSES = ("новый", "заинтересован", "нулевой урок", "записан", "отказ")
CALL_STATUSES = ("не звонили", "не ответил", "позвонили", "перезвонить")


class Ids:
    """Sequential ids inside the demo range."""

    def __init__(self) -> None:
        self.n = 0

    def next(self, block: int = 0x8000) -> uuid.UUID:
        self.n += 1
        return uuid.UUID(f"{DEMO_PREFIX}{block:04x}-{self.n:012x}")


def _is_demo(column: str = "id") -> str:
    return f"{column}::text LIKE '{DEMO_PREFIX}%'"


async def demo_exists(db: AsyncSession) -> bool:
    return bool(
        (await db.execute(text(f"SELECT 1 FROM app_user WHERE {_is_demo()} LIMIT 1"))).first()
    )


def _month_start(d: date, back: int) -> date:
    index = d.year * 12 + d.month - 1 - back
    return date(index // 12, index % 12 + 1, 1)


def _next_weekday(d: date, iso: int) -> date:
    return d + timedelta(days=(iso - d.isoweekday()) % 7)


async def seed_demo(db: AsyncSession, on: date | None = None) -> tuple[str, int]:
    """Insert the dataset. Returns (the demo users' password, rows made). Run `demo_exists`
    first: a second run would collide on the fixed logins."""
    now_day = on or today()
    rng = random.Random(20260101)
    ids = Ids()
    password = temp_password()
    pw_hash = hash_password(password)
    count = 0

    def add(obj: object) -> None:
        nonlocal count
        db.add(obj)
        count += 1

    role = {
        code: rid
        for code, rid in (
            await db.execute(text("SELECT code, id FROM role WHERE code IS NOT NULL"))
        ).all()
    }
    branch = {name: bid for name, bid in (await db.execute(text("SELECT name, id FROM branch")))}

    def user(
        login: str, name: str, code: str, branch_name: str | None, n: int, rate: str = "0"
    ) -> AppUser:
        u = AppUser(
            id=ids.next(),
            login=f"{LOGIN_PREFIX}{login}",
            full_name=name,
            phone=f"+99200000{n:04d}",
            branch_id=branch[branch_name] if branch_name else None,
            role_id=role[code],
            password_hash=pw_hash,
            default_rate=Decimal(rate),
        )
        add(u)
        return u

    user("admin", "Демо Суперадминов", "superadmin", None, 1)
    courses = []
    for name, direction, price, months, fmt in COURSES:
        c = Course(
            id=ids.next(),
            name=name,
            direction=direction,
            default_price_month=Decimal(price),
            duration_months=months,
            format=fmt,
        )
        add(c)
        courses.append(c)
    await db.flush()

    phone_n = 100
    for bi, bname in enumerate(BRANCHES):
        bid = branch[bname]
        manager = user(f"manager{bi + 1}", f"Менеджер Образцов {bi + 1}", "manager", bname, 10 + bi)
        instructors = [
            user(
                f"instructor{bi + 1}{k}",
                f"Инструктор Примеров {bi + 1}{k}",
                "instructor",
                bname,
                20 + bi * 2 + k,
                rate="1500",
            )
            for k in (1, 2)
        ]
        rooms = []
        for rname, cap in (
            ("Демо-аудитория А", 16),
            ("Демо-аудитория Б", 12),
            ("Демо-аудитория В", 20),
        ):
            r = Room(id=ids.next(), branch_id=bid, name=rname, capacity=cap)
            add(r)
            rooms.append(r)
        await db.flush()

        campaigns = []
        for k, platform in enumerate(PLATFORMS[:2]):
            camp = Campaign(
                id=ids.next(),
                name=f"Демо-кампания {platform} {bi + 1}",
                course_id=courses[k].id,
                branch_id=bid,
                platform=platform,
                start_date=now_day - timedelta(days=45),
                end_date=None if k == 0 else now_day - timedelta(days=5),
                budget=Decimal(800 + 400 * k),
                status="активна" if k == 0 else "завершена",
            )
            add(camp)
            campaigns.append(camp)

        # one running, one finished, one recruiting cohort per branch
        plans = (
            ("running", _next_weekday(_month_start(now_day, 2), 1), 17),
            ("done", _next_weekday(_month_start(now_day, 6), 2), 12),
            ("recruiting", _next_weekday(now_day + timedelta(days=21), 1), 12),
        )
        students: list[Student] = []
        for k in range(12):
            phone_n += 1
            s = Student(
                id=ids.next(),
                full_name=f"{FIRST[(k + bi * 5) % len(FIRST)]} {LAST[(k * 3 + bi) % len(LAST)]}",
                gender="female" if k % 2 else "male",
                phone=f"+99200100{phone_n:04d}",
                branch_id=bid,
            )
            add(s)
            students.append(s)
        await db.flush()

        for ci, (kind, start, weeks) in enumerate(plans):
            end = start + timedelta(weeks=weeks)
            course = courses[ci % len(courses)]
            cohort = Cohort(
                id=ids.next(),
                course_id=course.id,
                branch_id=bid,
                instructor_id=instructors[ci % 2].id,
                room_id=rooms[ci].id,
                start_date=start,
                end_date=end,
                weekdays=[1, 3, 5] if ci == 0 else [2, 4],
                start_time=time(10 + ci, 0),
                end_time=time(11 + ci, 30),
                capacity=rooms[ci].capacity,
                price_month=course.default_price_month,
                instructor_rate=Decimal("1500"),
                status=status_for(start, end, now_day),
            )
            add(cohort)
            await db.flush()
            count += await generate_lessons(db, cohort)

            members = students[: {"running": 8, "done": 6, "recruiting": 4}[kind]]
            if kind == "recruiting":
                members = students[8:12]
            enrollments = []
            for s in members:
                e = Enrollment(
                    id=ids.next(),
                    cohort_id=cohort.id,
                    student_id=s.id,
                    status="активный",
                    enrolled_at=datetime.combine(start, time(9, 0), tzinfo=UTC),
                )
                add(e)
                enrollments.append(e)
            await db.flush()
            if kind == "recruiting":
                continue

            lessons = (
                (
                    await db.execute(
                        text(
                            "SELECT id FROM lesson WHERE cohort_id = :c AND lesson_date < :d "
                            "ORDER BY starts_at"
                        ),
                        {"c": cohort.id, "d": now_day},
                    )
                )
                .scalars()
                .all()
            )
            for e in enrollments:
                keen = rng.random()
                for lid in lessons:
                    present = rng.random() < 0.6 + 0.4 * keen
                    add(
                        Attendance(
                            lesson_id=lid,
                            enrollment_id=e.id,
                            present=present,
                            reason=None if present else "болезнь",
                            marked_by=instructors[ci % 2].id,
                        )
                    )
                grade = Grade(
                    enrollment_id=e.id,
                    homework=rng.randint(22, 40),
                    final=rng.randint(15, 40) if kind == "done" else None,
                )
                add(grade)
                if kind == "done":
                    total = (grade.homework or 0) + (grade.final or 0)
                    e.status = "выпускник" if total >= 56 else "завершил"

            periods = [p for p in cohort_periods(start, end) if p <= now_day]
            for e in enrollments:
                for month_no, period in enumerate(periods, start=1):
                    if rng.random() < 0.15:
                        continue  # a debt
                    confirmed = rng.random() < 0.8 or period < _month_start(now_day, 1)
                    paid = min(period + timedelta(days=rng.randint(0, 10)), now_day)
                    add(
                        Payment(
                            id=ids.next(),
                            enrollment_id=e.id,
                            month_no=month_no,
                            amount=course.default_price_month,
                            method=rng.choice(("alif", "payvand", "наличные")),
                            paid_at=paid,
                            status="подтверждено" if confirmed else "ожидает",
                            confirmed_by=manager.id if confirmed else None,
                            confirmed_at=datetime.combine(paid, time(12, 0), tzinfo=UTC)
                            if confirmed
                            else None,
                            idempotency_key=ids.next(0x9000),
                        )
                    )
            for period in periods[:-1] if kind == "running" else periods:
                add(
                    InstructorPayout(
                        id=ids.next(),
                        instructor_id=instructors[ci % 2].id,
                        cohort_id=cohort.id,
                        period=period,
                        amount=Decimal("1500"),
                        paid_at=min(period + timedelta(days=27), now_day),
                        method="наличные",
                    )
                )
            await db.flush()

        for k in range(12):
            phone_n += 1
            status = LEAD_STATUSES[k % len(LEAD_STATUSES)]
            name = f"{FIRST[(k * 5 + bi) % len(FIRST)]} {LAST[(k * 7 + bi + 3) % len(LAST)]}"
            add(
                Lead(
                    id=ids.next(),
                    full_name=name,
                    raw_name=name,
                    phone=f"+99200200{phone_n:04d}",
                    phone_raw=f"+99200200{phone_n:04d}",
                    course_id=courses[k % len(courses)].id,
                    source=SOURCES[k % len(SOURCES)],
                    campaign_id=campaigns[k % 2].id if k % 3 else None,
                    branch_id=bid,
                    call_status=CALL_STATUSES[k % len(CALL_STATUSES)],
                    status=status,
                    refusal_reason="дорого" if status == "отказ" else None,
                    converted_student_id=students[k % len(students)].id
                    if status == "записан"
                    else None,
                )
            )
        await db.flush()

    await record(
        db, None, "demo.seed", "demo", None, {"rows": [None, count]}, label=f"{count} записей"
    )
    return password, count


# Children before parents: the order foreign keys need.
_WIPE = (
    ("attendance", "enrollment_id"),
    ("grade", "enrollment_id"),
    ("payment", "id"),
    ("instructor_payout", "id"),
    ("lead", "id"),
    ("enrollment", "id"),
    ("cohort", "id"),
    ("student", "id"),
    ("campaign", "id"),
    ("room", "id"),
    ("course", "id"),
    ("refresh_token", "user_id"),
    ("app_user", "id"),
)


async def wipe_demo(db: AsyncSession) -> int:
    """Delete every row `seed_demo` made, and only those. Returns how many."""
    total = 0
    for table, column in _WIPE:
        result = await db.execute(text(f"DELETE FROM {table} WHERE {_is_demo(column)}"))
        total += int(result.rowcount or 0)  # type: ignore[attr-defined]
    await record(
        db, None, "demo.wipe", "demo", None, {"rows": [None, total]}, label=f"{total} записей"
    )
    return total
