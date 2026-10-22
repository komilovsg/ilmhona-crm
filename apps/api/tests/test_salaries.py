"""Stage 2: instructor rates, payout schedule, payouts (#9), cards (#17), own-data-only (owner)."""

import asyncio
import uuid
from collections.abc import Callable
from datetime import date
from io import BytesIO
from typing import Any

import httpx
import pytest
from openpyxl import load_workbook
from sqlalchemy.exc import IntegrityError

from app.audit.sentences import Entry, sentence
from app.cohorts.status import today
from tests.conftest import SignedIn, make_role, make_user, sign_in, sql
from tests.money import (
    PO,
    I,
    S,
    add_months,
    enroll,
    make_payout,
    manager_role,
    pay,
    running_cohort,
    this_month,
)


async def instructor(
    browser: Callable[[], httpx.AsyncClient], login: str, branch: str | None = "Душанбе"
) -> tuple[uuid.UUID, httpx.AsyncClient]:
    uid = await make_user(login, "instructor", branch=branch)
    c = browser()
    await sign_in(c, login)
    return uid, c


async def set_default_rate(admin: httpx.AsyncClient, uid: uuid.UUID, rate: int) -> None:
    r = await admin.patch(f"{I}/{uid}", json={"default_rate": str(rate)})
    assert r.status_code == 200, r.text


def schedule_of(body: dict[str, Any], code: str) -> list[dict[str, Any]]:
    return [r for r in body["items"] if r["cohort_code"] == code]


# ---- rate ------------------------------------------------------------------------------


async def test_cohort_rate_defaults_from_the_instructor_and_is_editable(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    uid, _ = await instructor(browser, "ins")
    await set_default_rate(admin, uid, 300)
    cohort = await running_cohort(admin, instructor_id=str(uid))
    rows = (await admin.get(S, params={"month": "all"})).json()
    assert {r["rate"] for r in schedule_of(rows, cohort["code"])} == {"300.00"}
    # changing the default later does not rewrite cohorts that already exist
    await set_default_rate(admin, uid, 999)
    assert {r["rate"] for r in (await admin.get(S, params={"month": "all"})).json()["items"]} == {
        "300.00"
    }
    r = await admin.patch(f"{S}/cohorts/{cohort['id']}/rate", json={"instructor_rate": "450.50"})
    assert r.status_code == 200 and r.json()["instructor_rate"] == "450.50"
    assert {r["rate"] for r in (await admin.get(S, params={"month": "all"})).json()["items"]} == {
        "450.50"
    }
    # a new instructor on the cohort brings their own default
    other = await make_user("ins2", "instructor", branch="Душанбе")
    await set_default_rate(admin, other, 700)
    await admin.patch(f"/api/v1/cohorts/{cohort['id']}", json={"instructor_id": str(other)})
    assert {r["rate"] for r in (await admin.get(S, params={"month": "all"})).json()["items"]} == {
        "700.00"
    }
    # validation and rights
    assert (await admin.patch(f"{I}/{uid}", json={"default_rate": "-1"})).status_code == 422
    assert (
        await admin.patch(f"{S}/cohorts/{cohort['id']}/rate", json={"instructor_rate": "-1"})
    ).status_code == 422
    with pytest.raises(IntegrityError):
        await sql("UPDATE cohort SET instructor_rate = -1 WHERE id = :i", i=cohort["id"])


async def test_rate_version_conflicts(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    uid, _ = await instructor(browser, "ins")
    cohort = await running_cohort(admin, instructor_id=str(uid))
    version = (await sql("SELECT version FROM cohort WHERE id = :i", i=cohort["id"]))[0][0]
    ok = await admin.patch(f"{S}/cohorts/{cohort['id']}/rate", json={"instructor_rate": "100"})
    assert ok.status_code == 200
    stale = await admin.patch(
        f"{S}/cohorts/{cohort['id']}/rate",
        json={"instructor_rate": "200"},
        headers={"X-Record-Version": str(version)},
    )
    assert (stale.status_code, stale.json()["code"]) == (409, "stale_version")
    # the default rate of the instructor is versioned too
    await set_default_rate(admin, uid, 10)
    stale = await admin.patch(
        f"{I}/{uid}", json={"default_rate": "20"}, headers={"X-Record-Version": "1"}
    )
    assert (stale.status_code, stale.json()["code"]) == (409, "stale_version")


# ---- schedule ----------------------------------------------------------------------------


async def test_schedule_is_every_month_the_cohort_runs_times_the_rate(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    uid, _ = await instructor(browser, "ins")
    await set_default_rate(admin, uid, 1000)
    cohort = await running_cohort(admin, back=1, weeks=13, instructor_id=str(uid))
    months = cohort["months"]
    rows = (await admin.get(S, params={"month": "all"})).json()
    mine = schedule_of(rows, cohort["code"])
    assert len(mine) == months
    assert [r["period"] for r in mine][0] == add_months(this_month(), -1).isoformat()
    s = rows["summary"]
    assert s["total_schedule"] == f"{1000 * months}.00"
    assert (s["fund_month"], s["paid_total"], s["paid_month"], s["due_month"]) == (
        "1000.00",
        "0.00",
        "0.00",
        "1000.00",
    )
    assert s["overdue"] == "1000.00"  # last month is behind us and unpaid
    # default month = this month: one row; states by period
    now = (await admin.get(S)).json()
    assert [r["period"] for r in now["items"]] == [this_month().isoformat()]
    states = {r["period"]: r["state"] for r in mine}
    assert states[add_months(this_month(), -1).isoformat()] == "к выплате"
    assert states[add_months(this_month(), 1).isoformat()] == "запланировано"
    # a cohort without an instructor, and a cancelled one, have no schedule
    await running_cohort(admin, name="B")
    cancelled = await running_cohort(
        admin, name="C", instructor_id=str(uid), start_time="12:00", end_time="13:30"
    )
    await admin.post(f"/api/v1/cohorts/{cancelled['id']}/cancel")
    assert len((await admin.get(S, params={"month": "all"})).json()["items"]) == months


async def test_paying_updates_paid_due_and_state(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    uid, _ = await instructor(browser, "ins")
    await set_default_rate(admin, uid, 1000)
    cohort = await running_cohort(admin, back=1, weeks=13, instructor_id=str(uid))
    # half now: partial; the rest is still due
    r = await make_payout(admin, cohort, amount="400")
    assert r.status_code == 201, r.text
    body = (await admin.get(S)).json()
    (row,) = body["items"]
    assert (row["state"], row["paid"], row["due"]) == ("частично", "400.00", "600.00")
    assert body["summary"]["paid_month"] == "400.00" and body["summary"]["due_month"] == "600.00"
    r = await admin.patch(f"{PO}/{r.json()['id']}", json={"amount": "1000"})
    assert r.status_code == 200 and r.json()["amount"] == "1000.00"
    body = (await admin.get(S)).json()
    assert body["items"][0]["state"] == "выплачено"
    assert (body["summary"]["due_month"], body["summary"]["paid_total"]) == ("0.00", "1000.00")


async def test_schedule_export_equals_the_screen(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    uid, _ = await instructor(browser, "ins")
    await set_default_rate(admin, uid, 100)
    cohort = await running_cohort(admin, back=1, instructor_id=str(uid))
    await make_payout(admin, cohort)
    shown = (await admin.get(S, params={"month": "all"})).json()["items"]
    x = await admin.get(f"{S}/export", params={"month": "all"})
    ws = load_workbook(BytesIO(x.content)).active
    assert ws is not None
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    assert [(r[2], r[5], r[8]) for r in rows] == [
        (s["cohort_code"], float(s["rate"]), s["state"]) for s in shown
    ]
    assert ws["A1"].value == "Месяц" and "TJS" in ws["F2"].number_format
    audit = await sql("SELECT diff FROM audit_log WHERE action = 'export' AND entity = 'salary'")
    assert audit[0][0]["rows"] == len(shown)


# ---- payouts -----------------------------------------------------------------------------


async def test_payout_amount_period_and_uniqueness(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    uid, _ = await instructor(browser, "ins")
    await set_default_rate(admin, uid, 500)
    cohort = await running_cohort(admin, back=1, instructor_id=str(uid))
    today_ = today()
    # any day of the month is accepted and stored as the first day; the amount defaults to the rate
    r = await make_payout(admin, cohort, today_.replace(day=17))
    assert r.status_code == 201, r.text
    assert (r.json()["period"], r.json()["amount"], r.json()["instructor_id"]) == (
        this_month().isoformat(),
        "500.00",
        str(uid),
    )
    again = await make_payout(admin, cohort, this_month(), amount="1")
    assert (again.status_code, again.json()["code"]) == (409, "payout_exists")
    assert (await sql("SELECT count(*) FROM instructor_payout"))[0][0] == 1
    # parallel double click: one wins, the rest are 409
    last = add_months(this_month(), -1)
    results = await asyncio.gather(*[make_payout(admin, cohort, last) for _ in range(4)])
    assert sorted(r.status_code for r in results) == [201, 409, 409, 409]
    # a month the cohort does not run, and values out of range
    r = await make_payout(admin, cohort, add_months(this_month(), -6))
    assert (r.status_code, r.json()["code"]) == (422, "payout_period_invalid")
    for bad in ({"amount": "0"}, {"amount": "-3"}, {"paid_at": "2019-01-01"}, {"method": "visa"}):
        r = await make_payout(admin, cohort, add_months(this_month(), 1), **bad)
        assert r.status_code == 422, bad
    nobody = await running_cohort(admin, name="N")
    r = await make_payout(admin, nobody, amount="5")
    assert (r.status_code, r.json()["code"]) == (422, "cohort_no_instructor")
    # the database holds the rule itself
    with pytest.raises(IntegrityError):
        await sql(
            "INSERT INTO instructor_payout (instructor_id, cohort_id, period, amount, paid_at, "
            "method) VALUES (:u, :c, :p, 5, :d, 'alif')",
            u=uid,
            c=cohort["id"],
            p=this_month(),
            d=today_,
        )
    with pytest.raises(IntegrityError):  # a period is a first day
        await sql(
            "INSERT INTO instructor_payout (instructor_id, cohort_id, period, amount, paid_at, "
            "method) VALUES (:u, :c, :p, 5, :d, 'alif')",
            u=uid,
            c=cohort["id"],
            p=date(2026, 3, 15),
            d=today_,
        )


async def test_payout_versions_delete_and_audit(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    uid, _ = await instructor(browser, "ins")
    await set_default_rate(admin, uid, 500)
    cohort = await running_cohort(admin, back=1, instructor_id=str(uid))
    payout = (await make_payout(admin, cohort)).json()
    ok = await admin.patch(f"{PO}/{payout['id']}", json={"note": "аванс", "method": "alif"})
    assert ok.status_code == 200 and ok.json()["note"] == "аванс"
    stale = await admin.patch(
        f"{PO}/{payout['id']}", json={"amount": "1"}, headers={"X-Record-Version": "1"}
    )
    assert (stale.status_code, stale.json()["code"]) == (409, "stale_version")
    assert (await admin.delete(f"{PO}/{payout['id']}")).status_code == 204
    assert (await admin.get(f"{PO}/{payout['id']}")).status_code == 404
    rows = await sql(
        "SELECT action, entity, label, diff FROM audit_log WHERE entity = 'instructor_payout' "
        "ORDER BY id"
    )
    texts = [sentence(Entry("Анна", a, en, lab, d)) for a, en, lab, d in rows]
    label = f"User ins, {cohort['code']}, {this_month():%m.%Y}"
    assert texts[0].startswith(f"Анна: отмечена выплата {label} — ")
    assert texts[1].startswith(f"Анна: изменена выплата {label} — ")
    assert texts[2] == f"Анна: удалена выплата {label}"
    assert (await admin.get("/api/v1/audit", params={"section": "instructors"})).json()[
        "total"
    ] == 3


async def test_payouts_list_filters_and_export(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    a, _ = await instructor(browser, "ia")
    b, _ = await instructor(browser, "ib")
    await set_default_rate(admin, a, 100)
    await set_default_rate(admin, b, 200)
    ca = await running_cohort(admin, name="A", back=1, instructor_id=str(a))
    cb = await running_cohort(admin, name="B", back=1, instructor_id=str(b))
    await make_payout(admin, ca)
    await make_payout(admin, cb)
    await make_payout(admin, cb, add_months(this_month(), -1))
    body = (await admin.get(PO)).json()
    assert (body["total"], body["sum"]) == (3, "500.00")
    only = (await admin.get(PO, params={"instructor_id": str(b)})).json()
    assert (only["total"], only["sum"]) == (2, "400.00")
    month = this_month().strftime("%Y-%m")
    assert (await admin.get(PO, params={"month": month})).json()["total"] == 2
    assert (await admin.get(PO, params={"month": "2026-13"})).status_code == 422
    x = await admin.get(f"{PO}/export", params={"instructor_id": str(b)})
    ws = load_workbook(BytesIO(x.content)).active
    assert ws is not None
    assert len(list(ws.iter_rows(min_row=2))) == 2 and ws["G2"].value == 200


# ---- profit (#9) -------------------------------------------------------------------------


async def test_bug_09_profit_uses_payouts_not_the_schedule(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    uid, _ = await instructor(browser, "ins")
    await set_default_rate(admin, uid, 1000)
    cohort = await running_cohort(admin, back=1, instructor_id=str(uid), price=800)
    e = await enroll(admin, cohort)
    await pay(admin, e, amount=800, confirm=True)
    await pay(admin, e, month=2, amount=800)  # pending: not income
    f = (await admin.get("/api/v1/metrics/finance")).json()
    # the old system showed payroll 0 and an inflated profit; with a schedule but no payouts the
    # payroll is 0 because nothing was paid yet — and it moves the moment a payout is recorded
    assert (f["income"], f["payroll"], f["ads"], f["profit"]) == (
        "800.00",
        "0.00",
        "0.00",
        "800.00",
    )
    assert (await admin.get(S)).json()["summary"]["fund_month"] == "1000.00"
    po = await make_payout(admin, cohort, amount="300")
    f = (await admin.get("/api/v1/metrics/finance")).json()
    assert (f["income"], f["payroll"], f["profit"]) == ("800.00", "300.00", "500.00")
    await admin.delete(f"{PO}/{po.json()['id']}")
    assert (await admin.get("/api/v1/metrics/finance")).json()["profit"] == "800.00"
    # unconfirming takes the income back
    first = (await admin.get("/api/v1/payments", params={"status": "подтверждено"})).json()
    await admin.post(f"/api/v1/payments/{first['items'][0]['id']}/unconfirm")
    assert (await admin.get("/api/v1/metrics/finance")).json()["income"] == "0.00"


async def test_finance_scope_and_rights(
    login_as: SignedIn, admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    uid, ins = await instructor(browser, "ins")
    d = await running_cohort(admin, name="D", instructor_id=str(uid))
    i = await running_cohort(admin, name="I", branch="Истаравшан")
    await pay(admin, await enroll(admin, d, "Д"), amount=100, confirm=True)
    await pay(admin, await enroll(admin, i, "И", branch="Истаравшан"), amount=70, confirm=True)
    assert (await admin.get("/api/v1/metrics/finance")).json()["income"] == "170.00"
    anna = await login_as("anna", await manager_role(), branch="Душанбе")
    assert (await anna.get("/api/v1/metrics/finance")).json()["income"] == "100.00"
    assert (await ins.get("/api/v1/metrics/finance")).status_code == 403


# ---- instructor cards (#17) --------------------------------------------------------------


async def test_bug_17_card_has_numbers_and_no_efficiency_percent(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    uid, _ = await instructor(browser, "ins")
    other, _ = await instructor(browser, "other")
    await set_default_rate(admin, uid, 1000)
    mine = await running_cohort(admin, name="M", back=1, instructor_id=str(uid), price=500)
    theirs = await running_cohort(admin, name="T", back=1, instructor_id=str(other), price=800)
    a, b = await enroll(admin, mine, "Алиев"), await enroll(admin, mine, "Бобоев")
    await pay(admin, a, amount=500, confirm=True)
    await pay(admin, b, amount=250, confirm=True)
    await pay(admin, b, month=2, amount=499)  # pending: not income
    await pay(admin, await enroll(admin, theirs, "Чужой"), amount=777, confirm=True)
    await admin.patch(f"/api/v1/enrollments/{b}", json={"status": "отчислен"})
    await make_payout(admin, mine, amount="600")
    items = (await admin.get(I)).json()["items"]
    card = next(c for c in items if c["id"] == str(uid))
    assert (card["cohorts"], card["students"], card["income"], card["paid_out"]) == (
        1,
        1,  # the expelled student is not counted
        "750.00",  # confirmed payments of the instructor's own cohorts, expelled student included
        "600.00",
    )
    assert card["default_rate"] == "1000.00"
    detail = (await admin.get(f"{I}/{uid}")).json()
    assert [c["code"] for c in detail["cohorts_list"]] == [mine["code"]]
    assert detail["cohorts_list"][0]["income"] == "750.00"
    # #17: no «efficiency» in any shape
    for body in (card, detail):
        assert not any(
            k for k in body if "effic" in k.lower() or "percent" in k.lower() or "%" in k
        ), body.keys()
    assert (await admin.get(I, params={"q": "other"})).json()["total"] == 1
    x = await admin.get(f"{I}/export")
    ws = load_workbook(BytesIO(x.content)).active
    assert ws is not None
    assert [c.value for c in ws[1]] == [
        "Инструктор",
        "Телефон",
        "Филиал",
        "Потоков",
        "Студентов",
        "Доход с потоков",
        "Выплачено",
        "Ставка по умолчанию",
    ]


async def test_cards_branch_scope(login_as: SignedIn, admin: httpx.AsyncClient) -> None:
    here = await make_user("here", "instructor", branch="Душанбе")
    anywhere = await make_user("anywhere", "instructor")
    there = await make_user("there", "instructor", branch="Истаравшан")
    role = await make_role("Кадры", {"instructors": "change"})
    anna = await login_as("anna", role, branch="Душанбе")
    ids = {c["id"] for c in (await anna.get(I)).json()["items"]}
    assert ids == {str(here), str(anywhere)}
    assert (await anna.get(f"{I}/{there}")).status_code == 404
    assert (await anna.patch(f"{I}/{there}", json={"default_rate": "5"})).status_code == 404
    assert (await anna.patch(f"{I}/{here}", json={"default_rate": "5"})).status_code == 200
    istar = await running_cohort(admin, name="I", branch="Истаравшан", instructor_id=str(anywhere))
    sched = (await anna.get(S, params={"month": "all"})).json()
    assert schedule_of(sched, istar["code"]) == []  # another branch's cohort stays hidden


# ---- the instructor sees only their own money (owner requirement) -------------------------


async def test_instructor_sees_only_own_rate_schedule_and_payouts(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    mine_id, me = await instructor(browser, "ins")
    other_id, _ = await instructor(browser, "other")
    await set_default_rate(admin, mine_id, 400)
    await set_default_rate(admin, other_id, 900)
    mine = await running_cohort(admin, name="M", back=1, instructor_id=str(mine_id))
    theirs = await running_cohort(admin, name="T", back=1, instructor_id=str(other_id))
    my_payout = (await make_payout(admin, mine)).json()
    their_payout = (await make_payout(admin, theirs)).json()

    # own card with the rate; the list holds only that card
    card = await me.get(f"{I}/{mine_id}")
    assert card.status_code == 200 and card.json()["default_rate"] == "400.00"
    assert [c["id"] for c in (await me.get(I)).json()["items"]] == [str(mine_id)]
    # own schedule and payouts only
    sched = (await me.get(S, params={"month": "all"})).json()
    assert {r["instructor_id"] for r in sched["items"]} == {str(mine_id)}
    assert {r["rate"] for r in sched["items"]} == {"400.00"}
    assert sched["summary"]["paid_total"] == "400.00"  # not 1300: the other's payout is not mine
    payouts = (await me.get(PO)).json()
    assert [p["id"] for p in payouts["items"]] == [my_payout["id"]] and payouts["sum"] == "400.00"
    assert (await me.get(f"{PO}/{my_payout['id']}")).status_code == 200

    # anything of another instructor: 404, as if it did not exist
    for r in (
        await me.get(f"{I}/{other_id}"),
        await me.get(f"{PO}/{their_payout['id']}"),
        await me.get(S, params={"instructor_id": str(other_id)}),
        await me.get(PO, params={"instructor_id": str(other_id)}),
        await me.get(f"{S}/export", params={"instructor_id": str(other_id)}),
        await me.get(f"{PO}/export", params={"instructor_id": str(other_id)}),
    ):
        assert (r.status_code, r.json()["code"]) == (404, "not_found"), r.url
    # asking for oneself explicitly is fine
    assert (await me.get(PO, params={"instructor_id": str(mine_id)})).status_code == 200
    # their cohort's filter by cohort id leaks nothing either
    assert (await me.get(PO, params={"cohort_id": theirs["id"]})).json()["total"] == 0
    assert (await me.get(S, params={"cohort_id": theirs["id"], "month": "all"})).json()[
        "items"
    ] == []

    # export of own data contains no foreign rows
    ws = load_workbook(
        BytesIO((await me.get(f"{S}/export", params={"month": "all"})).content)
    ).active
    assert ws is not None
    assert {row[1] for row in ws.iter_rows(min_row=2, values_only=True)} == {"User ins"}


async def test_instructor_never_writes_money(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    mine_id, me = await instructor(browser, "ins")
    mine = await running_cohort(admin, back=1, instructor_id=str(mine_id))
    payout = (await make_payout(admin, mine, amount="10")).json()
    for r in (
        await make_payout(me, mine, add_months(this_month(), 1), amount="10"),
        await me.patch(f"{PO}/{payout['id']}", json={"amount": "99999"}),
        await me.delete(f"{PO}/{payout['id']}"),
        await me.patch(f"{S}/cohorts/{mine['id']}/rate", json={"instructor_rate": "99999"}),
        await me.patch(f"{I}/{mine_id}", json={"default_rate": "99999"}),
    ):
        assert r.status_code == 403, r.url
    # even with the matrix cranked up to «change» the role still cannot write money (#24 rule)
    await sql(
        "INSERT INTO role_permission (role_id, section, level) SELECT id, 'instructors', 'change' "
        "FROM role WHERE code = 'instructor' ON CONFLICT (role_id, section) DO UPDATE "
        "SET level = 'change'"
    )
    try:
        assert (await me.patch(f"{I}/{mine_id}", json={"default_rate": "99999"})).status_code == 403
        assert (await me.delete(f"{PO}/{payout['id']}")).status_code == 403
    finally:
        await sql(
            "UPDATE role_permission SET level = 'view' WHERE section = 'instructors' "
            "AND role_id = (SELECT id FROM role WHERE code = 'instructor')"
        )
    assert (await sql("SELECT amount FROM instructor_payout"))[0][0] == 10
    assert (await sql("SELECT default_rate FROM app_user WHERE id = :i", i=mine_id))[0][0] == 0


async def test_manager_has_no_salary_access_by_default(
    login_as: SignedIn, admin: httpx.AsyncClient
) -> None:
    anna = await login_as("anna", await manager_role(), branch="Душанбе")
    for url in (I, S, PO, f"{S}/export", f"{PO}/export", f"{I}/export"):
        assert (await anna.get(url)).status_code == 403, url
