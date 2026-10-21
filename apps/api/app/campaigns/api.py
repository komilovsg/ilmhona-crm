"""Campaigns (маркетинг): list with numbers, create, edit, delete, Excel export.

Rights: `marketing` view / change, branch scope; no access for the instructor role. Leads,
converted, enrolled, CPL and CAC come from `app.metrics.sales`, never computed here.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import diff_of, record
from app.auth.deps import Principal, require_csrf_header
from app.core.db import DB
from app.core.errors import NOT_FOUND, DomainError
from app.core.versioning import Version, check_version
from app.education.scope import branch_for_write
from app.export import MAX_ROWS, Col, check_cap, xlsx_response
from app.leads.errors import CAMPAIGN_DATES_INVALID, CAMPAIGN_IN_USE
from app.leads.scope import MarketingReader, MarketingWriter, campaign_filters
from app.metrics.money import money
from app.metrics.sales import campaign_stats, marketing_totals
from app.models import Branch, Campaign, Course

router = APIRouter(
    prefix="/api/v1/campaigns", tags=["campaigns"], dependencies=[Depends(require_csrf_header)]
)

PLATFORMS = ("Facebook Ads", "Instagram", "TikTok", "Telegram", "Google", "офлайн", "другое")
STATUSES = ("запланирована", "активна", "остановлена", "завершена")
Platform = Literal["Facebook Ads", "Instagram", "TikTok", "Telegram", "Google", "офлайн", "другое"]
Status = Literal["запланирована", "активна", "остановлена", "завершена"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Budget = Annotated[Decimal, Field(ge=0, le=Decimal("9999999999.99"), decimal_places=2)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CampaignCreate(Strict):
    name: Name
    course_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    platform: Platform
    start_date: date
    end_date: date | None = None
    budget: Budget = Decimal(0)
    status: Status = "запланирована"


class CampaignUpdate(Strict):
    name: Name | None = None
    course_id: uuid.UUID | None = None
    platform: Platform | None = None
    start_date: date | None = None
    end_date: date | None = None
    budget: Budget | None = None
    status: Status | None = None


def _out(c: Campaign, branch: str, course: str | None, stats: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": c.id,
        "name": c.name,
        "course_id": c.course_id,
        "course_name": course,
        "branch_id": c.branch_id,
        "branch_name": branch,
        "platform": c.platform,
        "start_date": c.start_date,
        "end_date": c.end_date,
        "budget": money(c.budget),
        "status": c.status,
        "version": c.version,
        "created_at": c.created_at,
        **stats,
    }


def _snapshot(c: Campaign) -> dict[str, Any]:
    return {
        "name": c.name,
        "course_id": c.course_id,
        "platform": c.platform,
        "start_date": c.start_date,
        "end_date": c.end_date,
        "budget": c.budget,
        "status": c.status,
    }


def _where(
    p: Principal,
    q: str | None,
    status: str | None,
    platform: str | None,
    course_id: uuid.UUID | None,
    branch_id: uuid.UUID | None,
    date_from: date | None,
    date_to: date | None,
) -> list[Any]:
    where: list[Any] = list(campaign_filters(p))
    if branch_id:
        where.append(Campaign.branch_id == branch_id)
    if status:
        where.append(Campaign.status == status)
    if platform:
        where.append(Campaign.platform == platform)
    if course_id:
        where.append(Campaign.course_id == course_id)
    if date_from:
        where.append(Campaign.start_date >= date_from)
    if date_to:
        where.append(Campaign.start_date <= date_to)
    if q and q.strip():
        like = f"%{q.strip().replace('%', r'\%').replace('_', r'\_')}%"
        where.append(Campaign.name.ilike(like))
    return where


def _select(where: list[Any]) -> Any:
    return (
        select(Campaign, Branch.name, Course.name)
        .join(Branch, Branch.id == Campaign.branch_id)
        .outerjoin(Course, Course.id == Campaign.course_id)
        .where(*where)
        .order_by(Campaign.start_date.desc(), Campaign.name, Campaign.id)
    )


async def _rows(db: AsyncSession, where: list[Any], limit: int) -> list[dict[str, Any]]:
    rows = (await db.execute(_select(where).limit(limit))).all()
    stats = await campaign_stats(db, [r[0] for r in rows])
    return [_out(c, b, course, stats[c.id]) for c, b, course in rows]


async def _load(db: AsyncSession, p: Principal, campaign_id: uuid.UUID) -> Campaign:
    campaign = (
        await db.execute(select(Campaign).where(Campaign.id == campaign_id, *campaign_filters(p)))
    ).scalar_one_or_none()
    if campaign is None:
        raise DomainError(NOT_FOUND)
    return campaign


async def _detail(db: AsyncSession, p: Principal, campaign_id: uuid.UUID) -> dict[str, Any]:
    return (await _rows(db, [Campaign.id == campaign_id], 1))[0]


async def _check_course(db: AsyncSession, course_id: uuid.UUID | None) -> None:
    if (
        course_id is not None
        and not (await db.execute(select(Course.id).where(Course.id == course_id))).first()
    ):
        raise DomainError(NOT_FOUND)


LIST_CAP = 500


@router.get("")
async def list_campaigns(
    p: MarketingReader,
    db: DB,
    q: str | None = None,
    status: str | None = None,
    platform: str | None = None,
    course_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    """All matching campaigns (a few dozen at most) with the totals of exactly these rows."""
    where = _where(p, q, status, platform, course_id, branch_id, date_from, date_to)
    found = (await db.execute(_select(where).limit(LIST_CAP))).all()
    campaigns = [r[0] for r in found]
    stats = await campaign_stats(db, campaigns)
    return {
        "items": [_out(c, b, course, stats[c.id]) for c, b, course in found],
        "totals": marketing_totals(campaigns, stats),
    }


CAMPAIGN_COLUMNS: list[Col[dict[str, Any]]] = [
    Col("Кампания", lambda c: c["name"]),
    Col("Курс", lambda c: c["course_name"]),
    Col("Филиал", lambda c: c["branch_name"]),
    Col("Платформа", lambda c: c["platform"]),
    Col("Старт", lambda c: c["start_date"], "date"),
    Col("Окончание", lambda c: c["end_date"], "date"),
    Col("Бюджет", lambda c: c["budget"], "money"),
    Col("Лиды", lambda c: c["leads"], "int"),
    Col("Записались", lambda c: c["converted"], "int"),
    Col("Зачислено", lambda c: c["enrolled"], "int"),
    Col("CPL", lambda c: c["cpl"], "money"),
    Col("CAC", lambda c: c["cac"], "money"),
    Col("Статус", lambda c: c["status"]),
]


@router.get("/export")
async def export_campaigns(
    p: MarketingReader,
    db: DB,
    q: str | None = None,
    status: str | None = None,
    platform: str | None = None,
    course_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Response:
    where = _where(p, q, status, platform, course_id, branch_id, date_from, date_to)
    rows = await _rows(db, where, MAX_ROWS + 1)
    check_cap(rows)
    return await xlsx_response(
        db,
        p,
        entity="campaign",
        slug="kampanii",
        title="Кампании",
        columns=CAMPAIGN_COLUMNS,
        rows=rows,
        filters={
            "q": q,
            "status": status,
            "platform": platform,
            "course_id": course_id,
            "branch_id": branch_id,
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@router.post("", status_code=201)
async def create_campaign(body: CampaignCreate, p: MarketingWriter, db: DB) -> dict[str, Any]:
    if body.end_date is not None and body.end_date < body.start_date:
        raise DomainError(CAMPAIGN_DATES_INVALID)
    await _check_course(db, body.course_id)
    campaign = Campaign(
        name=body.name,
        course_id=body.course_id,
        branch_id=branch_for_write(p, body.branch_id),
        platform=body.platform,
        start_date=body.start_date,
        end_date=body.end_date,
        budget=body.budget,
        status=body.status,
    )
    db.add(campaign)
    await db.flush()
    await record(
        db, p.id, "campaign.create", "campaign", campaign.id, diff_of({}, _snapshot(campaign)),
        branch_id=campaign.branch_id,
    )  # fmt: skip
    return await _detail(db, p, campaign.id)


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: uuid.UUID, p: MarketingReader, db: DB) -> dict[str, Any]:
    await _load(db, p, campaign_id)
    return await _detail(db, p, campaign_id)


@router.patch("/{campaign_id}")
async def update_campaign(
    campaign_id: uuid.UUID, body: CampaignUpdate, version: Version, p: MarketingWriter, db: DB
) -> dict[str, Any]:
    campaign = await _load(db, p, campaign_id)

    async def current() -> dict[str, Any]:
        return await _detail(db, p, campaign_id)

    await check_version(db, campaign, version, "campaign", current)
    before = _snapshot(campaign)
    sent = body.model_fields_set
    if "name" in sent and body.name:
        campaign.name = body.name
    if "course_id" in sent:
        await _check_course(db, body.course_id)
        campaign.course_id = body.course_id
    if "platform" in sent and body.platform:
        campaign.platform = body.platform
    if "start_date" in sent and body.start_date:
        campaign.start_date = body.start_date
    if "end_date" in sent:
        campaign.end_date = body.end_date
    if "budget" in sent and body.budget is not None:
        campaign.budget = body.budget
    if "status" in sent and body.status:
        campaign.status = body.status
    if campaign.end_date is not None and campaign.end_date < campaign.start_date:
        raise DomainError(CAMPAIGN_DATES_INVALID)
    await db.flush()
    await record(
        db, p.id, "campaign.update", "campaign", campaign.id,
        diff_of(before, _snapshot(campaign)), branch_id=campaign.branch_id,
    )  # fmt: skip
    return await _detail(db, p, campaign_id)


@router.delete("/{campaign_id}", status_code=204)
async def delete_campaign(campaign_id: uuid.UUID, p: MarketingWriter, db: DB) -> None:
    campaign = await _load(db, p, campaign_id)
    snapshot, branch_id = _snapshot(campaign), campaign.branch_id
    try:
        async with db.begin_nested():
            await db.delete(campaign)
            await db.flush()
    except IntegrityError as exc:
        raise DomainError(CAMPAIGN_IN_USE) from exc
    await record(
        db, p.id, "campaign.delete", "campaign", campaign_id, diff_of(snapshot, {}),
        branch_id=branch_id,
    )  # fmt: skip
