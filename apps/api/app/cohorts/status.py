"""Cohort status by dates (#20) and the enrollment cascade (#11): the one code path.

набор before start, активный from start to end_date inclusive, завершён after. «отменён» is set
by hand only and sticky. Every write of a cohort and the daily job (`python -m app.cli daily`)
call `sync_status`; when a cohort becomes завершён its активный enrollments become выпускник
(total ≥ 70) or завершил.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import record
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
    return datetime.now(TZ).date()


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
    """#11 + grades: an active enrollment closes as выпускник when its total is at least 70,
    otherwise as завершил. A manager may still correct a status by hand afterwards."""
    active = (
        (
            await db.execute(
                select(Enrollment).where(
                    Enrollment.cohort_id == cohort.id, Enrollment.status == ACTIVE
                )
            )
        )
        .scalars()
        .all()
    )
    if not active:
        return
    results = await enrollment_results(db, cohort.id, enrollment_ids=[e.id for e in active])
    graduates = 0
    for enrollment in active:
        graduated = results[enrollment.id]["passed"]
        enrollment.status = GRADUATE if graduated else COMPLETED
        graduates += graduated
    await db.flush()
    await record(
        db,
        actor_id,  # type: ignore[arg-type]
        "cohort.close_enrollments",
        "cohort",
        cohort.id,
        {"enrollments_completed": [0, len(active)], "graduates": [0, graduates]},
        branch_id=cohort.branch_id,
    )
