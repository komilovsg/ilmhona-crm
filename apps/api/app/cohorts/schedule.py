"""Lessons from a cohort's schedule, and the room-conflict check that names the other cohort (#7).

The database (EXCLUDE on room × time) is the guarantee; `check_room_free` only exists to tell the
user *which* cohort holds the room. A race that slips past it still ends as a 409 (room_busy)."""

import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cohorts.status import TZ
from app.core.errors import DomainError
from app.education.errors import ROOM_BUSY
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


async def generate_lessons(
    db: AsyncSession, cohort: Cohort, *, after: datetime | None = None
) -> int:
    """Insert the cohort's lessons (only those starting after `after`, when given). Returns how
    many. Raises room_busy when the room is taken."""
    rows = []
    for day in lesson_dates(cohort.start_date, cohort.end_date, cohort.weekdays):
        starts, ends = local_dt(day, cohort.start_time), local_dt(day, cohort.end_time)
        if after is None or starts > after:
            rows.append((day, starts, ends))
    await check_room_free(db, cohort.room_id, [(s, e) for _, s, e in rows])
    db.add_all(
        Lesson(
            cohort_id=cohort.id,
            room_id=cohort.room_id,
            lesson_date=day,
            starts_at=starts,
            ends_at=ends,
        )
        for day, starts, ends in rows
    )
    await db.flush()
    return len(rows)
