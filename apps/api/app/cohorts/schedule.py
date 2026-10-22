"""Lessons from a cohort's schedule, and the room / instructor conflict checks that name the other
cohort (#7, and one instructor in one place at a time).

The database (EXCLUDE on room × time and on instructor × time) is the guarantee; the checks here
only exist to tell the user *which* cohort holds the slot. A race that slips past them still ends
as a 409 (room_busy / instructor_busy)."""

import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import exists, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.cohorts.status import TZ
from app.core.errors import DomainError
from app.education.errors import INSTRUCTOR_BUSY, ROOM_BUSY
from app.models import Cohort, Lesson


def local_dt(day: date, at: time) -> datetime:
    """A wall-clock time in Asia/Dushanbe as a timezone-aware datetime."""
    return datetime.combine(day, at, tzinfo=TZ)


def lesson_dates(start: date, end: date, weekdays: list[int]) -> list[date]:
    days = set(weekdays)
    return [
        start + timedelta(days=i)
        for i in range((end - start).days + 1)
        if (start + timedelta(days=i)).isoweekday() in days
    ]


async def check_room_free(
    db: AsyncSession,
    room_id: uuid.UUID,
    windows: list[tuple[datetime, datetime]],
    *,
    ignore_lesson: uuid.UUID | None = None,
) -> None:
    """Raise room_busy (naming the cohort) if any window overlaps a live lesson in the room."""
    if not windows:
        return
    lo = min(s for s, _ in windows)
    hi = max(e for _, e in windows)
    query = (
        select(Lesson, Cohort.code)
        .join(Cohort, Cohort.id == Lesson.cohort_id)
        .where(
            Lesson.room_id == room_id,
            ~Lesson.cancelled,
            Lesson.starts_at < hi,
            Lesson.ends_at > lo,
        )
    )
    if ignore_lesson:
        query = query.where(Lesson.id != ignore_lesson)
    for lesson, code in (await db.execute(query)).all():
        for start, end in windows:
            if lesson.starts_at < end and lesson.ends_at > start:
                raise DomainError(
                    ROOM_BUSY,
                    cohort=code,
                    date=lesson.starts_at.astimezone(TZ).date().isoformat(),
                    start=lesson.starts_at.astimezone(TZ).strftime("%H:%M"),
                    end=lesson.ends_at.astimezone(TZ).strftime("%H:%M"),
                )


def _when(lesson: Lesson) -> dict[str, str]:
    return {
        "date": lesson.starts_at.astimezone(TZ).date().isoformat(),
        "start": lesson.starts_at.astimezone(TZ).strftime("%H:%M"),
        "end": lesson.ends_at.astimezone(TZ).strftime("%H:%M"),
    }


async def check_instructor_free(
    db: AsyncSession,
    instructor_id: uuid.UUID | None,
    windows: list[tuple[datetime, datetime]],
    *,
    branch_id: uuid.UUID,
    ignore_lesson: uuid.UUID | None = None,
) -> None:
    """Raise instructor_busy if any window overlaps a live lesson of the instructor. A cohort of
    another branch is not named (only «другого филиала»). Lessons marked as an old conflict count
    too: nothing new may overlap them."""
    if instructor_id is None or not windows:
        return
    lo = min(s for s, _ in windows)
    hi = max(e for _, e in windows)
    query = (
        select(Lesson, Cohort.code, Cohort.branch_id)
        .join(Cohort, Cohort.id == Lesson.cohort_id)
        .where(
            Lesson.instructor_id == instructor_id,
            ~Lesson.cancelled,
            Lesson.starts_at < hi,
            Lesson.ends_at > lo,
        )
        .order_by(Lesson.starts_at)
    )
    if ignore_lesson:
        query = query.where(Lesson.id != ignore_lesson)
    for lesson, code, other_branch in (await db.execute(query)).all():
        for start, end in windows:
            if lesson.starts_at < end and lesson.ends_at > start:
                who = code if other_branch == branch_id else "другого филиала"
                raise DomainError(INSTRUCTOR_BUSY, cohort=who, **_when(lesson))


async def reassign_instructor(db: AsyncSession, cohort: Cohort, *, after: datetime) -> None:
    """The cohort's lessons ahead (starting after `after`) go to its (new) instructor; the ones
    held already keep who taught them. Raises instructor_busy when the new one is taken."""
    ahead = (
        await db.execute(
            select(Lesson.starts_at, Lesson.ends_at).where(
                Lesson.cohort_id == cohort.id, Lesson.starts_at > after, ~Lesson.cancelled
            )
        )
    ).all()
    await check_instructor_free(
        db, cohort.instructor_id, [(s, e) for s, e in ahead], branch_id=cohort.branch_id
    )
    await db.execute(
        update(Lesson)
        .where(Lesson.cohort_id == cohort.id, Lesson.starts_at > after)
        .values(instructor_id=cohort.instructor_id, instructor_conflict=False)
    )


async def settle_conflicts(db: AsyncSession, instructor_ids: set[uuid.UUID | None]) -> None:
    """Clear the «конфликт инструктора» mark on the instructors' lessons that no longer overlap a
    live lesson of theirs (moved, cancelled, reassigned)."""
    ids = [i for i in instructor_ids if i is not None]
    if not ids:
        return
    other = aliased(Lesson)
    overlap = exists().where(
        other.instructor_id == Lesson.instructor_id,
        other.id != Lesson.id,
        ~other.cancelled,
        other.starts_at < Lesson.ends_at,
        other.ends_at > Lesson.starts_at,
    )
    await db.execute(
        update(Lesson)
        .where(
            Lesson.instructor_conflict,
            Lesson.instructor_id.in_(ids),
            or_(Lesson.cancelled, ~overlap),
        )
        .values(instructor_conflict=False)
        .execution_options(synchronize_session="fetch")
    )


async def generate_lessons(
    db: AsyncSession, cohort: Cohort, *, after: datetime | None = None
) -> int:
    """Insert the cohort's lessons (only those starting after `after`, when given). Returns how
    many. Raises room_busy / instructor_busy when the room or the instructor is taken."""
    # a lesson that survived a rebuild (it has marks) is already there: no second one on its slot
    kept = set(
        (await db.execute(select(Lesson.starts_at).where(Lesson.cohort_id == cohort.id)))
        .scalars()
        .all()
    )
    rows = []
    for day in lesson_dates(cohort.start_date, cohort.end_date, cohort.weekdays):
        starts, ends = local_dt(day, cohort.start_time), local_dt(day, cohort.end_time)
        if (after is None or starts > after) and starts not in kept:
            rows.append((day, starts, ends))
    windows = [(s, e) for _, s, e in rows]
    await check_room_free(db, cohort.room_id, windows)
    await check_instructor_free(db, cohort.instructor_id, windows, branch_id=cohort.branch_id)
    db.add_all(
        Lesson(
            cohort_id=cohort.id,
            room_id=cohort.room_id,
            instructor_id=cohort.instructor_id,
            lesson_date=day,
            starts_at=starts,
            ends_at=ends,
        )
        for day, starts, ends in rows
    )
    await db.flush()
    return len(rows)
