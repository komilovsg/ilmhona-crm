"""Cohorts (потоки): CRUD, status, lessons, enrollments.

Rights: `cohorts` view to read, `cohorts` change to write (never for the instructor role: #24).
Branch scope everywhere; an instructor sees only cohorts where they teach (others are 404, also
their lessons and enrollments). Numbers (fill, counts) come from `app.metrics`.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Annotated, Any, Self

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import diff_of, record
from app.auth.deps import Principal, require, require_csrf_header
from app.cohorts import status as st
from app.cohorts.schedule import check_room_free, generate_lessons, local_dt
from app.core.db import DB
from app.core.errors import FORBIDDEN, NOT_FOUND, VALIDATION_FAILED, DomainError
from app.core.versioning import Version, check_version
from app.education.errors import (
    COHORT_CLOSED,
    COHORT_FULL,
    COHORT_IN_USE,
    COHORT_NOT_CANCELLED,
    INSTRUCTOR_INVALID,
    LESSON_CANCELLED,
    ROOM_BRANCH_MISMATCH,
    STUDENT_BRANCH_MISMATCH,
)
from app.education.scope import (
    branch_for_write,
    check_cohort_visible,
    cohort_filters,
    writer,
)
from app.metrics import cohort_enrolled, cohort_fill, has_marks
from app.models import AppUser, Branch, Cohort, Course, Enrollment, Lesson, Role, Room, Student
from app.permissions import allows

router = APIRouter(prefix="/api/v1", tags=["cohorts"], dependencies=[Depends(require_csrf_header)])

View = Annotated[Principal, require("cohorts", "view")]
Change = Annotated[Principal, writer("cohorts")]

MIN_DATE, MAX_DATE = date(2020, 1, 1), date(2035, 12, 31)
OPEN_FROM, OPEN_TO = time(7, 0), time(22, 0)
Day = Annotated[date, Field(ge=MIN_DATE, le=MAX_DATE)]
Capacity = Annotated[int, Field(ge=1, le=100)]
Price = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)]
ENROLLMENT_STATUSES = ("активный", "завершил", "выпускник", "отчислен")


def window_problem(start: time, end: time) -> str | None:
    """#6: a lesson starts at 07:00 or later, ends by 22:00 and lasts 30-240 minutes."""
    minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    if start < OPEN_FROM or end > OPEN_TO:
        return "time outside 07:00-22:00"
    if not 30 <= minutes <= 240:
        return "duration must be 30-240 minutes"
    return None


def schedule_problem(
    start_date: date, end_date: date, weekdays: list[int], start: time, end: time
) -> str | None:
    if end_date <= start_date:
        return "end_date must be after start_date"
    if not weekdays or any(not 1 <= d <= 7 for d in weekdays):
        return "weekdays: 1..7, at least one"
    return window_problem(start, end)


def _minute(t: time) -> time:
    return t.replace(second=0, microsecond=0)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CohortCreate(Strict):
    course_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    instructor_id: uuid.UUID | None = None
    room_id: uuid.UUID
    start_date: Day
    end_date: Day
    weekdays: list[Annotated[int, Field(ge=1, le=7)]] = Field(min_length=1, max_length=7)
    start_time: time
    end_time: time
    capacity: Capacity
    price_month: Price | None = None  # default: the course's price

    @model_validator(mode="after")
    def _check(self) -> Self:
        self.weekdays = sorted(set(self.weekdays))
        self.start_time, self.end_time = _minute(self.start_time), _minute(self.end_time)
        problem = schedule_problem(
            self.start_date, self.end_date, self.weekdays, self.start_time, self.end_time
        )
        if problem:
            raise ValueError(problem)
        return self


class CohortUpdate(Strict):
    """Only the fields present change (`instructor_id: null` clears the instructor)."""

    instructor_id: uuid.UUID | None = None
    room_id: uuid.UUID | None = None
    start_date: Day | None = None
    end_date: Day | None = None
    weekdays: list[Annotated[int, Field(ge=1, le=7)]] | None = Field(
        default=None, min_length=1, max_length=7
    )
    start_time: time | None = None
    end_time: time | None = None
    capacity: Capacity | None = None
    price_month: Price | None = None


class LessonIn(Strict):
    date: Day
    start_time: time
    end_time: time
    room_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        self.start_time, self.end_time = _minute(self.start_time), _minute(self.end_time)
        problem = window_problem(self.start_time, self.end_time)
        if problem:
            raise ValueError(problem)
        return self


class LessonMove(Strict):
    date: Day | None = None
    start_time: time | None = None
    end_time: time | None = None
    room_id: uuid.UUID | None = None


class NewStudent(Strict):
    full_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    phone: Phone | None = None
    gender: Annotated[str, StringConstraints(pattern=r"^(male|female)$")] | None = None


class EnrollIn(Strict):
    student_id: uuid.UUID | None = None
    new_student: NewStudent | None = None

    @model_validator(mode="after")
    def _one(self) -> Self:
        if (self.student_id is None) == (self.new_student is None):
            raise ValueError("give student_id or new_student")
        return self


class EnrollmentStatus(Strict):
    status: Annotated[str, StringConstraints(pattern=r"^(активный|завершил|выпускник|отчислен)$")]


def _hm(t: time) -> str:
    return t.strftime("%H:%M")


def _snapshot(c: Cohort) -> dict[str, Any]:
    return {
        "code": c.code,
        "course_id": c.course_id,
        "instructor_id": c.instructor_id,
        "room_id": c.room_id,
        "start_date": c.start_date,
        "end_date": c.end_date,
        "weekdays": list(c.weekdays),
        "start_time": _hm(c.start_time),
        "end_time": _hm(c.end_time),
        "capacity": c.capacity,
        "price_month": str(c.price_month),
        "status": c.status,
    }


def _out(
    c: Cohort,
    course: str,
    branch: str,
    instructor: str | None,
    room: str,
    fill: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": c.id,
        "version": c.version,
        "code": c.code,
        "course_id": c.course_id,
        "course_name": course,
        "branch_id": c.branch_id,
        "branch_name": branch,
        "instructor_id": c.instructor_id,
        "instructor_name": instructor,
        "room_id": c.room_id,
        "room_name": room,
        "start_date": c.start_date,
        "end_date": c.end_date,
        "weekdays": list(c.weekdays),
        "start_time": _hm(c.start_time),
        "end_time": _hm(c.end_time),
        "capacity": c.capacity,
        "price_month": c.price_month,
        "status": c.status,
        "fill": fill,
    }


def _select() -> Any:
    return (
        select(Cohort, Course.name, Branch.name, AppUser.full_name, Room.name)
        .join(Course, Course.id == Cohort.course_id)
        .join(Branch, Branch.id == Cohort.branch_id)
        .join(Room, Room.id == Cohort.room_id)
        .outerjoin(AppUser, AppUser.id == Cohort.instructor_id)
    )


async def _outs(db: AsyncSession, rows: Sequence[Any]) -> list[dict[str, Any]]:
    fill = await cohort_fill(db, [r[0] for r in rows])
    return [_out(c, course, branch, ins, room, fill[c.id]) for c, course, branch, ins, room in rows]


async def _load(
    db: AsyncSession, p: Principal, cohort_id: uuid.UUID, *, lock: bool = False
) -> Cohort:
    query = select(Cohort).where(Cohort.id == cohort_id)
    if lock:
        query = query.with_for_update()
    cohort = (await db.execute(query)).scalar_one_or_none()
    if cohort is None:
        raise DomainError(NOT_FOUND)
    check_cohort_visible(p, cohort)
    return cohort


async def _detail(db: AsyncSession, cohort_id: uuid.UUID) -> dict[str, Any]:
    rows = (await db.execute(_select().where(Cohort.id == cohort_id))).all()
    return (await _outs(db, rows))[0]


async def _check_instructor(
    db: AsyncSession, instructor_id: uuid.UUID | None, branch_id: uuid.UUID
) -> None:
    """An active user with role instructor, working in the cohort's branch (or in all)."""
    if instructor_id is None:
        return
    row = (
        await db.execute(
            select(AppUser.is_active, AppUser.branch_id, Role.code)
            .join(Role, Role.id == AppUser.role_id)
            .where(AppUser.id == instructor_id)
        )
    ).first()
    if row is None or not row[0] or row[2] != "instructor" or row[1] not in (None, branch_id):
        raise DomainError(INSTRUCTOR_INVALID)


async def _room_in_branch(
    db: AsyncSession, p: Principal, room_id: uuid.UUID, branch_id: uuid.UUID
) -> Room:
    """A room outside the user's scope is 404 like a missing one (no probing other branches)."""
    room = (await db.execute(select(Room).where(Room.id == room_id))).scalar_one_or_none()
    if room is None:
        raise DomainError(NOT_FOUND)
    p.check_scope(room.branch_id)
    if room.branch_id != branch_id:
        raise DomainError(ROOM_BRANCH_MISMATCH)
    return room


def _now() -> datetime:
    return datetime.now(UTC)


# ---- cohorts -----------------------------------------------------------------------------


@router.get("/cohorts")
async def list_cohorts(
    p: View,
    db: DB,
    status: str | None = None,
    branch_id: uuid.UUID | None = None,
    q: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 24,
) -> dict[str, Any]:
    where = cohort_filters(p)
    if status:
        where.append(Cohort.status == status)
    if branch_id:
        where.append(Cohort.branch_id == branch_id)
    if q and q.strip():
        like = f"%{q.strip().replace('%', r'\%').replace('_', r'\_')}%"
        where.append(
            or_(Cohort.code.ilike(like), Course.name.ilike(like), AppUser.full_name.ilike(like))
        )
    total = (
        await db.execute(
            select(func.count())
            .select_from(Cohort)
            .join(Course, Course.id == Cohort.course_id)
            .outerjoin(AppUser, AppUser.id == Cohort.instructor_id)
            .where(*where)
        )
    ).scalar_one()
    rows = (
        await db.execute(
            _select()
            .where(*where)
            .order_by(Cohort.start_date.desc(), Cohort.code)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).all()
    return {
        "items": await _outs(db, list(rows)),
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/cohorts/instructors")
async def list_instructors(
    p: View, db: DB, branch_id: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    """Active instructors who may teach in `branch_id` (their branch, or all branches): the
    choices of the cohort form. Not the users section: a manager needs no rights on it."""
    where = [Role.code == "instructor", AppUser.is_active]
    if p.branch_id is not None:
        branch_id = p.branch_id
    if branch_id:
        where.append(or_(AppUser.branch_id.is_(None), AppUser.branch_id == branch_id))
    rows = await db.execute(
        select(AppUser.id, AppUser.full_name, AppUser.branch_id)
        .join(Role, Role.id == AppUser.role_id)
        .where(*where)
        .order_by(AppUser.full_name)
    )
    return [{"id": i, "full_name": n, "branch_id": b} for i, n, b in rows.all()]


@router.post("/cohorts", status_code=201)
async def create_cohort(body: CohortCreate, p: Change, db: DB) -> dict[str, Any]:
    branch_id = branch_for_write(p, body.branch_id)
    course = (
        await db.execute(select(Course).where(Course.id == body.course_id))
    ).scalar_one_or_none()
    if course is None:
        raise DomainError(NOT_FOUND)
    await _room_in_branch(db, p, body.room_id, branch_id)
    await _check_instructor(db, body.instructor_id, branch_id)
    cohort = Cohort(
        course_id=course.id,
        branch_id=branch_id,
        instructor_id=body.instructor_id,
        room_id=body.room_id,
        start_date=body.start_date,
        end_date=body.end_date,
        weekdays=body.weekdays,
        start_time=body.start_time,
        end_time=body.end_time,
        capacity=body.capacity,
        price_month=course.default_price_month if body.price_month is None else body.price_month,
        status=st.status_for(body.start_date, body.end_date, st.today()),
    )
    db.add(cohort)
    await db.flush()
    await st.sync_status(db, cohort, p.id)
    count = await generate_lessons(db, cohort)
    await record(
        db,
        p.id,
        "cohort.create",
        "cohort",
        cohort.id,
        {**diff_of({}, _snapshot(cohort)), "lessons": [0, count]},
        branch_id=cohort.branch_id,
    )
    return await _detail(db, cohort.id)


@router.get("/cohorts/{cohort_id}")
async def get_cohort(cohort_id: uuid.UUID, p: View, db: DB) -> dict[str, Any]:
    cohort = await _load(db, p, cohort_id)
    return await _detail(db, cohort.id)


_SCHEDULE_FIELDS = ("start_date", "end_date", "weekdays", "start_time", "end_time", "room_id")


@router.patch("/cohorts/{cohort_id}")
async def update_cohort(
    cohort_id: uuid.UUID, body: CohortUpdate, version: Version, p: Change, db: DB
) -> dict[str, Any]:
    cohort = await _load(db, p, cohort_id)
    await check_version(db, cohort, version, "cohort", lambda: _detail(db, cohort.id))
    if cohort.status == st.CANCELLED:
        raise DomainError(COHORT_CLOSED)
    before = _snapshot(cohort)
    sent = body.model_fields_set
    schedule_before = {f: getattr(cohort, f) for f in _SCHEDULE_FIELDS}
    for field in ("start_date", "end_date", "capacity"):
        if field in sent and getattr(body, field) is not None:
            setattr(cohort, field, getattr(body, field))
    if "weekdays" in sent and body.weekdays is not None:
        cohort.weekdays = sorted(set(body.weekdays))
    if "start_time" in sent and body.start_time is not None:
        cohort.start_time = _minute(body.start_time)
    if "end_time" in sent and body.end_time is not None:
        cohort.end_time = _minute(body.end_time)
    if "price_month" in sent and body.price_month is not None:
        cohort.price_month = body.price_month
    if schedule_problem(
        cohort.start_date, cohort.end_date, cohort.weekdays, cohort.start_time, cohort.end_time
    ):
        raise DomainError(VALIDATION_FAILED)
    if cohort.capacity < (await cohort_enrolled(db, [cohort.id]))[cohort.id]:
        raise DomainError(COHORT_FULL)
    if "room_id" in sent and body.room_id is not None:
        await _room_in_branch(db, p, body.room_id, cohort.branch_id)
        cohort.room_id = body.room_id
    if "instructor_id" in sent and body.instructor_id != cohort.instructor_id:
        await _check_instructor(db, body.instructor_id, cohort.branch_id)
        cohort.instructor_id = body.instructor_id
    lessons_note: list[int] | None = None
    if {f: getattr(cohort, f) for f in _SCHEDULE_FIELDS} != schedule_before:
        # Past lessons stay, and so does any lesson with marks; the rest ahead is rebuilt.
        now = _now()
        removed = (
            await db.execute(
                delete(Lesson).where(
                    Lesson.cohort_id == cohort.id,
                    Lesson.starts_at > now,
                    Lesson.source == "generated",
                    ~has_marks(),
                )
            )
        ).rowcount  # type: ignore[attr-defined]
        await db.flush()
        lessons_note = [removed, await generate_lessons(db, cohort, after=now)]
    await st.sync_status(db, cohort, p.id)
    cohort.updated_at = _now()
    await db.flush()
    diff = diff_of(before, _snapshot(cohort))
    if lessons_note:
        diff["future_lessons"] = lessons_note
    await record(db, p.id, "cohort.update", "cohort", cohort.id, diff, branch_id=cohort.branch_id)
    return await _detail(db, cohort.id)


@router.post("/cohorts/{cohort_id}/cancel")
async def cancel_cohort(cohort_id: uuid.UUID, p: Change, db: DB) -> dict[str, Any]:
    """«Отменён» is manual and sticky; the lessons still ahead are cancelled with it."""
    cohort = await _load(db, p, cohort_id)
    if cohort.status == st.CANCELLED:
        raise DomainError(COHORT_CLOSED)
    before = cohort.status
    cohort.status = st.CANCELLED
    cohort.updated_at = _now()
    cancelled = (
        await db.execute(
            update(Lesson)
            .where(Lesson.cohort_id == cohort.id, Lesson.starts_at > _now(), ~Lesson.cancelled)
            .values(cancelled=True)
        )
    ).rowcount  # type: ignore[attr-defined]
    await record(
        db,
        p.id,
        "cohort.cancel",
        "cohort",
        cohort.id,
        {"status": [before, st.CANCELLED], "lessons_cancelled": [0, cancelled]},
        branch_id=cohort.branch_id,
    )
    return await _detail(db, cohort.id)


@router.post("/cohorts/{cohort_id}/restore")
async def restore_cohort(cohort_id: uuid.UUID, p: Change, db: DB) -> dict[str, Any]:
    cohort = await _load(db, p, cohort_id)
    if cohort.status != st.CANCELLED:
        raise DomainError(COHORT_NOT_CANCELLED)
    now = _now()
    await db.execute(
        delete(Lesson).where(
            Lesson.cohort_id == cohort.id,
            Lesson.starts_at > now,
            Lesson.source == "generated",
            ~has_marks(),
        )
    )
    await db.flush()
    cohort.status = st.status_for(cohort.start_date, cohort.end_date, st.today())
    await generate_lessons(db, cohort, after=now)
    await st.sync_status(db, cohort, p.id)
    cohort.updated_at = now
    await record(
        db,
        p.id,
        "cohort.restore",
        "cohort",
        cohort.id,
        {"status": [st.CANCELLED, cohort.status]},
        branch_id=cohort.branch_id,
    )
    return await _detail(db, cohort.id)


@router.delete("/cohorts/{cohort_id}", status_code=204)
async def delete_cohort(cohort_id: uuid.UUID, p: Change, db: DB) -> None:
    cohort = await _load(db, p, cohort_id)
    snapshot, branch_id = _snapshot(cohort), cohort.branch_id
    try:
        async with db.begin_nested():
            await db.delete(cohort)
            await db.flush()
    except IntegrityError as exc:
        raise DomainError(COHORT_IN_USE) from exc
    await record(
        db, p.id, "cohort.delete", "cohort", cohort_id, diff_of(snapshot, {}), branch_id=branch_id
    )


# ---- lessons -----------------------------------------------------------------------------


def _lesson_out(le: Lesson, room: str) -> dict[str, Any]:
    return {
        "id": le.id,
        "version": le.version,
        "cohort_id": le.cohort_id,
        "room_id": le.room_id,
        "room_name": room,
        "date": le.lesson_date,
        "start": le.starts_at.astimezone(st.TZ).strftime("%H:%M"),
        "end": le.ends_at.astimezone(st.TZ).strftime("%H:%M"),
        "cancelled": le.cancelled,
        "source": le.source,
    }


async def _lesson_detail(db: AsyncSession, lesson_id: uuid.UUID) -> dict[str, Any]:
    row = (
        await db.execute(
            select(Lesson, Room.name)
            .join(Room, Room.id == Lesson.room_id)
            .where(Lesson.id == lesson_id)
        )
    ).one()
    return _lesson_out(*row)


def _lesson_snapshot(le: Lesson) -> dict[str, Any]:
    return {
        "date": le.lesson_date,
        "start": le.starts_at.astimezone(st.TZ).strftime("%H:%M"),
        "end": le.ends_at.astimezone(st.TZ).strftime("%H:%M"),
        "room_id": le.room_id,
        "cancelled": le.cancelled,
    }


@router.get("/cohorts/{cohort_id}/lessons")
async def list_lessons(cohort_id: uuid.UUID, p: View, db: DB) -> list[dict[str, Any]]:
    cohort = await _load(db, p, cohort_id)
    rows = await db.execute(
        select(Lesson, Room.name)
        .join(Room, Room.id == Lesson.room_id)
        .where(Lesson.cohort_id == cohort.id)
        .order_by(Lesson.starts_at)
    )
    return [_lesson_out(le, room) for le, room in rows.all()]


@router.post("/cohorts/{cohort_id}/lessons", status_code=201)
async def add_lesson(cohort_id: uuid.UUID, body: LessonIn, p: Change, db: DB) -> dict[str, Any]:
    cohort = await _load(db, p, cohort_id)
    if cohort.status in (st.CANCELLED, st.DONE):
        raise DomainError(COHORT_CLOSED)
    room_id = body.room_id or cohort.room_id
    await _room_in_branch(db, p, room_id, cohort.branch_id)
    starts, ends = local_dt(body.date, body.start_time), local_dt(body.date, body.end_time)
    await check_room_free(db, room_id, [(starts, ends)])
    lesson = Lesson(
        cohort_id=cohort.id,
        room_id=room_id,
        lesson_date=body.date,
        starts_at=starts,
        ends_at=ends,
        source="manual",
    )
    db.add(lesson)
    await db.flush()
    await record(
        db,
        p.id,
        "lesson.create",
        "lesson",
        lesson.id,
        diff_of({}, {"cohort": cohort.code, **_lesson_snapshot(lesson)}),
        branch_id=cohort.branch_id,
    )
    return await _lesson_detail(db, lesson.id)


async def _lesson(db: AsyncSession, p: Principal, lesson_id: uuid.UUID) -> tuple[Lesson, Cohort]:
    row = (
        await db.execute(
            select(Lesson, Cohort)
            .join(Cohort, Cohort.id == Lesson.cohort_id)
            .where(Lesson.id == lesson_id)
        )
    ).first()
    if row is None:
        raise DomainError(NOT_FOUND)
    check_cohort_visible(p, row[1])
    return row[0], row[1]


@router.patch("/lessons/{lesson_id}")
async def move_lesson(
    lesson_id: uuid.UUID, body: LessonMove, version: Version, p: Change, db: DB
) -> dict[str, Any]:
    lesson, cohort = await _lesson(db, p, lesson_id)
    await check_version(db, lesson, version, "lesson", lambda: _lesson_detail(db, lesson.id))
    if lesson.cancelled:
        raise DomainError(LESSON_CANCELLED)
    if cohort.status == st.CANCELLED:
        raise DomainError(COHORT_CLOSED)
    before = _lesson_snapshot(lesson)
    day = body.date or lesson.lesson_date
    start = body.start_time or lesson.starts_at.astimezone(st.TZ).time()
    end = body.end_time or lesson.ends_at.astimezone(st.TZ).time()
    start, end = _minute(start), _minute(end)
    if window_problem(start, end) or not MIN_DATE <= day <= MAX_DATE:
        raise DomainError(VALIDATION_FAILED)
    room_id = body.room_id or lesson.room_id
    await _room_in_branch(db, p, room_id, cohort.branch_id)
    starts, ends = local_dt(day, start), local_dt(day, end)
    await check_room_free(db, room_id, [(starts, ends)], ignore_lesson=lesson.id)
    lesson.source = "manual"  # a moved lesson is no longer the schedule's to rebuild
    lesson.room_id, lesson.lesson_date, lesson.starts_at, lesson.ends_at = (
        room_id,
        day,
        starts,
        ends,
    )
    await db.flush()
    await record(
        db,
        p.id,
        "lesson.move",
        "lesson",
        lesson.id,
        diff_of(before, _lesson_snapshot(lesson)),
        branch_id=cohort.branch_id,
    )
    return await _lesson_detail(db, lesson.id)


@router.post("/lessons/{lesson_id}/cancel")
async def cancel_lesson(lesson_id: uuid.UUID, p: Change, db: DB) -> dict[str, Any]:
    lesson, cohort = await _lesson(db, p, lesson_id)
    if lesson.cancelled:
        raise DomainError(LESSON_CANCELLED)
    lesson.cancelled = True
    await db.flush()
    await record(
        db,
        p.id,
        "lesson.cancel",
        "lesson",
        lesson.id,
        {"cancelled": [False, True], "date": [None, lesson.lesson_date]},
        branch_id=cohort.branch_id,
    )
    return await _lesson_detail(db, lesson.id)


# ---- enrollments -------------------------------------------------------------------------


def _enrollment_out(e: Enrollment, s: Student) -> dict[str, Any]:
    return {
        "id": e.id,
        "version": e.version,
        "cohort_id": e.cohort_id,
        "student_id": s.id,
        "student_name": s.full_name,
        "phone": s.phone,
        "status": e.status,
        "enrolled_at": e.enrolled_at,
    }


@router.get("/cohorts/{cohort_id}/enrollments")
async def list_enrollments(cohort_id: uuid.UUID, p: View, db: DB) -> list[dict[str, Any]]:
    cohort = await _load(db, p, cohort_id)
    rows = await db.execute(
        select(Enrollment, Student)
        .join(Student, Student.id == Enrollment.student_id)
        .where(Enrollment.cohort_id == cohort.id)
        .order_by(Student.full_name, Enrollment.id)
    )
    return [_enrollment_out(e, s) for e, s in rows.all()]


@router.post("/cohorts/{cohort_id}/enrollments", status_code=201)
async def enroll(cohort_id: uuid.UUID, body: EnrollIn, p: Change, db: DB) -> dict[str, Any]:
    if body.new_student is not None and not allows(p.level("students"), "change"):
        raise DomainError(FORBIDDEN, section="students", level="change")
    cohort = await _load(db, p, cohort_id, lock=True)
    if cohort.status in (st.CANCELLED, st.DONE):
        raise DomainError(COHORT_CLOSED)
    if (await cohort_enrolled(db, [cohort.id]))[cohort.id] >= cohort.capacity:
        raise DomainError(COHORT_FULL)
    if body.new_student is not None:
        student = Student(
            full_name=body.new_student.full_name,
            phone=body.new_student.phone or None,
            gender=body.new_student.gender,
            branch_id=cohort.branch_id,
        )
        db.add(student)
        await db.flush()
        await record(
            db,
            p.id,
            "student.create",
            "student",
            student.id,
            diff_of({}, {"full_name": student.full_name, "phone": student.phone}),
            branch_id=student.branch_id,
        )
    else:
        found = (
            await db.execute(select(Student).where(Student.id == body.student_id))
        ).scalar_one_or_none()
        if found is None:
            raise DomainError(NOT_FOUND)
        p.check_scope(found.branch_id)
        if found.branch_id != cohort.branch_id:
            raise DomainError(STUDENT_BRANCH_MISMATCH)
        student = found
    enrollment = Enrollment(cohort_id=cohort.id, student_id=student.id)
    db.add(enrollment)
    await db.flush()  # unique(cohort_id, student_id): a second enrollment is a 409 (#4)
    await record(
        db,
        p.id,
        "enrollment.create",
        "enrollment",
        enrollment.id,
        {
            "cohort": [None, cohort.code],
            "student": [None, student.full_name],
            "status": [None, enrollment.status],
        },
        branch_id=cohort.branch_id,
    )
    return _enrollment_out(enrollment, student)


async def _enrollment(
    db: AsyncSession, p: Principal, enrollment_id: uuid.UUID
) -> tuple[Enrollment, Student, Cohort]:
    row = (
        await db.execute(
            select(Enrollment, Student, Cohort)
            .join(Student, Student.id == Enrollment.student_id)
            .join(Cohort, Cohort.id == Enrollment.cohort_id)
            .where(Enrollment.id == enrollment_id)
        )
    ).first()
    if row is None:
        raise DomainError(NOT_FOUND)
    check_cohort_visible(p, row[2])
    return row[0], row[1], row[2]


@router.patch("/enrollments/{enrollment_id}")
async def set_enrollment_status(
    enrollment_id: uuid.UUID, body: EnrollmentStatus, version: Version, p: Change, db: DB
) -> dict[str, Any]:
    enrollment, student, cohort = await _enrollment(db, p, enrollment_id)
    await check_version(
        db, enrollment, version, "enrollment", lambda: _enrollment_out(enrollment, student)
    )
    if body.status == "активный" and cohort.status in (st.CANCELLED, st.DONE):
        raise DomainError(COHORT_CLOSED)  # #11: a finished cohort has no active students
    before = enrollment.status
    enrollment.status = body.status
    await db.flush()
    await record(
        db,
        p.id,
        "enrollment.update",
        "enrollment",
        enrollment.id,
        {"status": [before, body.status], "cohort": [None, cohort.code]},
        branch_id=cohort.branch_id,
    )
    return _enrollment_out(enrollment, student)


@router.delete("/enrollments/{enrollment_id}", status_code=204)
async def remove_enrollment(enrollment_id: uuid.UUID, p: Change, db: DB) -> None:
    enrollment, student, cohort = await _enrollment(db, p, enrollment_id)
    await db.delete(enrollment)
    await db.flush()
    await record(
        db,
        p.id,
        "enrollment.delete",
        "enrollment",
        enrollment_id,
        {"cohort": [cohort.code, None], "student": [student.full_name, None]},
        branch_id=cohort.branch_id,
    )
