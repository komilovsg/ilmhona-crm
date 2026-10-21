"""Stage 4: the dashboard against the lists (#3, #22), months, courses, scope."""

from collections.abc import Callable
from decimal import Decimal
from typing import Any

import httpx

from tests.conftest import SignedIn, branch_id, make_role
from tests.money import PO, I, P
from tests.reports import ML, D, G, world
from tests.sales import CA, L

S = "/api/v1/students"
C = "/api/v1/cohorts"


async def total(c: httpx.AsyncClient, url: str, **params: Any) -> int:
    r = await c.get(url, params={"page_size": 1, **params})
    assert r.status_code == 200, r.text
    return r.json()["total"]  # type: ignore[no-any-return]


async def _branch_params(name: str | None) -> dict[str, str]:
    return {"branch_id": str(await branch_id(name))} if name else {}


# ---- #3 ----------------------------------------------------------------------------------


async def test_bug_03_dashboard_tiles_equal_the_lists(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    await world(admin, browser)
    for branch in (None, "Душанбе", "Истаравшан"):
        b = await _branch_params(branch)
        o = (await admin.get(f"{D}/overview", params=b)).json()
        # students and cohorts: the same status expression as the lists
        assert o["active_students"] == await total(admin, S, status="активный", **b)
        assert o["students_total"] == await total(admin, S, **b)
        assert o["active_cohorts"] == await total(admin, C, status="активный", **b)
        assert o["recruiting_cohorts"] == await total(admin, C, status="набор", **b)
        assert o["cohorts_total"] == await total(admin, C, **b)
        # money: payments and payouts lists
        payments = (await admin.get(P, params={"status": "подтверждено", **b})).json()
        assert o["income"] == payments["summary"]["confirmed"]
        payouts = (await admin.get(PO, params=b)).json()
        assert o["payroll"] == payouts["sum"]
        # leads, conversion, campaigns
        assert o["leads"] == await total(admin, L, **b)
        assert o["converted"] == await total(admin, L, status="записан", **b)
        assert o["conversion"] == (round(o["converted"] * 100 / o["leads"], 1) if o["leads"] else 0)
        campaigns = (await admin.get(CA, params=b)).json()["totals"]
        assert o["ads"] == campaigns["budget"] and o["campaigns"] == campaigns["campaigns"]
        assert Decimal(o["profit"]) == (
            Decimal(o["income"]) - Decimal(o["ads"]) - Decimal(o["payroll"])
        )
        # graduates: the list of graduates
        assert o["graduates"] == await total(admin, f"{G}/students", **b)
        courses = (await admin.get(f"{G}/courses", params=b)).json()["items"]
        assert o["graduates"] == sum(r["graduates"] for r in courses)
        assert o["funnel"]["всего"] == o["leads"]


async def test_dashboard_numbers_on_the_fixture(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    await world(admin, browser)
    o = (await admin.get(f"{D}/overview")).json()
    assert (o["leads"], o["converted"], o["conversion"]) == (5, 2, 40.0)
    assert (o["active_students"], o["students_total"]) == (3, 6)
    assert (o["active_cohorts"], o["recruiting_cohorts"]) == (2, 1)
    assert (o["income"], o["payroll"], o["ads"], o["profit"]) == (
        "1600.00", "400.00", "1200.00", "0.00",
    )  # fmt: skip
    assert (o["graduates"], o["campaigns"], o["cac"]) == (1, 2, "600.00")
    assert o["callbacks"]["count"] == 0 and len(o["recent_leads"]) == 5
    assert o["unfilled"]["count"] >= 0


async def test_cac_is_empty_without_converted_leads(admin: httpx.AsyncClient) -> None:
    o = (await admin.get(f"{D}/overview")).json()
    assert o["cac"] is None and o["conversion"] == 0 and o["leads"] == 0


async def test_period_cuts_dated_numbers_only(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    await world(admin, browser)
    old = {"date_from": "2020-01-01", "date_to": "2020-12-31"}
    o = (await admin.get(f"{D}/overview", params=old)).json()
    assert (o["leads"], o["income"], o["payroll"], o["ads"], o["graduates"]) == (
        0, "0.00", "0.00", "0.00", 0,
    )  # fmt: skip
    assert (o["active_students"], o["active_cohorts"]) == (3, 2)  # state, not a period
    leads_total = await total(admin, L, **old)
    assert leads_total == 0


async def test_by_month_adds_up_to_the_overview(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    await world(admin, browser)
    r = (await admin.get(f"{D}/by-month")).json()
    items = r["items"]
    assert len(items) == 12
    o = (await admin.get(f"{D}/overview")).json()
    assert sum(Decimal(i["income"]) for i in items) == Decimal(o["income"])
    assert sum(Decimal(i["payroll"]) for i in items) == Decimal(o["payroll"])
    assert sum(Decimal(i["ads"]) for i in items) == Decimal(o["ads"])
    assert sum(i["leads"] for i in items) == o["leads"]
    last = items[-1]
    assert (last["income"], last["payroll"], last["ads"], last["profit"]) == (
        "1600.00", "400.00", "1200.00", "0.00",
    )  # fmt: skip
    assert (last["new_students"], last["leads"]) == (6, 5)
    assert all(
        Decimal(i["profit"]) == Decimal(i["income"]) - Decimal(i["ads"]) - Decimal(i["payroll"])
        for i in items
    )
    assert all(i["income"] == "0.00" for i in items[:-1])


async def test_by_course_adds_up_to_the_overview(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    await world(admin, browser)
    items = (await admin.get(f"{D}/by-course")).json()["items"]
    o = (await admin.get(f"{D}/overview")).json()
    assert sum(Decimal(i["income"]) for i in items) == Decimal(o["income"])
    assert sum(i["graduates"] for i in items) == o["graduates"]
    by_name = {i["course_name"]: i for i in items}
    assert by_name["Курс Live"]["income"] == "1000.00" and by_name["Курс Live"]["students"] == 2
    assert by_name["Курс F"]["income"] == "300.00" and by_name["Курс F"]["graduates"] == 1
    assert by_name["Курс Набор"]["students"] == 0


# ---- #22 ---------------------------------------------------------------------------------


async def test_bug_22_instructor_card_equals_the_cohort_lists(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    w = await world(admin, browser)
    uid, mine = w["instructor"], w["instructor_client"]
    card = (await admin.get(f"{I}/{uid}")).json()
    own_card = (await mine.get(f"{I}/{uid}")).json()  # the same card in the instructor's cabinet
    assert {k: own_card[k] for k in ("cohorts", "students", "income", "paid_out")} == {
        k: card[k] for k in ("cohorts", "students", "income", "paid_out")
    }
    # the instructor's own cohort list (what they see in their cabinet)
    listed = (await mine.get(C, params={"page_size": 100})).json()
    assert card["cohorts"] == listed["total"] == len(card["cohorts_list"]) == 2
    assert card["active_cohorts"] == sum(1 for c in listed["items"] if c["status"] == "активный")
    assert card["students"] == sum(c["fill"]["enrolled"] for c in listed["items"])
    # income = the confirmed payments of those cohorts; paid out = the payouts list
    confirmed = Decimal(0)
    for c in listed["items"]:
        r = await admin.get(P, params={"status": "подтверждено", "cohort_id": c["id"]})
        confirmed += Decimal(r.json()["summary"]["confirmed"])
    assert (
        Decimal(card["income"])
        == confirmed
        == sum(Decimal(c["income"]) for c in card["cohorts_list"])
    )
    assert (
        card["paid_out"] == (await admin.get(PO, params={"instructor_id": str(uid)})).json()["sum"]
    )


# ---- rights and scope --------------------------------------------------------------------


async def test_instructor_has_no_report_money(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    w = await world(admin, browser)
    mine = w["instructor_client"]
    for url in (
        f"{D}/overview",
        f"{D}/by-month",
        f"{D}/by-course",
        f"{D}/by-month/export",
        ML,
        f"{ML}/export",
        f"{G}/students",
        f"{G}/courses",
        "/api/v1/employment",
        "/api/v1/metrics/finance",
    ):
        assert (await mine.get(url)).status_code == 403, url


async def test_instructor_is_denied_even_with_the_rights_in_the_matrix(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    from tests.edu import instructor_rights

    w = await world(admin, browser)
    async with instructor_rights(dashboard="change", master_list="change", graduates="change"):
        mine = w["instructor_client"]
        for url in (f"{D}/overview", ML, f"{G}/students"):
            assert (await mine.get(url)).status_code == 403, url


async def test_branch_manager_sees_only_their_branch_and_cannot_toggle_out(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient], login_as: SignedIn
) -> None:
    await world(admin, browser)
    from tests.money import manager_role

    mgr = await login_as("mgr", await manager_role(), branch="Душанбе")
    o = (await mgr.get(f"{D}/overview")).json()
    dushanbe = (await admin.get(f"{D}/overview", params=await _branch_params("Душанбе"))).json()
    assert o == dushanbe
    assert o["leads"] == 4 and o["income"] == "1300.00" and o["ads"] == "1000.00"
    # the toggle can narrow to their own branch, never reach into another
    own = (await mgr.get(f"{D}/overview", params=await _branch_params("Душанбе"))).json()
    assert own == o
    other = await _branch_params("Истаравшан")
    for url in (f"{D}/overview", f"{D}/by-month", f"{D}/by-course", ML, f"{G}/students"):
        assert (await mgr.get(url, params=other)).status_code == 404, url
    months = (await mgr.get(f"{D}/by-month")).json()["items"]
    assert months[-1]["income"] == "1300.00" and months[-1]["leads"] == 4


async def test_no_dashboard_right_no_dashboard(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    nobody = await login_as("nobody", await make_role("Пусто", {"students": "view"}))
    for url in (f"{D}/overview", ML, f"{G}/students", "/api/v1/employment"):
        assert (await nobody.get(url)).status_code == 403, url
