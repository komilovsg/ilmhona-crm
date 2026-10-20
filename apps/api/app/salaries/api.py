"""Salaries (stage 2): the payout schedule, the cohort's rate and the payouts actually made.

Rights: section `instructors` (view to read, change to write; the instructor role never writes).
The instructor role sees only their own rate, schedule and payouts: another instructor's payout
is 404, asking for another instructor's schedule is 404. Branch scope through the cohort.

The schedule = every month a cohort (with an instructor, not cancelled) runs × its rate. The
profit uses the payouts made, never the schedule (#9). Numbers come from `app.metrics.money`.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.audit.log import diff_of, record
from app.auth.deps import Principal, require, require_csrf_header
from app.core.db import DB
from app.core.errors import NOT_FOUND, DomainError
from app.core.versioning import Version, check_version
from app.education.scope import check_cohort_visible, cohort_filters, is_instructor, writer
from app.export import MAX_ROWS, Col, check_cap, xlsx_response
from app.metrics.money import (
    cohort_periods,
    first_of_month,
    money,
    salary_rows,
    salary_summary,
    today,
)
from app.models import AppUser, Branch, Cohort, Course, InstructorPayout
from app.payments.errors import COHORT_NO_INSTRUCTOR, PAYOUT_PERIOD_INVALID

router = APIRouter(prefix="/api/v1", tags=["salaries"], dependencies=[Depends(require_csrf_header)])

View = Annotated[Principal, require("instructors", "view")]
Change = Annotated[Principal, writer("instructors")]

MIN_DATE, MAX_DATE = date(2020, 1, 1), date(2035, 12, 31)
METHOD_LABELS = {"alif": "Alif", "payvand": "Payvand", "наличные": "Наличные"}
MonthParam = Annotated[str | None, Query(pattern=r"^(\d{4}-(0[1-9]|1[0-2])|all)$")]
MonthOnly = Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


Money = Annotated[Decimal, Field(max_digits=12, decimal_places=2)]
Day = Annotated[date, Field(ge=MIN_DATE, le=MAX_DATE)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class RateIn(Strict):
    instructor_rate: Annotated[Money, Field(ge=0)]


class PayoutIn(Strict):
    cohort_id: uuid.UUID
    period: Day  # any day of the month: it is stored as the first day
    amount: Annotated[Money, Field(gt=0)] | None = None  # default: the cohort's rate
    paid_at: Day
    method: Literal["alif", "payvand", "наличные"]
    note: Note | None = None


class PayoutUpdate(Strict):
    amount: Annotated[Money, Field(gt=0)] | None = None
    paid_at: Day | None = None
    method: Literal["alif", "payvand", "наличные"] | None = None
    note: Note | None = None


def _month_start(month: str) -> date:
    return date(int(month[:4]), int(month[5:]), 1)


def _next_month(d: date) -> date:
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1)


def _own(p: Principal, instructor_id: uuid.UUID | None) -> uuid.UUID | None:
    """Which instructor's money the request is about: an instructor's own, always; asking for
    somebody else's is 404."""
    if is_instructor(p):
        if instructor_id not in (None, p.id):
            raise DomainError(NOT_FOUND)
        return p.id
    return instructor_id


# ---- schedule ----------------------------------------------------------------------------


def _scope(
    p: Principal, branch_id: uuid.UUID | None, cohort_id: uuid.UUID | None
) -> list[ColumnElement[bool]]:
    where = list(cohort_filters(p))
    if branch_id:
        where.append(Cohort.branch_id == branch_id)
    if cohort_id:
        where.append(Cohort.id == cohort_id)
    return where


async def _schedule(
    db: AsyncSession,
    p: Principal,
    month: str | None,
    instructor_id: uuid.UUID | None,
    branch_id: uuid.UUID | None,
    cohort_id: uuid.UUID | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    who = _own(p, instructor_id)
    where = _scope(p, branch_id, cohort_id)
    rows = await salary_rows(db, where, instructor_id=who)
    summary = await salary_summary(db, where, rows, instructor_id=who)
    wanted = (
        first_of_month(today())
        if month is None
        else None
        if month == "all"
        else _month_start(month)
    )
    shown = [r for r in rows if wanted is None or r["period"] == wanted]
    branches = {i: n for i, n in (await db.execute(select(Branch.id, Branch.name))).all()}
    for r in shown:
        r["branch_name"] = branches.get(r["branch_id"])
    return summary, shown


@router.get("/salaries")
async def get_salaries(
    p: View,
    db: DB,
    month: MonthParam = None,
    instructor_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    cohort_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    summary, items = await _schedule(db, p, month, instructor_id, branch_id, cohort_id)
    return {"summary": summary, "items": items, "total": len(items)}


SCHEDULE_COLUMNS: list[Col[dict[str, Any]]] = [
    Col("Месяц", lambda r: r["period"], "date"),
    Col("Инструктор", lambda r: r["instructor_name"]),
    Col("Поток", lambda r: r["cohort_code"]),
    Col("Курс", lambda r: r["course_name"]),
    Col("Филиал", lambda r: r["branch_name"]),
    Col("Ставка", lambda r: r["rate"], "money"),
    Col("Выплачено", lambda r: r["paid"], "money"),
    Col("К выплате", lambda r: r["due"], "money"),
    Col("Статус", lambda r: r["state"]),
    Col("Дата выплаты", lambda r: r["payout"]["paid_at"] if r["payout"] else None, "date"),
]


@router.get("/salaries/export")
async def export_salaries(
    p: View,
    db: DB,
    month: MonthParam = None,
    instructor_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    cohort_id: uuid.UUID | None = None,
) -> Response:
    _, items = await _schedule(db, p, month, instructor_id, branch_id, cohort_id)
    check_cap(items)
    return await xlsx_response(
        db,
        p,
        entity="salary",
        slug="grafik_vyplat",
        title="График выплат",
        columns=SCHEDULE_COLUMNS,
        rows=items,
        filters={
            "month": month,
            "instructor_id": instructor_id,
            "branch_id": branch_id,
            "cohort": cohort_id,
        },
    )


@router.patch("/salaries/cohorts/{cohort_id}/rate")
async def set_cohort_rate(
    cohort_id: uuid.UUID, body: RateIn, version: Version, p: Change, db: DB
) -> dict[str, Any]:
    cohort = (await db.execute(select(Cohort).where(Cohort.id == cohort_id))).scalar_one_or_none()
    if cohort is None:
        raise DomainError(NOT_FOUND)
    check_cohort_visible(p, cohort)

    async def current() -> dict[str, Any]:
        return {"cohort_id": cohort.id, "instructor_rate": cohort.instructor_rate}

    await check_version(db, cohort, version, "cohort", current)
    before = str(cohort.instructor_rate)
    cohort.instructor_rate = body.instructor_rate
    await db.flush()
    await db.refresh(cohort)
    await record(
        db,
        p.id,
        "cohort.update",
        "cohort",
        cohort.id,
        diff_of({"instructor_rate": before}, {"instructor_rate": str(cohort.instructor_rate)}),
        branch_id=cohort.branch_id,
    )
    return {"cohort_id": cohort.id, "version": cohort.version, **await current()}


# ---- payouts -----------------------------------------------------------------------------

InstructorUser = aliased(AppUser)


def _payout_select() -> Any:
    return (
        select(InstructorPayout, InstructorUser.full_name, Cohort, Course.name, Branch.name)
        .join(InstructorUser, InstructorUser.id == InstructorPayout.instructor_id)
        .join(Cohort, Cohort.id == InstructorPayout.cohort_id)
        .join(Course, Course.id == Cohort.course_id)
        .join(Branch, Branch.id == Cohort.branch_id)
    )


def _payout_out(
    po: InstructorPayout, instructor: str, cohort: Cohort, course: str, branch: str
) -> dict[str, Any]:
    return {
        "id": po.id,
        "version": po.version,
        "instructor_id": po.instructor_id,
        "instructor_name": instructor,
        "cohort_id": cohort.id,
        "cohort_code": cohort.code,
        "course_name": course,
        "branch_id": cohort.branch_id,
        "branch_name": branch,
        "period": po.period,
        "amount": po.amount,
        "rate": cohort.instructor_rate,
        "paid_at": po.paid_at,
        "method": po.method,
        "note": po.note,
    }


def _payout_snapshot(po: InstructorPayout) -> dict[str, Any]:
    return {
        "amount": str(po.amount),
        "paid_at": po.paid_at,
        "method": po.method,
        "note": po.note,
    }


def _payout_label(instructor: str, cohort: Cohort, po: InstructorPayout) -> str:
    return f"{instructor}, {cohort.code}, {po.period:%m.%Y}"


def _payout_where(
    p: Principal,
    instructor_id: uuid.UUID | None,
    cohort_id: uuid.UUID | None,
    branch_id: uuid.UUID | None,
    month: str | None,
) -> list[ColumnElement[bool]]:
    """Branch scope through the cohort; the instructor role: own payouts only (also for
    cohorts they no longer teach)."""
    where: list[ColumnElement[bool]] = []
    if p.branch_id is not None:
        where.append(Cohort.branch_id == p.branch_id)
    who = _own(p, instructor_id)
    if who:
        where.append(InstructorPayout.instructor_id == who)
    if cohort_id:
        where.append(InstructorPayout.cohort_id == cohort_id)
    if branch_id:
        where.append(Cohort.branch_id == branch_id)
    if month:
        first = _month_start(month)
        where.append(InstructorPayout.period >= first)
        where.append(InstructorPayout.period < _next_month(first))
    return where


async def _payout_row(db: AsyncSession, p: Principal, payout_id: uuid.UUID) -> Any:
    row = (await db.execute(_payout_select().where(InstructorPayout.id == payout_id))).first()
    if row is None:
        raise DomainError(NOT_FOUND)
    p.check_scope(row[2].branch_id)
    if is_instructor(p) and row[0].instructor_id != p.id:
        raise DomainError(NOT_FOUND)  # another instructor's payout
    return row


@router.get("/payouts")
async def list_payouts(
    p: View,
    db: DB,
    instructor_id: uuid.UUID | None = None,
    cohort_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    month: MonthOnly = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict[str, Any]:
    where = _payout_where(p, instructor_id, cohort_id, branch_id, month)
    rows = (
        await db.execute(
            _payout_select()
            .where(*where)
            .order_by(InstructorPayout.paid_at.desc(), InstructorPayout.id)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).all()
    total, amount = (
        await db.execute(
            select(func.count(), func.coalesce(func.sum(InstructorPayout.amount), 0))
            .select_from(InstructorPayout)
            .join(Cohort, Cohort.id == InstructorPayout.cohort_id)
            .where(*where)
        )
    ).one()
    return {
        "items": [_payout_out(*r) for r in rows],
        "total": total,
        "sum": money(amount),
        "page": page,
        "page_size": page_size,
    }


PAYOUT_COLUMNS: list[Col[dict[str, Any]]] = [
    Col("Дата выплаты", lambda r: r["paid_at"], "date"),
    Col("Инструктор", lambda r: r["instructor_name"]),
    Col("Поток", lambda r: r["cohort_code"]),
    Col("Курс", lambda r: r["course_name"]),
    Col("Филиал", lambda r: r["branch_name"]),
    Col("Месяц", lambda r: r["period"], "date"),
    Col("Сумма", lambda r: r["amount"], "money"),
    Col("Способ", lambda r: METHOD_LABELS[r["method"]]),
    Col("Заметка", lambda r: r["note"]),
]


@router.get("/payouts/export")
async def export_payouts(
    p: View,
    db: DB,
    instructor_id: uuid.UUID | None = None,
    cohort_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    month: MonthOnly = None,
) -> Response:
    where = _payout_where(p, instructor_id, cohort_id, branch_id, month)
    rows = (
        await db.execute(
            _payout_select()
            .where(*where)
            .order_by(InstructorPayout.paid_at.desc(), InstructorPayout.id)
            .limit(MAX_ROWS + 1)
        )
    ).all()
    check_cap(rows)
    return await xlsx_response(
        db,
        p,
        entity="instructor_payout",
        slug="vyplaty",
        title="Выплаты",
        columns=PAYOUT_COLUMNS,
        rows=[_payout_out(*r) for r in rows],
        filters={
            "instructor_id": instructor_id,
            "cohort": cohort_id,
            "branch_id": branch_id,
            "month": month,
        },
    )


@router.post("/payouts", status_code=201)
async def create_payout(body: PayoutIn, p: Change, db: DB) -> dict[str, Any]:
    cohort = (
        await db.execute(select(Cohort).where(Cohort.id == body.cohort_id))
    ).scalar_one_or_none()
    if cohort is None:
        raise DomainError(NOT_FOUND)
    check_cohort_visible(p, cohort)
    if cohort.instructor_id is None:
        raise DomainError(COHORT_NO_INSTRUCTOR)
    period = first_of_month(body.period)
    if period not in cohort_periods(cohort.start_date, cohort.end_date):
        raise DomainError(PAYOUT_PERIOD_INVALID)
    po = InstructorPayout(
        instructor_id=cohort.instructor_id,
        cohort_id=cohort.id,
        period=period,
        amount=cohort.instructor_rate if body.amount is None else body.amount,
        paid_at=body.paid_at,
        method=body.method,
        note=body.note or None,
    )
    db.add(po)
    await db.flush()  # unique(instructor, cohort, period): a second payout is a 409
    row = await _payout_row(db, p, po.id)
    await record(
        db,
        p.id,
        "payout.create",
        "instructor_payout",
        po.id,
        diff_of({}, _payout_snapshot(po)),
        branch_id=cohort.branch_id,
        label=_payout_label(row[1], cohort, po),
    )
    return _payout_out(*row)


@router.get("/payouts/{payout_id}")
async def get_payout(payout_id: uuid.UUID, p: View, db: DB) -> dict[str, Any]:
    return _payout_out(*await _payout_row(db, p, payout_id))


@router.patch("/payouts/{payout_id}")
async def update_payout(
    payout_id: uuid.UUID, body: PayoutUpdate, version: Version, p: Change, db: DB
) -> dict[str, Any]:
    row = await _payout_row(db, p, payout_id)
    po: InstructorPayout = row[0]

    async def current() -> dict[str, Any]:
        return _payout_out(*await _payout_row(db, p, payout_id))

    await check_version(db, po, version, "instructor_payout", current)
    before = _payout_snapshot(po)
    sent = body.model_fields_set
    for field in ("amount", "paid_at", "method"):
        if field in sent and getattr(body, field) is not None:
            setattr(po, field, getattr(body, field))
    if "note" in sent:
        po.note = body.note or None
    await db.flush()
    await db.refresh(po)
    await record(
        db,
        p.id,
        "payout.update",
        "instructor_payout",
        po.id,
        diff_of(before, _payout_snapshot(po)),
        branch_id=row[2].branch_id,
        label=_payout_label(row[1], row[2], po),
    )
    return await current()


@router.delete("/payouts/{payout_id}", status_code=204)
async def delete_payout(payout_id: uuid.UUID, p: Change, db: DB) -> None:
    row = await _payout_row(db, p, payout_id)
    po: InstructorPayout = row[0]
    snapshot, label, branch_id = (
        _payout_snapshot(po),
        _payout_label(row[1], row[2], po),
        row[2].branch_id,
    )
    await db.delete(po)
    await db.flush()
    await record(
        db,
        p.id,
        "payout.delete",
        "instructor_payout",
        payout_id,
        diff_of(snapshot, {}),
        branch_id=branch_id,
        label=label,
    )
