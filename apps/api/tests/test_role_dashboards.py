"""Role dashboards: the numbers of every card against independent SQL, the alerts and their edge
cases, rights per card (a hidden card's endpoint still enforces them), and the per-user layout."""

import uuid
from datetime import timedelta
from typing import Any

import httpx

from app.core.db import sessionmaker
from app.metrics import dash
from app.metrics.money import today
from app.permissions import MANAGER_DEFAULT
from tests.conftest import SignedIn, branch_id, make_role, sql
from tests.edu import make_cohort, make_course, make_room
from tests.money import add_months, enroll, pay, running_cohort, this_month
from tests.sales import make_lead

K = "/api/v1/dashboard/cards"
PREF = "/api/v1/me/preferences/dashboard"
A = "/api/v1/audit"


def v(version: int) -> dict[str, str]:
    return {"X-Record-Version": str(version)}


async def recruiting(
    c: httpx.AsyncClient,
    name: str,
    *,
    days: int = 10,
    capacity: int = 20,
    branch: str = "Душанбе",
    price: int = 500,
) -> dict[str, Any]:
    return await make_cohort(
        c,
        await make_course(f"Курс {name}", price),
        await make_room(branch, f"R-{name}"),
        branch=branch,
        start=today() + timedelta(days=days),
        weeks=8,
        capacity=capacity,
    )


async def manager(login_as: SignedIn, login: str = "mgr", branch: str | None = "Душанбе") -> Any:
    role = await make_role("Менеджер (тест)", dict(MANAGER_DEFAULT))
    return await login_as(login, role, branch=branch)


async def only(c: httpx.AsyncClient, path: str, **params: Any) -> dict[str, Any]:
    r = await c.get(f"{K}/{path}", params=params)
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


# ---- month hero ------------------------------------------------------------------------------


async def test_month_hero_matches_sql(admin: httpx.AsyncClient) -> None:
    cohort = await running_cohort(admin, name="M", back=1)
    e1 = await enroll(admin, cohort, "Один")
    e2 = await enroll(admin, cohort, "Два")
    prev_first = add_months(this_month(), -1)
    await pay(admin, e1, month=2, confirm=True)
    await pay(admin, e2, month=1, confirm=True, paid_at=prev_first)
    await pay(admin, e1, month=1, confirm=True, paid_at=prev_first)
    await pay(admin, e2, month=2)  # pending: not collected

    d = await only(admin, "month")
    first = this_month()
    income = (
        await sql(
            "SELECT COALESCE(sum(amount), 0) FROM payment WHERE status = 'подтверждено' "
            "AND paid_at >= :f AND paid_at <= :t",
            f=first,
            t=today(),
        )
    )[0][0]
    prev = (
        await sql(
            "SELECT COALESCE(sum(amount), 0) FROM payment WHERE status = 'подтверждено' "
            "AND paid_at >= :f AND paid_at <= :t",
            f=prev_first,
            t=min(prev_first + timedelta(days=today().day - 1), first - timedelta(days=1)),
        )
    )[0][0]
    confirmed_month_2 = (
        await sql("SELECT sum(amount) FROM payment WHERE status = 'подтверждено' AND month_no = 2")
    )[0][0]
    all_confirmed = (await sql("SELECT sum(amount) FROM payment WHERE status = 'подтверждено'"))[0][
        0
    ]
    assert float(d["expected"]) == 1000.0  # two enrollments x the month's price
    assert d["collected"] == str(confirmed_month_2) and float(d["collected"]) == 500.0
    assert d["collection_pct"] == 50.0
    assert float(d["debt"]) == 2 * 2 * 500 - float(all_confirmed)
    assert d["debtors"] == 1  # one student paid both months
    assert float(d["income"]) == float(income) == 500.0
    assert float(d["income_prev"]) == float(prev) == 1000.0
    assert d["income_change_pct"] == -50.0
    assert float(d["profit"]) == float(income)
    created = (await sql("SELECT count(*) FROM student"))[0][0]
    assert d["new_students"] == created == 2 and d["new_students_change"] == 2


async def test_month_hero_empty_and_branch_scope(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    d = await only(admin, "month")
    assert d["expected"] == "0.00" and d["collection_pct"] == 0.0
    assert d["income_change_pct"] is None  # nothing to compare with, not +inf
    other = await running_cohort(admin, name="I", back=0, branch="Истаравшан")
    await enroll(admin, other, "Чужой", branch="Истаравшан")
    mine = await running_cohort(admin, name="D", back=0)
    await enroll(admin, mine, "Свой")
    mgr = await manager(login_as)
    assert float((await only(mgr, "month"))["expected"]) == 500.0
    assert float((await only(admin, "month"))["expected"]) == 1000.0
    ist = str(await branch_id("Истаравшан"))
    assert float((await only(admin, "month", branch_id=ist))["expected"]) == 500.0
    assert (await mgr.get(f"{K}/month", params={"branch_id": ist})).status_code == 404


# ---- timeline and seats ----------------------------------------------------------------------


async def test_timeline_window_status_scope_and_over_capacity(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    live = await running_cohort(admin, name="Live", back=0, capacity=1)
    await enroll(admin, live, "Раз")
    await enroll(admin, live, "Два")  # soft capacity: allowed, shown as over
    soon = await recruiting(admin, "Soon", days=20)
    await recruiting(admin, "Far", days=200)
    gone = await recruiting(admin, "Gone", days=15)
    await sql("UPDATE cohort SET status = 'отменён' WHERE id = :i", i=gone["id"])
    other = await recruiting(admin, "Ist", days=12, branch="Истаравшан")

    d = await only(admin, "timeline")
    codes = [i["code"] for i in d["items"]]
    assert set(codes) == {live["code"], soon["code"], other["code"]}
    by = {i["code"]: i for i in d["items"]}
    assert by[live["code"]]["over_capacity"] == {"enrolled": 2, "capacity": 1}
    assert by[live["code"]]["fill_pct"] == 200
    assert by[soon["code"]]["over_capacity"] is None and by[soon["code"]]["enrolled"] == 0
    enrolled_sql = (
        await sql(
            "SELECT count(*) FROM enrollment WHERE cohort_id = :c AND status <> 'отчислен'",
            c=uuid.UUID(live["id"]),
        )
    )[0][0]
    assert by[live["code"]]["enrolled"] == enrolled_sql
    assert d["window_start"] == this_month().isoformat() and d["today"] == today().isoformat()
    mgr = await manager(login_as)
    assert {i["code"] for i in (await only(mgr, "timeline"))["items"]} == {
        live["code"],
        soon["code"],
    }


async def test_seats_free_never_negative_and_only_recruiting(
    admin: httpx.AsyncClient,
) -> None:
    full = await recruiting(admin, "Full", days=3, capacity=1)
    await enroll(admin, full, "А")
    await enroll(admin, full, "Б")
    free = await recruiting(admin, "Free", days=5, capacity=12)
    await enroll(admin, free, "В")
    await running_cohort(admin, name="Run", back=0)
    items = (await only(admin, "seats"))["items"]
    assert [i["code"] for i in items] == [full["code"], free["code"]]
    assert items[0]["free"] == 0 and items[0]["over_capacity"] == {"enrolled": 2, "capacity": 1}
    assert items[1]["free"] == 11 and items[1]["enrolled"] == 1


# ---- alerts ----------------------------------------------------------------------------------


async def alerts(c: httpx.AsyncClient, **params: Any) -> dict[str, dict[str, str]]:
    items = (await only(c, "attention", **params))["items"]
    return {a["key"]: a for a in items}


async def test_alert_overpaid_months(admin: httpx.AsyncClient) -> None:
    cohort = await running_cohort(admin, name="O", back=1)
    e1 = await enroll(admin, cohort, "Переплатил")
    e2 = await enroll(admin, cohort, "Ровно")
    p1 = await pay(admin, e1, month=2, confirm=True)
    await pay(admin, e2, month=2, confirm=True)  # exactly the price: not an overpayment
    assert "overpaid" not in await alerts(admin)
    await sql("UPDATE payment SET amount = 1200 WHERE id = :i", i=uuid.UUID(p1["id"]))
    a = (await alerts(admin))["overpaid"]
    assert a["title"].startswith(f"{cohort['code']}: переплата 700 TJS за 2-й месяц")
    assert a["severity"] == "danger" and a["href"] == f"/cohorts/{cohort['id']}"
    async with sessionmaker() as db:
        rows = await dash.overpaid_months(db, [])
    independent = await sql(
        "SELECT e.id, p.month_no, sum(p.amount) - c.price_month FROM payment p "
        "JOIN enrollment e ON e.id = p.enrollment_id JOIN cohort c ON c.id = e.cohort_id "
        "GROUP BY e.id, p.month_no, c.price_month HAVING sum(p.amount) > c.price_month"
    )
    assert [(str(r["enrollment_id"]), r["month_no"], r["overpaid"]) for r in rows] == [
        (str(i), m, o) for i, m, o in independent
    ]
    # a pending payment on top of a full month counts too (entered = pending + confirmed)
    await sql("UPDATE payment SET amount = 500 WHERE id = :i", i=uuid.UUID(p1["id"]))
    await sql(
        "INSERT INTO payment (enrollment_id, month_no, amount, method, paid_at, idempotency_key) "
        "VALUES (:e, 2, 100, 'alif', :d, gen_random_uuid())",
        e=uuid.UUID(e1),
        d=today(),
    )
    assert "100" in (await alerts(admin))["overpaid"]["title"]
    # two months over: one line that says how many
    await sql("UPDATE payment SET amount = 600 WHERE enrollment_id = :e", e=uuid.UUID(e2))
    assert (await alerts(admin))["overpaid"]["title"] == "Переплаты в 2 месяцах оплат"


async def test_alert_unmarked_threshold_is_five_days(admin: httpx.AsyncClient) -> None:
    cohort = await running_cohort(admin, name="U", back=2)
    await enroll(admin, cohort, "Без отметок")
    a = (await alerts(admin))["unmarked"]
    assert a["title"] == "1 поток без отметок 5+ дней" and cohort["code"] in a["hint"]
    async with sessionmaker() as db:
        where: list[Any] = []
        assert [c["cohort_code"] for c in await dash.unmarked_cohorts(db, where)] == [
            cohort["code"]
        ]
        # a lesson younger than the threshold is not an alert; an older one is
        assert await dash.unmarked_cohorts(db, where, min_days=400) == []
        assert len(await dash.unmarked_cohorts(db, where, min_days=1)) == 1


async def test_alert_pending_payments_count_sum_and_age(admin: httpx.AsyncClient) -> None:
    cohort = await running_cohort(admin, name="P", back=1)
    e1 = await enroll(admin, cohort, "Один")
    e2 = await enroll(admin, cohort, "Два")
    assert "pending" not in await alerts(admin)
    p1 = await pay(admin, e1, month=2, amount=200)
    await pay(admin, e2, month=2, amount=300)
    await pay(admin, e2, month=1, amount=500, confirm=True)  # confirmed: not pending
    await sql(
        "UPDATE payment SET created_at = now() - interval '3 days' WHERE id = :i",
        i=uuid.UUID(p1["id"]),
    )
    a = (await alerts(admin))["pending"]
    assert a["title"] == "2 оплаты ждут подтверждения"
    assert a["hint"] == "500 TJS · старшая — 3 дня"
    assert a["href"] == "/payments?status=ожидает"
    n, total = (await sql("SELECT count(*), sum(amount) FROM payment WHERE status = 'ожидает'"))[0]
    async with sessionmaker() as db:
        got = await dash.pending_payments(db, [])
    assert (got["count"], got["sum"], got["oldest_days"]) == (n, total, 3)


async def test_alert_starting_soon_underfilled_edges(admin: httpx.AsyncClient) -> None:
    low = await recruiting(admin, "Low", days=12, capacity=20)
    await enroll(admin, low, "Один")
    half = await recruiting(admin, "Half", days=5, capacity=4)  # exactly 50 %: not under-filled
    await enroll(admin, half, "А")
    await enroll(admin, half, "Б")
    await recruiting(admin, "Late", days=20, capacity=20)  # beyond 14 days
    edge = await recruiting(admin, "Edge", days=14, capacity=10)  # day 14 counts
    got = await alerts(admin)
    assert set(got) == {f"soon:{low['id']}", f"soon:{edge['id']}"}
    a = got[f"soon:{low['id']}"]
    assert a["title"] == f"{low['code']} стартует через 12 дней"
    assert a["hint"] == "Занято 1 из 20 — нужна реклама" and a["severity"] == "info"


async def test_alerts_follow_the_rights(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    cohort = await running_cohort(admin, name="R", back=1)
    e = await enroll(admin, cohort, "Студент")
    p = await pay(admin, e, month=2, confirm=True)
    await sql("UPDATE payment SET amount = 900 WHERE id = :i", i=uuid.UUID(p["id"]))
    await pay(admin, e, month=1, amount=100)
    await recruiting(admin, "Soon", days=3)
    no_money = await make_role("Без денег", {"dashboard": "view", "cohorts": "view"})
    c = await login_as("nomoney", no_money)
    got = await alerts(c)
    assert "overpaid" not in got and "pending" not in got
    assert "unmarked" in got and any(k.startswith("soon:") for k in got)
    no_cohorts = await make_role("Только деньги", {"dashboard": "view", "payments": "view"})
    c2 = await login_as("onlymoney", no_cohorts)
    got2 = await alerts(c2)
    assert {"overpaid", "pending"} <= set(got2)
    assert "unmarked" not in got2 and not any(k.startswith("soon:") for k in got2)


# ---- demand ----------------------------------------------------------------------------------


async def test_demand_windows_trend_no_course_and_scope(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    py = await make_course("Python", 500)
    ai = await make_course("AI", 500)
    days = {"now": 2, "old": 40, "edge_cur": 29, "edge_prev": 30, "too_old": 60}

    async def lead(name: str, course: uuid.UUID | None, age: int, branch: str = "Душанбе") -> None:
        kw: dict[str, Any] = {"course_id": str(course)} if course else {}
        made = await make_lead(admin, name, branch=branch, **kw)
        await sql(
            "UPDATE lead SET created_at = now() - make_interval(days => :d) WHERE id = :i",
            d=age,
            i=uuid.UUID(made["id"]),
        )

    for i in range(3):
        await lead(f"Py{i}", py, days["now"])
    await lead("Py-prev", py, days["old"])
    await lead("Py-prev2", py, days["edge_prev"])
    await lead("Py-edge", py, days["edge_cur"])
    await lead("Py-too-old", py, days["too_old"])
    await lead("AI-new", ai, 1)
    await lead("Nobody", None, 3)
    await lead("Nobody2", None, 90)
    await lead("Ist", py, 1, branch="Истаравшан")

    d = await only(admin, "demand")
    rows = {r["course_name"]: r for r in d["items"]}
    assert rows["Python"]["leads"] == 5 and rows["Python"]["previous"] == 2
    assert rows["Python"]["change_pct"] == 150.0
    assert rows["AI"]["leads"] == 1 and rows["AI"]["previous"] == 0
    assert rows["AI"]["change_pct"] is None  # new demand: no percentage against zero
    assert d["no_course"] == 1
    sql_cur = (
        await sql(
            "SELECT count(*) FROM lead WHERE course_id IS NOT NULL "
            "AND created_at >= now() - interval '30 days'"
        )
    )[0][0]
    assert sum(r["leads"] for r in d["items"]) == sql_cur - 0
    mgr = await manager(login_as)
    mine = {r["course_name"]: r for r in (await only(mgr, "demand"))["items"]}
    assert mine["Python"]["leads"] == 4  # the other branch's lead is not counted
    assert (await only(mgr, "demand"))["no_course"] == 1


# ---- income per branch -----------------------------------------------------------------------


async def test_branch_months_match_sql(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    d_cohort = await running_cohort(admin, name="D", back=2)
    i_cohort = await running_cohort(admin, name="I", back=2, branch="Истаравшан", price=300)
    ed = await enroll(admin, d_cohort, "Д")
    ei = await enroll(admin, i_cohort, "И", branch="Истаравшан")
    await pay(admin, ed, month=1, confirm=True, paid_at=add_months(this_month(), -2))
    await pay(admin, ed, month=3, confirm=True)
    await pay(admin, ei, month=3, amount=300, confirm=True)
    await pay(admin, ei, month=2, amount=300)  # pending: no income

    data = await only(admin, "branches")
    assert [s["name"] for s in data["series"]] == ["Истаравшан", "Душанбе"][::-1]
    assert len(data["months"]) == 6
    by = {s["name"]: [float(x) for x in s["values"]] for s in data["series"]}
    assert by["Душанбе"][-3] == 500.0 and by["Душанбе"][-1] == 500.0
    assert by["Истаравшан"][-1] == 300.0 and sum(by["Истаравшан"]) == 300.0
    total_sql = (await sql("SELECT sum(amount) FROM payment WHERE status = 'подтверждено'"))[0][0]
    assert sum(sum(v) for v in by.values()) == float(total_sql)
    mgr = await manager(login_as)
    only_mine = (await only(mgr, "branches"))["series"]
    assert [s["name"] for s in only_mine] == ["Душанбе"]


# ---- manager's queues and week ---------------------------------------------------------------


async def test_queues_counts_and_permission_filtering(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    cohort = await running_cohort(admin, name="Q", back=1)
    e1 = await enroll(admin, cohort, "Должник")
    await pay(admin, e1, month=2, amount=200)  # pending
    await enroll(admin, cohort, "Другой должник")
    for i, (ago, status) in enumerate([(2, "перезвонить"), (0, "перезвонить"), (0, "не звонили")]):
        made = await make_lead(admin, f"Лид {i}")
        await sql(
            "UPDATE lead SET call_status = :s, next_contact_at = now() - make_interval(days => :d)"
            " WHERE id = :i",
            s=status,
            d=ago,
            i=uuid.UUID(made["id"]),
        )
    # a lead of the other branch is not the manager's
    await make_lead(admin, "Чужой", branch="Истаравшан")
    mgr = await manager(login_as)
    tiles = {t["key"]: t for t in (await only(mgr, "queues"))["tiles"]}
    assert tiles["callbacks"]["count"] == 2 and tiles["callbacks"]["overdue"] == 1
    assert tiles["debtors"]["count"] == 2
    debt_sql = (
        2 * 2 * 500  # two enrollments, two months each, nothing confirmed
    )
    assert float(tiles["debtors"]["sum"]) == debt_sql
    assert tiles["pending"]["count"] == 1 and float(tiles["pending"]["sum"]) == 200.0
    assert tiles["new_leads"]["count"] == 3
    # no payments right: the money tiles are not in the answer at all
    leads_only = await make_role("Лиды", {"leads": "view", "dashboard": "view"})
    c = await login_as("leadsonly", leads_only, branch="Душанбе")
    assert [t["key"] for t in (await only(c, "queues"))["tiles"]] == ["callbacks", "new_leads"]
    money_only = await make_role("Деньги", {"payments": "view"})
    c2 = await login_as("moneyonly", money_only)
    assert [t["key"] for t in (await only(c2, "queues"))["tiles"]] == ["debtors", "pending"]


async def test_call_queue_rows_and_rights(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    made = await make_lead(admin, "Мадина", phone="900000001")
    await sql(
        "UPDATE lead SET call_status = 'перезвонить', next_contact_at = now() WHERE id = :i",
        i=uuid.UUID(made["id"]),
    )
    mgr = await manager(login_as)
    data = await only(mgr, "call-queue")
    assert data["count"] == 1 and data["items"][0]["full_name"] == "Мадина"
    assert data["items"][0]["phone"].endswith("900000001")
    no_leads = await make_role("Без лидов", {"dashboard": "view"})
    c = await login_as("noleads", no_leads)
    assert (await c.get(f"{K}/call-queue")).status_code == 403


async def test_week_summary_matches_sql_and_hides_money(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    cohort = await running_cohort(admin, name="W", back=1)
    e1 = await enroll(admin, cohort, "Недельный", since=today())
    await pay(admin, e1, month=2, amount=500, confirm=True)
    await pay(admin, e1, month=1, amount=500, confirm=True, paid_at=today() - timedelta(days=20))
    for i in range(2):
        await make_lead(admin, f"Лид {i}")
    old = await make_lead(admin, "Старый")
    await sql(
        "UPDATE lead SET created_at = now() - interval '9 days' WHERE id = :i",
        i=uuid.UUID(old["id"]),
    )
    d = await only(admin, "week")
    paid_sql = (
        await sql(
            "SELECT count(*), sum(amount) FROM payment WHERE status = 'подтверждено' "
            "AND paid_at >= :s",
            s=today() - timedelta(days=6),
        )
    )[0]
    assert (d["payments_count"], float(d["payments_sum"])) == (paid_sql[0], float(paid_sql[1]))
    assert d["leads"] == 2 and d["leads_change"] == 2 - 1
    assert d["enrolled"] == 1
    no_money = await make_role("Лиды и дашборд", {"dashboard": "view", "leads": "view"})
    c = await login_as("nomoneyweek", no_money)
    got = await only(c, "week")
    assert got["payments_sum"] is None and got["debt"] is None and got["leads"] == 2
    no_leads = await make_role("Дашборд и оплаты", {"dashboard": "view", "payments": "view"})
    c2 = await login_as("noleadsweek", no_leads)
    got2 = await only(c2, "week")
    assert got2["leads"] is None and got2["payments_count"] == 1


# ---- rights of every card endpoint -----------------------------------------------------------

ENDPOINTS = {
    "month": "payments",
    "timeline": "cohorts",
    "attention": "dashboard",
    "demand": "leads",
    "branches": "payments",
    "call-queue": "leads",
    "seats": "cohorts",
    "week": "dashboard",
}


async def test_card_endpoints_enforce_rights(
    admin: httpx.AsyncClient,
    login_as: SignedIn,
    client: httpx.AsyncClient,
) -> None:
    ins = await login_as("ins", "instructor", branch="Душанбе")
    for path in [*ENDPOINTS, "queues"]:
        assert (await client.get(f"{K}/{path}")).status_code == 401, path
        assert (await ins.get(f"{K}/{path}")).status_code == 403, path
        assert (await admin.get(f"{K}/{path}")).status_code == 200, path
    for path, section in ENDPOINTS.items():
        others = {s: "change" for s in ENDPOINTS.values() if s != section}
        role = await make_role(f"Без {section} {path}", others)
        c = await login_as(f"no-{path}", role)
        assert (await c.get(f"{K}/{path}")).status_code == 403, (path, section)
    nothing = await make_role("Ничего", {"rooms": "view"})
    c = await login_as("nothing", nothing)
    assert (await c.get(f"{K}/queues")).status_code == 403


# ---- layout preferences ----------------------------------------------------------------------


async def layout(c: httpx.AsyncClient) -> dict[str, Any]:
    r = await c.get(PREF)
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def ids(data: dict[str, Any], *, visible: bool | None = None) -> list[str]:
    return [c["id"] for c in data["cards"] if visible is None or c["visible"] is visible]


async def test_defaults_per_role(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    sa = await layout(admin)
    assert sa["version"] == 0 and sa["is_default"] is True
    assert ids(sa, visible=True) == [
        "academy_goal",
        "month_hero",
        "goals",
        "demand",
        "timeline",
        "attention",
        "branches_months",
        "courses_income",
        "overview",
        "notes",
    ]
    assert set(ids(sa, visible=False)) == {"queues", "call_queue", "seats", "week"}
    mgr = await manager(login_as)
    m = await layout(mgr)
    assert ids(m, visible=True) == ["academy_goal", "queues", "call_queue", "seats", "week"]
    # the superadmin-only cards are not offered to a manager at all
    assert "goals" not in ids(m) and "notes" not in ids(m)
    assert all(c["title"] for c in m["cards"])


async def test_catalog_follows_permissions(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    leads_only = await make_role("Только лиды", {"leads": "view", "dashboard": "view"})
    c = await login_as("l", leads_only)
    got = set(ids(await layout(c)))
    assert got == {
        "academy_goal",
        "demand",
        "attention",
        "queues",
        "call_queue",
        "week",
        "overview",
    }
    ins = await login_as("ins", "instructor", branch="Душанбе")
    assert ids(await layout(ins)) == []  # an instructor has no dashboard


async def test_save_order_hidden_version_and_cleaning(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    mgr = await manager(login_as)
    r = await mgr.put(
        PREF, json={"order": ["week", "queues"], "hidden": ["queues"]}, no_version=True
    )
    assert r.status_code == 428  # the version header is required
    body = {
        "order": ["week", "nope", "goals", "queues", "week"],  # unknown, forbidden, duplicate
        "hidden": ["queues", "notes", "nope"],
    }
    r = await mgr.put(PREF, json=body, headers=v(0))
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved["version"] == 1 and saved["is_default"] is False
    assert ids(saved)[:2] == ["week", "queues"]
    assert set(ids(saved)) == set(ids(await layout(mgr)))  # complete, nothing foreign
    assert "goals" not in ids(saved) and "notes" not in ids(saved)
    assert ids(saved, visible=False)[0] == "queues"
    stored = (await sql("SELECT dashboard FROM user_pref"))[0][0]
    assert "goals" not in stored["order"] and "nope" not in stored["hidden"]
    # stale version: 409 with the current layout
    r = await mgr.put(PREF, json={"order": ["seats"], "hidden": []}, headers=v(0))
    assert r.status_code == 409 and r.json()["code"] == "stale_version"
    assert r.json()["params"]["current"]["version"] == 1
    r = await mgr.put(PREF, json={"order": ["seats"], "hidden": []}, headers=v(1))
    assert r.status_code == 200 and r.json()["version"] == 2 and ids(r.json())[0] == "seats"
    # the same body again is a harmless retry, not a new version
    r = await mgr.put(PREF, json={"order": ["seats"], "hidden": []}, headers=v(1))
    assert r.status_code == 200 and r.json()["version"] == 2
    # an unknown field is rejected
    r = await mgr.put(PREF, json={"order": [], "hidden": [], "user_id": "x"}, headers=v(2))
    assert r.status_code == 422


async def test_reset_returns_defaults_and_is_audited(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    await admin.put(PREF, json={"order": ["notes"], "hidden": ["month_hero"]}, headers=v(0))
    assert ids(await layout(admin))[0] == "notes"
    r = await admin.put(PREF, json={"reset": True}, headers=v(1))
    assert r.status_code == 200 and r.json()["is_default"] is True
    assert ids(r.json())[0] == "academy_goal" and "month_hero" in ids(r.json(), visible=True)
    actions = [
        x[0]
        for x in await sql("SELECT action FROM audit_log WHERE entity = 'user_pref' ORDER BY id")
    ]
    assert actions == ["dashboard_pref.update", "dashboard_pref.reset"]
    texts = [
        i["text"] for i in (await admin.get(A, params={"entity": "user_pref"})).json()["items"]
    ]
    assert sorted(t.split(": ", 1)[1] for t in texts) == [
        "изменены настройки дашборда",
        "сброшены настройки дашборда",
    ]


async def test_preferences_are_own_only(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    other = await login_as("second", "superadmin")
    await admin.put(PREF, json={"order": ["notes"], "hidden": ["goals"]}, headers=v(0))
    assert ids(await layout(other))[0] == "academy_goal"  # not the first user's layout
    assert (await layout(other))["version"] == 0
    r = await other.put(PREF, json={"order": ["timeline"], "hidden": []}, headers=v(0))
    assert r.status_code == 200  # its own first save is version 0 whatever the other did
    assert ids(await layout(admin))[0] == "notes"
    # there is no way to name another user: ids in the path are 404/405
    uid = str((await sql("SELECT id FROM app_user WHERE login = 'second'"))[0][0])
    assert (await admin.get(f"{PREF}/{uid}")).status_code in (404, 405)
    assert (await admin.put(f"{PREF}/{uid}", json={}, headers=v(1))).status_code in (404, 405)
    rows = await sql("SELECT count(*) FROM user_pref")
    assert rows[0][0] == 2


async def test_layout_cannot_grant_what_the_role_lacks(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    role = await make_role("Меняющийся", {"dashboard": "view", "payments": "view"})
    c = await login_as("changing", role)
    assert "month_hero" in ids(await layout(c))
    await c.put(PREF, json={"order": ["month_hero"], "hidden": ["week"]}, headers=v(0))
    await sql("DELETE FROM role_permission WHERE role_id = :r AND section = 'payments'", r=role)
    saved = await layout(c)
    assert "month_hero" not in ids(saved)  # a stored id the user may no longer have is ignored
    assert (await c.get(f"{K}/month")).status_code == 403  # and its endpoint refuses anyway
    # a card hidden in the layout is still protected: hiding is not a permission change
    await c.put(PREF, json={"order": [], "hidden": ["attention"]}, headers=v(saved["version"]))
    assert (await c.get(f"{K}/attention")).status_code == 200
    assert "attention" in ids(await layout(c), visible=False)
