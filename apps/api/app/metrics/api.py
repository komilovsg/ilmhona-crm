"""`GET /api/v1/metrics/education`: the education numbers for the user's scope."""

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.auth.deps import Principal, require, require_csrf_header
from app.core.db import DB
from app.core.errors import FORBIDDEN, DomainError
from app.education.scope import cohort_filters, is_instructor, require_any, student_filters
from app.leads.query import lead_where
from app.leads.scope import LeadReader, campaign_filters
from app.metrics import education_summary
from app.metrics.money import finance
from app.metrics.sales import callbacks_today, funnel, needs_review_count

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
    p: Annotated[Principal, require("dashboard", "view")],
    db: DB,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """Income = confirmed payments, payroll = payouts made, ads = budgets of the campaigns that
    started in the period, profit = income − ads − payroll (#9). No period = everything."""
    if is_instructor(p):
        raise DomainError(FORBIDDEN, section="dashboard", level="view")
    return await finance(db, cohort_filters(p), campaign_filters(p), date_from, date_to)


@router.get("/leads")
async def leads_summary(
    p: LeadReader,
    db: DB,
    q: str | None = None,
    call_status: str | None = None,
    source: str | None = None,
    course_id: uuid.UUID | None = None,
    campaign_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    needs_review: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """The funnel (lead counts by status) and the conversion % of the same selection the lead
    list shows, without its status filter; plus the callbacks due today and the leads to check."""
    where = lead_where(
        p, q=q, call_status=call_status, source=source, course_id=course_id,
        campaign_id=campaign_id, branch_id=branch_id, needs_review=needs_review,
        date_from=date_from, date_to=date_to,
    )  # fmt: skip
    scope = lead_where(p, branch_id=branch_id, course_id=course_id, campaign_id=campaign_id)
    return {
        **await funnel(db, where),
        "callbacks_today": await callbacks_today(db, scope),
        "needs_review": await needs_review_count(db, scope),
    }
