"""Stale cohorts: an активный cohort with no attendance marks for `stale_days` (a setting, 60 by
default) is flagged, and closed by the nightly job when `stale_auto_close` is on (off by default).
One definition for the job, the warning on the cohort, the dashboard alert and the list filter, so
they can never disagree.

The clock of a cohort starts on the date of its last marked lesson, or on its start date when
nothing was ever marked. Idle days = today - that date. With auto-close on, closed at `stale_days`
idle days; the warning shows from `stale_days - WARN_DAYS` and names the closing date. With it off
nothing is closed: the warning shows from `stale_days - WARN_DAYS` on and never names a date.
"""

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import ColumnElement, Date, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.models import AcademySettings, Attendance, Cohort, Lesson

WARN_DAYS = 15
ACTIVE = "активный"


# the setting as a SQL value, so a list of cohorts needs no query of its own for it
DAYS = select(AcademySettings.stale_days).scalar_subquery()
AUTO = select(AcademySettings.stale_auto_close).scalar_subquery()


async def stale_days(db: AsyncSession) -> int:
    return int(await db.scalar(select(AcademySettings.stale_days)) or 60)


async def auto_close_on(db: AsyncSession) -> bool:
    return bool(await db.scalar(select(AcademySettings.stale_auto_close)))


def clock_start() -> ColumnElement[date]:
    """The date the idle clock of `Cohort` runs from (correlated to the cohort row)."""
    last_mark = (
        select(func.max(Lesson.lesson_date))
        .select_from(Lesson)
        .join(Attendance, Attendance.lesson_id == Lesson.id)
        .where(Lesson.cohort_id == Cohort.id)
        .correlate(Cohort)
        .scalar_subquery()
    )
    return func.coalesce(last_mark, Cohort.start_date)


def due_clause(days: Any, on: date) -> ColumnElement[bool]:
    """An активный cohort idle for `days` days or more (an int or `DAYS`)."""
    return and_(Cohort.status == ACTIVE, clock_start() <= cast(on, Date) - days)


def warning_clause(days: Any, on: date) -> ColumnElement[bool]:
    """An активный cohort in the last WARN_DAYS before it is closed; with auto-close off, any
    активный cohort that long without marks."""
    return and_(
        Cohort.status == ACTIVE,
        clock_start() <= cast(on, Date) - (days - WARN_DAYS),
        or_(AUTO.is_(False), clock_start() > cast(on, Date) - days),
    )


async def closing_soon(
    db: AsyncSession,
    cohort_where: list[ColumnElement[bool]],
    on: date | None = None,
) -> list[dict[str, Any]]:
    """Cohorts in the warning window: idle days and the closing date. Closest to closing first."""
    on = on or clock.today()
    start = clock_start()
    rows = await db.execute(
        select(Cohort.id, Cohort.code, start, DAYS, AUTO)
        .where(*cohort_where, warning_clause(DAYS, on))
        .order_by(start, Cohort.code)
    )
    return [
        {
            "cohort_id": i,
            "cohort_code": c,
            "idle_days": (on - s).days,
            "closes_on": s + timedelta(days=int(days)) if auto else None,
        }
        for i, c, s, days, auto in rows
    ]


async def warnings_for(
    db: AsyncSession, ids: list[uuid.UUID], on: date | None = None
) -> dict[uuid.UUID, dict[str, Any]]:
    if not ids:
        return {}
    items = await closing_soon(db, [Cohort.id.in_(ids)], on)
    return {
        i["cohort_id"]: {"idle_days": i["idle_days"], "closes_on": i["closes_on"]} for i in items
    }


async def due_cohorts(db: AsyncSession, on: date | None = None) -> tuple[int, list[Cohort]]:
    """(stale_days, the cohorts the nightly job closes), by code."""
    on = on or clock.today()
    days = await stale_days(db)
    rows = await db.execute(select(Cohort).where(due_clause(days, on)).order_by(Cohort.code))
    return days, list(rows.scalars())
