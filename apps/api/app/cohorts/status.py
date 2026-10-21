"""Cohort status by dates (#20) and the enrollment cascade (#11): the one code path.

набор before start, активный from start to end_date inclusive, завершён after. «отменён» is set
by hand only and sticky. Every write of a cohort and the daily job (`python -m app.cli daily`)
call `sync_status`; when a cohort becomes завершён its активный enrollments become выпускник
(total ≥ 70) or завершил.
"""

import uuid
from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import record
from app.core import clock
from app.metrics import enrollment_results
from app.models import Cohort, Enrollment

TZ = ZoneInfo("Asia/Dushanbe")

RECRUITING = "набор"
ACTIVE = "активный"
DONE = "завершён"
CANCELLED = "отменён"
GRADUATE = "выпускник"
COMPLETED = "завершил"
STATUSES = (RECRUITING, ACTIVE, DONE, CANCELLED)


def today() -> date:
    return clock.today()


def status_for(start: date, end: date, on: date) -> str:
    if on < start:
        return RECRUITING
    if on <= end:
        return ACTIVE
    return DONE


async def sync_status(
    db: AsyncSession, cohort: Cohort, actor_id: object, on: date | None = None
) -> bool:
    """Bring the status (and the enrollments of a finished cohort) in line with the dates.
    True when the status changed. The caller audits the cohort itself; the cascade audits here."""
    if cohort.status == CANCELLED:
        return False
    new = status_for(cohort.start_date, cohort.end_date, on or today())
    changed = new != cohort.status
    if changed:
        cohort.status = new
    if new == DONE:
        await _close_enrollments(db, cohort, actor_id)
    return changed


async def _close_enrollments(db: AsyncSession, cohort: Cohort, actor_id: object) -> None:
    await close_enrollments(db, [cohort], actor_id)


async def close_enrollments(db: AsyncSession, cohorts: list[Cohort], actor_id: object) -> None:
    """#11 + grades: an active enrollment closes as выпускник when its total is at least 70,
    otherwise as завершил. A manager may still correct a status by hand afterwards. Any number of
    cohorts at once: two queries in all (the import closes ~100 cohorts in one go)."""
    ids = [c.id for c in cohorts]
    active: dict[object, list[Enrollment]] = {}
    for e in (
        (
            await db.execute(
                select(Enrollment).where(Enrollment.cohort_id.in_(ids), Enrollment.status == ACTIVE)
            )
        )
        .scalars()
        .all()
    ):
        active.setdefault(e.cohort_id, []).append(e)
    if not active:
        return
    results = await enrollment_results(
        db, None, enrollment_ids=[e.id for rows in active.values() for e in rows]
    )
    closed: list[tuple[Cohort, int, int]] = []
    for cohort in cohorts:
        graduates = 0
        for enrollment in active.get(cohort.id, []):
            graduated = results[enrollment.id]["passed"]
            enrollment.status = GRADUATE if graduated else COMPLETED
            graduates += graduated
        if cohort.id in active:
            closed.append((cohort, len(active[cohort.id]), graduates))
    await db.flush()
    for cohort, count, graduates in closed:
        await record(
            db,
            actor_id,  # type: ignore[arg-type]
            "cohort.close_enrollments",
            "cohort",
            cohort.id,
            {"enrollments_completed": [0, count], "graduates": [0, graduates]},
            branch_id=cohort.branch_id,
            label=cohort.code,
        )


async def reevaluate(
    db: AsyncSession,
    enrollment: Enrollment,
    cohort: Cohort,
    actor_id: object,
    results: dict[uuid.UUID, dict[str, Any]] | None = None,
) -> bool:
    """A grade changed on a finished cohort: the closed enrollment follows the new total
    (выпускник at ≥ 70, else завершил), unless a manager set the status by hand
    (`status_manual`) or a certificate was already issued. True when the status changed."""
    if (
        cohort.status != DONE
        or enrollment.status_manual
        or enrollment.status not in (GRADUATE, COMPLETED)
    ):
        return False
    if results is None:  # the import passes the results of all its enrollments at once
        results = await enrollment_results(db, cohort.id, enrollment_ids=[enrollment.id])
    result = results[enrollment.id]
    new = GRADUATE if result["passed"] else COMPLETED
    if new == enrollment.status or (enrollment.certificate_no and new != GRADUATE):
        return False
    before, enrollment.status = enrollment.status, new
    await db.flush()
    await record(
        db,
        actor_id,  # type: ignore[arg-type]
        "enrollment.update",
        "enrollment",
        enrollment.id,
        {"status": [before, new], "reason": [None, "пересчёт по оценкам"]},
        branch_id=cohort.branch_id,
    )
    return True
