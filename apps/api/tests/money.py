"""Fixtures for the money tests: running cohorts, enrollments, payments, payouts (all fake)."""

import uuid
from datetime import date
from typing import Any

import httpx

from app.cohorts.status import today
from app.metrics.money import cohort_months
from app.permissions import MANAGER_DEFAULT
from tests.conftest import make_role, sql
from tests.edu import C, make_cohort, make_course, make_room, make_student

P = "/api/v1/payments"
PO = "/api/v1/payouts"
S = "/api/v1/salaries"
I = "/api/v1/instructors"  # noqa: E741


def add_months(d: date, n: int) -> date:
    index = d.year * 12 + d.month - 1 + n
    return date(index // 12, index % 12 + 1, d.day)


def this_month() -> date:
    return today().replace(day=1)


async def running_cohort(
    admin: httpx.AsyncClient,
    *,
    name: str = "A",
    branch: str = "Душанбе",
    back: int = 2,
    weeks: int = 17,
    price: int = 500,
    **extra: Any,
) -> dict[str, Any]:
    """A cohort that started `back` months ago (first of that month) and is still running."""
    cohort = await make_cohort(
        admin,
        await make_course(f"Курс {name}", price),
        await make_room(branch, f"R-{name}"),
        branch=branch,
        start=add_months(this_month(), -back),
        weeks=weeks,
        **extra,
    )
    cohort["months"] = cohort_months(
        date.fromisoformat(cohort["start_date"]), date.fromisoformat(cohort["end_date"])
    )
    return cohort


async def enroll(
    admin: httpx.AsyncClient,
    cohort: dict[str, Any],
    name: str = "Студент",
    *,
    since: date | None = None,
    branch: str = "Душанбе",
) -> str:
    """Enroll a new student; `since` moves enrolled_at (default: the cohort's start)."""
    sid = await make_student(name, branch)
    r = await admin.post(f"{C}/{cohort['id']}/enrollments", json={"student_id": str(sid)})
    assert r.status_code == 201, r.text
    await sql(
        "UPDATE enrollment SET enrolled_at = :d WHERE id = :i",
        d=since or date.fromisoformat(cohort["start_date"]),
        i=r.json()["id"],
    )
    return str(r.json()["id"])


async def pay(
    c: httpx.AsyncClient,
    enrollment: str,
    *,
    month: int = 1,
    amount: str | int = 500,
    method: str = "alif",
    confirm: bool = False,
    key: uuid.UUID | None = None,
    paid_at: date | None = None,
    **extra: Any,
) -> dict[str, Any]:
    r = await c.post(
        P,
        json={
            "idempotency_key": str(key or uuid.uuid4()),
            "enrollment_id": enrollment,
            "month_no": month,
            "amount": str(amount),
            "method": method,
            "paid_at": (paid_at or today()).isoformat(),
            **extra,
        },
    )
    assert r.status_code == 201, r.text
    payment = r.json()
    if confirm:
        r = await c.post(f"{P}/{payment['id']}/confirm")
        assert r.status_code == 200, r.text
        payment = r.json()
    return payment  # type: ignore[no-any-return]


async def cohort_money(c: httpx.AsyncClient, cohort: dict[str, Any]) -> dict[str, Any]:
    r = await c.get(f"{P}/by-cohort/{cohort['id']}")
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def money_of(summary: dict[str, Any], enrollment: str) -> dict[str, Any]:
    return next(i for i in summary["items"] if i["enrollment_id"] == enrollment)


async def make_payout(
    c: httpx.AsyncClient, cohort: dict[str, Any], period: date | None = None, **kw: Any
) -> httpx.Response:
    return await c.post(
        PO,
        json={
            "cohort_id": cohort["id"],
            "period": (period or this_month()).isoformat(),
            "paid_at": today().isoformat(),
            "method": "наличные",
            **kw,
        },
    )


async def manager_role() -> uuid.UUID:
    """The manager's starting rights as a custom role: another test may have edited the seeded one."""
    return await make_role("Менеджер (тест)", dict(MANAGER_DEFAULT))
