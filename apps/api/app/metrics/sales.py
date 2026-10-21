"""Sales numbers (SPEC «Метрики»): the one place that counts leads and campaigns.

- converted = leads with status «записан» (set only by converting the lead into a student);
  enrolled = converted leads whose student has an enrollment that is not «отчислен».
- Funnel = lead counts by status for a period (by the day the lead was created, Dushanbe time);
  conversion % = converted / all leads of the same selection (0 when there are none).
- CPL = campaign budget ÷ leads of the campaign; CAC = budget ÷ converted. Both are None («—»)
  when the divisor is 0: never a division error, never a fake 0.
- Ads (реклама, `money.ads_total`) = budgets of the campaigns that started in the period; it
  feeds the profit.
- «Перезвонить сегодня» = call status «перезвонить» and next contact up to the end of today.
"""

import uuid
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.metrics.money import TZ, ZERO, money, today
from app.models import Campaign, Enrollment, Lead

LEAD_STATUSES = ("новый", "заинтересован", "нулевой урок", "записан", "отказ")
CALL_STATUSES = ("не звонили", "не ответил", "позвонили", "перезвонить")
CONVERTED = "записан"
CALLBACK = "перезвонить"
TOTAL = "всего"


def _start_of(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=TZ)


def lead_period(date_from: date | None, date_to: date | None) -> list[ColumnElement[bool]]:
    """Leads created from the start of `date_from` to the end of `date_to` (Dushanbe days)."""
    where: list[ColumnElement[bool]] = []
    if date_from:
        where.append(Lead.created_at >= _start_of(date_from))
    if date_to:
        where.append(Lead.created_at < _start_of(date_to + timedelta(days=1)))
    return where


def end_of_today() -> datetime:
    return _start_of(today() + timedelta(days=1))


def callback_filter() -> list[ColumnElement[bool]]:
    return [Lead.call_status == CALLBACK, Lead.next_contact_at < end_of_today()]


def percent(part: int, whole: int) -> float:
    return round(part * 100 / whole, 1) if whole else 0.0


async def funnel(db: AsyncSession, where: Sequence[ColumnElement[bool]]) -> dict[str, Any]:
    """Counts by status (all keys always present), the total and the conversion %."""
    rows = await db.execute(select(Lead.status, func.count()).where(*where).group_by(Lead.status))
    counts = dict.fromkeys(LEAD_STATUSES, 0)
    counts.update({s: n for s, n in rows.all()})
    counts[TOTAL] = sum(counts[s] for s in LEAD_STATUSES)
    return {"counts": counts, "conversion": percent(counts[CONVERTED], counts[TOTAL])}


async def callbacks_today(db: AsyncSession, where: Sequence[ColumnElement[bool]]) -> int:
    return (
        await db.execute(select(func.count()).select_from(Lead).where(*where, *callback_filter()))
    ).scalar_one()


async def needs_review_count(db: AsyncSession, where: Sequence[ColumnElement[bool]]) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(Lead).where(*where, Lead.needs_review.is_(True))
        )
    ).scalar_one()


def ratio(budget: Decimal, divisor: int) -> Decimal | None:
    return money(budget / divisor) if divisor else None


async def campaign_stats(
    db: AsyncSession, campaigns: Sequence[Campaign]
) -> dict[uuid.UUID, dict[str, Any]]:
    """Leads, converted, enrolled, CPL and CAC per campaign (all leads of the campaign)."""
    stats: dict[uuid.UUID, dict[str, Any]] = {}
    for c in campaigns:
        stats[c.id] = {"leads": 0, "converted": 0, "enrolled": 0, "cpl": None, "cac": None}
    if campaigns:
        has_enrollment = exists().where(
            Enrollment.student_id == Lead.converted_student_id, Enrollment.status != "отчислен"
        )
        rows = await db.execute(
            select(
                Lead.campaign_id,
                func.count(),
                func.count().filter(Lead.status == CONVERTED),
                func.count().filter(and_(Lead.status == CONVERTED, has_enrollment)),
            )
            .where(Lead.campaign_id.in_([c.id for c in campaigns]))
            .group_by(Lead.campaign_id)
        )
        for cid, leads, converted, enrolled in rows.all():
            assert cid is not None
            stats[cid].update(leads=leads, converted=converted, enrolled=enrolled)
    for c in campaigns:
        s = stats[c.id]
        s["cpl"], s["cac"] = ratio(c.budget, s["leads"]), ratio(c.budget, s["converted"])
    return stats


def marketing_totals(
    campaigns: Sequence[Campaign], stats: dict[uuid.UUID, dict[str, Any]]
) -> dict[str, Any]:
    """Totals of a campaign list: budget, leads, converted, enrolled, CPL, CAC."""
    budget = money(sum((c.budget for c in campaigns), ZERO))
    leads = sum(s["leads"] for s in stats.values())
    converted = sum(s["converted"] for s in stats.values())
    enrolled = sum(s["enrolled"] for s in stats.values())
    return {
        "campaigns": len(campaigns),
        "budget": budget,
        "leads": leads,
        "converted": converted,
        "enrolled": enrolled,
        "cpl": ratio(budget, leads),
        "cac": ratio(budget, converted),
    }
