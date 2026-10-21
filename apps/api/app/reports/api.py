"""Dashboard and master list (stage 4). Every number comes from `app.metrics.reports`.

Rights: `dashboard` and `master_list` view; the instructor role gets 403 whatever the matrix says
(money and sales numbers). Money needs its own section too (`MONEY_SECTIONS`: hidden = null,
no Excel column); lead names on the dashboard need `leads` view. Branch scope applies; the
branch toggle narrows within it (another branch than the user's is a 404).
"""

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response

from app.auth.deps import Principal, require_csrf_header
from app.core.db import DB
from app.core.paging import Page, PageSize
from app.export import MAX_ROWS, Col, check_cap, xlsx_response
from app.leads.scope import reader
from app.metrics import unfilled_top
from app.metrics.reports import (
    Scope,
    by_course,
    by_month,
    callback_leads,
    hidden_money,
    hide_money,
    master_count,
    master_rows,
    master_select,
    master_where,
    overview,
    recent_leads,
    shown_columns,
)
from app.metrics.sales import callbacks_today
from app.permissions import allows

router = APIRouter(prefix="/api/v1", tags=["reports"], dependencies=[Depends(require_csrf_header)])

DashboardReader = Annotated[Principal, reader("dashboard")]
MasterReader = Annotated[Principal, reader("master_list")]
WIDGET_ROWS = 5


def scope_of(p: Principal, branch_id: uuid.UUID | None) -> Scope:
    if branch_id:
        p.check_scope(branch_id)
    return Scope.of(p, branch_id)


# ---- dashboard ---------------------------------------------------------------------------


@router.get("/dashboard/overview")
async def dashboard_overview(
    p: DashboardReader,
    db: DB,
    branch_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    scope = scope_of(p, branch_id)
    unfilled_count, unfilled = await unfilled_top(db, scope.cohort, WIDGET_ROWS)
    names = allows(p.level("leads"), "view")  # lead names and phones: the leads section's
    (numbers,) = hide_money([await overview(db, scope, date_from, date_to)], hidden_money(p))
    return {
        **numbers,
        "unfilled": {
            "count": unfilled_count,
            "items": [
                {
                    "lesson_id": lesson.id,
                    "cohort_id": cohort.id,
                    "cohort_code": cohort.code,
                    "course_name": course,
                    "date": lesson.lesson_date,
                    "marked": marked,
                    "total": total,
                }
                for lesson, cohort, course, _room, total, marked in unfilled
            ],
        },
        "callbacks": {
            "count": await callbacks_today(db, scope.leads()),
            "items": await callback_leads(db, scope, WIDGET_ROWS) if names else [],
        },
        "recent_leads": await recent_leads(db, scope, WIDGET_ROWS) if names else [],
    }


@router.get("/dashboard/by-month")
async def dashboard_by_month(
    p: DashboardReader, db: DB, branch_id: uuid.UUID | None = None
) -> dict[str, Any]:
    data = await by_month(db, scope_of(p, branch_id))
    hide_money(data["items"], hidden_money(p))
    return data


MONTH_COLUMNS: list[Col[dict[str, Any]]] = [
    Col("Месяц", lambda r: r["month"], "date"),
    Col("Доход", lambda r: r["income"], "money"),
    Col("Зарплата", lambda r: r["payroll"], "money"),
    Col("Реклама", lambda r: r["ads"], "money"),
    Col("Прибыль", lambda r: r["profit"], "money"),
    Col("Новых студентов", lambda r: r["new_students"], "int"),
    Col("Лидов", lambda r: r["leads"], "int"),
]
MONTH_MONEY = {"Доход": "income", "Зарплата": "payroll", "Реклама": "ads", "Прибыль": "profit"}


@router.get("/dashboard/by-month/export")
async def export_by_month(
    p: DashboardReader, db: DB, branch_id: uuid.UUID | None = None
) -> Response:
    data = await by_month(db, scope_of(p, branch_id))
    return await xlsx_response(
        db,
        p,
        entity="dashboard_month",
        slug="dashbord_po_mesyatsam",
        title="Дашборд по месяцам",
        columns=shown_columns(MONTH_COLUMNS, MONTH_MONEY, hidden_money(p)),
        rows=data["items"],
        filters={"branch_id": branch_id},
    )


@router.get("/dashboard/by-course")
async def dashboard_by_course(
    p: DashboardReader,
    db: DB,
    branch_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    items = await by_course(db, scope_of(p, branch_id), date_from, date_to)
    hidden = hidden_money(p)
    if "income" in hidden:  # the order by income would rank what the numbers hide
        items.sort(key=lambda r: r["course_name"])
    return {"items": hide_money(items, hidden)}


# ---- master list -------------------------------------------------------------------------


@router.get("/master-list")
async def master_list(
    p: MasterReader,
    db: DB,
    branch_id: uuid.UUID | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: Page = 1,
    page_size: PageSize = 25,
) -> dict[str, Any]:
    where = master_where(scope_of(p, branch_id), status, date_from, date_to)
    total = await master_count(db, where)
    found = (
        await db.execute(master_select(where).limit(page_size).offset((page - 1) * page_size))
    ).all()
    return {
        "items": hide_money(await master_rows(db, [tuple(r) for r in found]), hidden_money(p)),
        "total": total,
        "page": page,
        "page_size": page_size,
    }


MASTER_COLUMNS: list[Col[dict[str, Any]]] = [
    Col("Старт", lambda r: r["start_date"], "date"),
    Col("Конец", lambda r: r["end_date"], "date"),
    Col("Поток", lambda r: r["code"]),
    Col("Курс", lambda r: r["course_name"]),
    Col("Филиал", lambda r: r["branch_name"]),
    Col("Формат", lambda r: "Онлайн" if r["format"] == "online" else "Офлайн"),
    Col("Стоимость/мес", lambda r: r["price_month"], "money"),
    Col("Статус", lambda r: r["status"]),
    Col("Лиды (за 45 дней до старта)", lambda r: r["leads"], "int"),
    Col("Нулевой урок", lambda r: r["zero_lesson"], "int"),
    Col("Записались", lambda r: r["enrolled"], "int"),
    Col("Оплатили мес. 1", lambda r: r["paid_1"], "int"),
    Col("Оплатили мес. 2", lambda r: r["paid_2"], "int"),
    Col("Оплатили мес. 3", lambda r: r["paid_3"], "int"),
    Col("LTV/чел", lambda r: r["ltv"], "money"),
    Col("Доход", lambda r: r["income"], "money"),
    Col("Выпускников", lambda r: r["graduates"], "int"),
    Col("Трудоустроено", lambda r: r["employed"], "int"),
]
MASTER_MONEY = {"LTV/чел": "ltv", "Доход": "income"}


@router.get("/master-list/export")
async def export_master_list(
    p: MasterReader,
    db: DB,
    branch_id: uuid.UUID | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Response:
    where = master_where(scope_of(p, branch_id), status, date_from, date_to)
    found = (await db.execute(master_select(where).limit(MAX_ROWS + 1))).all()
    check_cap(found)
    rows = await master_rows(db, [tuple(r) for r in found])
    return await xlsx_response(
        db,
        p,
        entity="master_list",
        slug="master_list",
        title="Мастер-лист",
        columns=shown_columns(MASTER_COLUMNS, MASTER_MONEY, hidden_money(p)),
        rows=rows,
        filters={
            "branch_id": branch_id,
            "status": status,
            "date_from": date_from,
            "date_to": date_to,
        },
    )
