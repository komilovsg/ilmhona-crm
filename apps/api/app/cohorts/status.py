"""Cohort status by dates (#20) and the enrollment cascade (#11): the one code path.

набор before start, активный from start to end_date inclusive, завершён after. «отменён» is set
by hand only and sticky. Every write of a cohort and the daily job (`python -m app.cli daily`)
call `sync_status`; when a cohort becomes завершён its активный enrollments become завершил.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import record
from app.models import Cohort, Enrollment

TZ = ZoneInfo("Asia/Dushanbe")

RECRUITING = "набор"
ACTIVE = "активный"
DONE = "завершён"
CANCELLED = "отменён"
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
        closed = (
            await db.execute(
                update(Enrollment)
                .where(Enrollment.cohort_id == cohort.id, Enrollment.status == ACTIVE)
                .values(status="завершил")
            )
        ).rowcount  # type: ignore[attr-defined]
        if closed:
            await record(
                db,
                actor_id,  # type: ignore[arg-type]
                "cohort.close_enrollments",
                "cohort",
                cohort.id,
                {"enrollments_completed": [0, closed]},
                branch_id=cohort.branch_id,
            )
    return changed
