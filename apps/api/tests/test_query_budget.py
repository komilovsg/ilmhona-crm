"""Query-count budgets of the hottest endpoints. Every SQL statement is a network round trip to
Neon, so a list that runs one query per row (N+1) is slow in production while its test passes.
Each endpoint is counted on a small world and again after more cohorts, graduates, students and
payments exist: the count must not move, and must stay under its budget."""

from collections.abc import Callable

import httpx
import pytest
from sqlalchemy import event

from app.core.db import engine
from tests.conftest import sql
from tests.money import enroll, pay, running_cohort
from tests.reports import finished_cohort, world

# name -> (url builder, budget: the most statements one request may run)
ENDPOINTS: dict[str, tuple[Callable[[dict[str, str]], str], int]] = {
    "auth/me": (lambda w: "/api/v1/auth/me", 2),
    "dashboard/overview": (lambda w: "/api/v1/dashboard/overview", 11),
    "graduates/students": (lambda w: "/api/v1/graduates/students", 8),
    "graduates/courses": (lambda w: "/api/v1/graduates/courses", 8),
    "students list": (lambda w: "/api/v1/students", 5),
    "payments list": (lambda w: "/api/v1/payments", 4),
    "payments debtors": (lambda w: "/api/v1/payments/debtors", 4),
    "cohorts list": (lambda w: "/api/v1/cohorts", 7),
    "attendance grid": (lambda w: f"/api/v1/cohorts/{w['cohort']}/attendance", 7),
    "me/today": (lambda w: "/api/v1/me/today", 6),
    "master-list": (lambda w: "/api/v1/master-list", 9),
}


class Counter:
    def __init__(self) -> None:
        self.n = 0

    def __call__(self, *_: object) -> None:
        self.n += 1


async def queries(c: httpx.AsyncClient, url: str) -> int:
    counter = Counter()
    event.listen(engine.sync_engine, "before_cursor_execute", counter)
    try:
        r = await c.get(url)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", counter)
    assert r.status_code == 200, (url, r.text)
    return counter.n


@pytest.mark.parametrize("name", ENDPOINTS)
async def test_query_count_is_flat_and_within_budget(
    name: str,
    admin: httpx.AsyncClient,
    browser: Callable[[], httpx.AsyncClient],
) -> None:
    w = await world(admin, browser)
    ids = {"cohort": str(w["done"]["id"])}
    build, budget = ENDPOINTS[name]
    small = await queries(admin, build(ids))
    # three more cohorts' worth of rows on every list
    await finished_cohort(
        admin, {"Г Один": (40, 40), "Г Два": (35, 35), "Г Три": (30, 40)}, name="X"
    )
    await finished_cohort(admin, {"Г Четыре": (40, 30)}, name="Y", branch="Истаравшан")
    more = await running_cohort(admin, name="More")
    for i in range(3):
        enrollment = await enroll(admin, more, f"Ещё {i}")
        await pay(admin, enrollment, month=1, confirm=bool(i % 2))
    assert (await sql("SELECT count(*) FROM cohort"))[0][0] >= 7
    big = await queries(admin, build(ids))
    assert big == small, f"{name}: {small} queries on a small world, {big} on a bigger one (N+1?)"
    assert big <= budget, f"{name}: {big} queries, budget {budget}"
