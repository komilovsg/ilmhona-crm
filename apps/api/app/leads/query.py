"""The one `where` of the lead list: the screen, the funnel numbers and the Excel export all
build their selection here, so they can never disagree."""

import re
import uuid
from datetime import date
from typing import Any

from sqlalchemy import ColumnElement, func, or_

from app.auth.deps import Principal
from app.leads.scope import lead_filters
from app.metrics.sales import callback_filter, lead_period
from app.models import Lead


def like(q: str) -> str:
    return f"%{q.strip().replace('%', r'\%').replace('_', r'\_')}%"


def lead_where(
    p: Principal,
    *,
    q: str | None = None,
    status: str | None = None,
    call_status: str | None = None,
    source: str | None = None,
    course_id: uuid.UUID | None = None,
    campaign_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    needs_review: bool | None = None,
    callback: bool = False,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[Any]:
    where: list[ColumnElement[bool]] = list(lead_filters(p))
    if branch_id:
        where.append(Lead.branch_id == branch_id)
    if status:
        where.append(Lead.status == status)
    if call_status:
        where.append(Lead.call_status == call_status)
    if source:
        where.append(Lead.source == source)
    if course_id:
        where.append(Lead.course_id == course_id)
    if campaign_id:
        where.append(Lead.campaign_id == campaign_id)
    if needs_review:
        where.append(Lead.needs_review.is_(True))
    if callback:
        where.extend(callback_filter())
    where.extend(lead_period(date_from, date_to))
    if q and q.strip():
        terms = [Lead.full_name.ilike(like(q)), Lead.raw_name.ilike(like(q))]
        digits = re.sub(r"\D", "", q)
        if len(digits) >= 3:  # a phone typed in any form: +992 90 123…, (90) 123…
            terms.append(func.regexp_replace(Lead.phone, r"\D", "", "g").like(f"%{digits}%"))
        where.append(or_(*terms))
    return where
