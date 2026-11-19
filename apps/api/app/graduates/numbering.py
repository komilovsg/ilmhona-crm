"""The certificate number: CERT-YYYY-NNNN from `certificate_no_seq`, kept on the enrollment.

The one numbering there is. A graduate is numbered by the graduates screen or by the issue of a
certificate; a non-graduate only through the issue path the settings switch opens
(`graduate_only=False`).
"""

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.cohorts.status import GRADUATE
from app.core.errors import DomainError
from app.graduates.errors import NOT_GRADUATE
from app.models import Enrollment


async def assign_number(
    db: AsyncSession, enrollment: Enrollment, *, graduate_only: bool = True
) -> bool:
    """Number the enrollment if it has no number yet (True), keep it if it has (False). The row
    must be locked by the caller."""
    if graduate_only and enrollment.status != GRADUATE:
        raise DomainError(NOT_GRADUATE)
    if enrollment.certificate_no:
        return False
    now = datetime.now(UTC)
    n = (await db.execute(text("SELECT nextval('certificate_no_seq')"))).scalar_one()
    enrollment.certificate_non_graduate = enrollment.status != GRADUATE
    enrollment.certificate_no = f"CERT-{now.year}-{n:04d}"
    enrollment.certificate_issued_at = now
    await db.flush()
    return True
