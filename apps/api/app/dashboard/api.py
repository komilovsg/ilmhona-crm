"""Data of the role dashboards' cards, one endpoint per card, each with its own rights check (a
card the layout hides is still protected here; the layout never grants anything). Branch scope
applies; `branch_id` narrows within it. Every number comes from `app.metrics.dash`.
"""

import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.auth.deps import CurrentUser, Principal, require_csrf_header
from app.core.db import DB
from app.core.errors import FORBIDDEN, DomainError
from app.education.scope import is_instructor
from app.leads.scope import reader
from app.metrics import dash
from app.metrics.money import debt_summary, today
from app.metrics.reports import callback_leads, hidden_money, hide_money
from app.metrics.sales import callbacks_today
from app.permissions import allows
from app.reports.api import scope_of

router = APIRouter(
    prefix="/api/v1/dashboard/cards",
    tags=["dashboard"],
    dependencies=[Depends(require_csrf_header)],
)

Payments = Annotated[Principal, reader("payments")]
Leads = Annotated[Principal, reader("leads")]
Cohorts = Annotated[Principal, reader("cohorts")]
Dashboard = Annotated[Principal, reader("dashboard")]
ALERT_COHORTS = 3
CALL_ROWS = 6


def _any_of(*sections: str) -> Any:
    async def dependency(p: CurrentUser) -> Principal:
        if is_instructor(p) or not any(allows(p.level(s), "view") for s in sections):
            raise DomainError(FORBIDDEN, section=sections[0], level="view")
        return p

    return Depends(dependency)


AnyOfLeadsPayments = Annotated[Principal, _any_of("leads", "payments")]


def plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def tjs(value: Decimal) -> str:
    whole = value == value.to_integral_value()
    text = f"{value:,.0f}" if whole else f"{value:,.2f}"
    return text.replace(",", " ") + " TJS"


def _alert(key: str, severity: str, title: str, hint: str, href: str) -> dict[str, str]:
    return {"key": key, "severity": severity, "title": title, "hint": hint, "href": href}


def _can(p: Principal, section: str) -> bool:
    return allows(p.level(section), "view")


# ---- superadmin cards ------------------------------------------------------------------------


@router.get("/month")
async def month(p: Payments, db: DB, branch_id: uuid.UUID | None = None) -> dict[str, Any]:
    data = await dash.month_hero(db, scope_of(p, branch_id))
    hide_money([data], hidden_money(p))  # profit needs payroll and marketing rights too
    return data


@router.get("/timeline")
async def timeline(p: Cohorts, db: DB, branch_id: uuid.UUID | None = None) -> dict[str, Any]:
    return await dash.cohort_lanes(db, scope_of(p, branch_id))


@router.get("/attention")
async def attention(p: Dashboard, db: DB, branch_id: uuid.UUID | None = None) -> dict[str, Any]:
    """Alerts the user may act on: each needs the section its numbers come from."""
    scope = scope_of(p, branch_id)
    alerts: list[dict[str, str]] = []
    if _can(p, "payments"):
        over = await dash.overpaid_months(db, scope.cohort)
        if over:
            top = over[0]
            if len(over) == 1:
                title = (
                    f"{top['cohort_code']}: переплата {tjs(top['overpaid'])} "
                    f"за {top['month_no']}-й месяц"
                )
            else:
                title = f"Переплаты в {len(over)} месяцах оплат"
            hint = (
                f"{top['student_name']}: оплаты за месяц больше цены — проверить"
                if len(over) == 1
                else f"Больше всего: {top['cohort_code']}, {tjs(top['overpaid'])}"
            )
            alerts.append(_alert("overpaid", "danger", title, hint, f"/cohorts/{top['cohort_id']}"))
    if _can(p, "cohorts"):
        unmarked = await dash.unmarked_cohorts(db, scope.cohort)
        if unmarked:
            n = len(unmarked)
            codes = ", ".join(u["cohort_code"] for u in unmarked[:5])
            word = plural(n, "поток", "потока", "потоков")
            title = f"{n} {word} без отметок {dash.UNMARKED_DAYS}+ дней"
            href = f"/cohorts/{unmarked[0]['cohort_id']}" if n == 1 else "/cohorts"
            alerts.append(
                _alert("unmarked", "warning", title, codes + (" …" if n > 5 else ""), href)
            )
    if _can(p, "payments"):
        pending = await dash.pending_payments(db, scope.cohort)
        if pending["count"]:
            n = pending["count"]
            age = pending["oldest_days"]
            old = (
                "старшая — сегодня"
                if not age
                else f"старшая — {age} {plural(age, 'день', 'дня', 'дней')}"
            )
            title = f"{n} {plural(n, 'оплата ждёт', 'оплаты ждут', 'оплат ждут')} подтверждения"
            alerts.append(
                _alert(
                    "pending",
                    "warning",
                    title,
                    f"{tjs(pending['sum'])} · {old}",
                    "/payments?status=ожидает",
                )
            )
    if _can(p, "cohorts"):
        soon = await dash.starting_soon_underfilled(db, scope.cohort)
        for s in soon[:ALERT_COHORTS]:
            d = s["starts_in_days"]
            when = "сегодня" if d == 0 else f"через {d} {plural(d, 'день', 'дня', 'дней')}"
            alerts.append(
                _alert(
                    f"soon:{s['cohort_id']}",
                    "info",
                    f"{s['cohort_code']} стартует {when}",
                    f"Занято {s['enrolled']} из {s['capacity']} — нужна реклама",
                    f"/cohorts/{s['cohort_id']}",
                )
            )
        if len(soon) > ALERT_COHORTS:
            n = len(soon) - ALERT_COHORTS
            alerts.append(
                _alert(
                    "soon:more",
                    "info",
                    f"Ещё {n} {plural(n, 'поток', 'потока', 'потоков')} с малым набором",
                    "Старт в ближайшие 14 дней",
                    "/cohorts",
                )
            )
    return {"items": alerts}


@router.get("/demand")
async def demand(p: Leads, db: DB, branch_id: uuid.UUID | None = None) -> dict[str, Any]:
    return await dash.lead_demand(db, scope_of(p, branch_id))


@router.get("/branches")
async def branches(p: Payments, db: DB, branch_id: uuid.UUID | None = None) -> dict[str, Any]:
    return await dash.income_by_branch_month(db, scope_of(p, branch_id))


# ---- manager cards ---------------------------------------------------------------------------


@router.get("/queues")
async def queues(
    p: AnyOfLeadsPayments, db: DB, branch_id: uuid.UUID | None = None
) -> dict[str, Any]:
    """Tiles for the sections the user may read; the others are not in the answer."""
    scope = scope_of(p, branch_id)
    tiles: list[dict[str, Any]] = []
    if _can(p, "leads"):
        due = await callbacks_today(db, scope.leads())
        tiles.append(
            {
                "key": "callbacks",
                "count": due,
                "overdue": await dash.callbacks_overdue(db, scope.leads()),
            }
        )
    if _can(p, "payments"):
        debtors, debt = await debt_summary(db, scope.cohort)
        tiles.append({"key": "debtors", "count": debtors, "sum": debt})
        pending = await dash.pending_payments(db, scope.cohort)
        tiles.append({"key": "pending", "count": pending["count"], "sum": pending["sum"]})
    if _can(p, "leads"):
        day = today()
        tiles.append(
            {"key": "new_leads", "count": await dash.leads_created(db, scope.leads(), day, day)}
        )
    return {"tiles": tiles}


@router.get("/call-queue")
async def call_queue(p: Leads, db: DB, branch_id: uuid.UUID | None = None) -> dict[str, Any]:
    scope = scope_of(p, branch_id)
    return {
        "count": await callbacks_today(db, scope.leads()),
        "items": await callback_leads(db, scope, CALL_ROWS),
    }


@router.get("/seats")
async def seats(p: Cohorts, db: DB, branch_id: uuid.UUID | None = None) -> dict[str, Any]:
    return {"items": await dash.open_cohorts(db, scope_of(p, branch_id))}


@router.get("/week")
async def week(p: Dashboard, db: DB, branch_id: uuid.UUID | None = None) -> dict[str, Any]:
    """The last 7 days; what the user may not read (leads, money) is null."""
    data = await dash.week_summary(db, scope_of(p, branch_id))
    hidden: dict[str, tuple[str, ...]] = {
        "leads": ("leads", "leads_change"),
        "payments": ("payments_count", "payments_sum", "debt", "debtors"),
    }
    for section, keys in hidden.items():
        if not _can(p, section):
            for k in keys:
                data[k] = None
    return data
