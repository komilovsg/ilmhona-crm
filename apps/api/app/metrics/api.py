"""`GET /api/v1/metrics/education`: the education numbers for the user's scope."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.auth.deps import Principal, require, require_csrf_header
from app.core.db import DB
from app.core.errors import FORBIDDEN, DomainError
from app.education.scope import cohort_filters, is_instructor, require_any, student_filters
from app.metrics import education_summary
from app.metrics.money import finance

router = APIRouter(
    prefix="/api/v1/metrics", tags=["metrics"], dependencies=[Depends(require_csrf_header)]
)


@router.get("/education")
async def education(
    p: Annotated[Principal, require_any("cohorts", "students")], db: DB
) -> dict[str, Any]:
    return await education_summary(db, cohort_filters(p), student_filters(p))


@router.get("/finance")
async def finance_summary(
    p: Annotated[Principal, require("dashboard", "view")], db: DB
) -> dict[str, Any]:
    """Income = confirmed payments, payroll = payouts made, ads (0 until stage 3), profit (#9)."""
    if is_instructor(p):
        raise DomainError(FORBIDDEN, section="dashboard", level="view")
    return await finance(db, cohort_filters(p))
