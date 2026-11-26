"""A discount on a payment: a percent of the month's price, computed on the server. The month is
covered by payments plus discounts, the debt drops by the discount, income stays the money
received and the discounts are their own line in the reports."""

import uuid
from io import BytesIO
from typing import Any

import httpx
from openpyxl import load_workbook

from app.audit.sentences import Entry, sentence
from app.cohorts.status import today
from tests.conftest import SignedIn, sql
from tests.money import P, cohort_money, enroll, manager_role, money_of, pay, running_cohort

D = "/api/v1/dashboard"


def body(enrollment: str, **kw: Any) -> dict[str, Any]:
    return {
        "idempotency_key": str(uuid.uuid4()),
        "enrollment_id": enrollment,
        "month_no": 1,
        "amount": "400",
        "method": "наличные",
        "paid_at": today().isoformat(),
        "discount_percent": 20,
        "note": "второй курс",
        **kw,
    }


async def month(c: httpx.AsyncClient, e: str, month_no: int = 1) -> dict[str, Any]:
    r = await c.get(f"{P}/month", params={"enrollment_id": e, "month_no": month_no})
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


async def test_500_with_20_percent_pays_400_and_closes_the_month(
    admin: httpx.AsyncClient,
) -> None:
    cohort = await running_cohort(admin, price=500, back=0)
    e = await enroll(admin, cohort)
    # the discount follows the price, not the sum entered: 20 % of 500 whatever is typed
    r = await admin.post(P, json=body(e))
    assert r.status_code == 201, r.text
    p = r.json()
    assert (p["amount"], p["discount_percent"], p["discount_amount"]) == ("400.00", 20, "100.00")
    assert p["note"] == "второй курс"  # covered in full: no «Частичная оплата» prefix
    s = await month(admin, e)
    assert (s["paid"], s["discount"], s["remaining"], s["full"]) == (
        "400.00",
        "100.00",
        "0.00",
        True,
    )
    await admin.post(f"{P}/{p['id']}/confirm")
    m = money_of(await cohort_money(admin, cohort), e)
    assert (m["paid"], m["discount"], m["debt"], m["paid_months"]) == (
        "400.00",
        "100.00",
        "0.00",
        [1],
    )
    debtors = (await admin.get(f"{P}/debtors")).json()
    assert e not in [d["enrollment_id"] for d in debtors["items"]]
    # nothing more fits the month
    more = await admin.post(P, json=body(e, amount="1", discount_percent=None, note=None))
    assert (more.status_code, more.json()["code"]) == (409, "month_already_paid")


async def test_partial_200_with_20_percent_leaves_200(admin: httpx.AsyncClient) -> None:
    cohort = await running_cohort(admin, price=500, back=0)
    e = await enroll(admin, cohort)
    r = await admin.post(P, json=body(e, amount="200", partial=True))
    assert r.status_code == 201, r.text
    assert r.json()["note"] == "Частичная оплата. Осталось оплатить 200 TJS. второй курс"
    s = await month(admin, e)
    assert (s["paid"], s["discount"], s["remaining"], s["discount_percent"]) == (
        "200.00",
        "100.00",
        "200.00",
        20,
    )
    # one discount per month: the second part of the month comes without one
    twice = await admin.post(P, json=body(e, amount="200"))
    assert (twice.status_code, twice.json()["code"]) == (409, "month_discount_exists")
    assert twice.json()["params"] == {"month_no": 1, "percent": 20}
    over = await admin.post(P, json=body(e, amount="201", discount_percent=None))
    assert (over.status_code, over.json()["code"]) == (409, "month_overpaid")
    assert over.json()["params"]["remaining"] == "200.00"
    assert (await admin.post(P, json=body(e, amount="200", discount_percent=None))).status_code
    s = await month(admin, e)
    assert (s["paid"], s["remaining"], s["full"]) == ("400.00", "0.00", True)


async def test_100_percent_is_a_payment_of_0_and_closes_the_month(
    admin: httpx.AsyncClient,
) -> None:
    cohort = await running_cohort(admin, price=500, back=0)
    e = await enroll(admin, cohort)
    r = await admin.post(P, json=body(e, amount="0", discount_percent=100, note="сотрудник"))
    assert r.status_code == 201, r.text
    assert (r.json()["amount"], r.json()["discount_amount"]) == ("0.00", "500.00")
    await admin.post(f"{P}/{r.json()['id']}/confirm")
    m = money_of(await cohort_money(admin, cohort), e)
    assert (m["paid"], m["debt"], m["paid_months"]) == ("0.00", "0.00", [1])
    # a payment of 0 without a discount is no payment
    zero = await admin.post(P, json=body(e, month_no=2, amount="0", discount_percent=None))
    assert (zero.status_code, zero.json()["code"]) == (422, "payment_amount_zero")


async def test_a_discount_needs_a_reason_and_a_price(admin: httpx.AsyncClient) -> None:
    cohort = await running_cohort(admin, price=500)
    e = await enroll(admin, cohort)
    for note in (None, "", "   "):
        r = await admin.post(P, json=body(e, note=note))
        assert (r.status_code, r.json()["code"]) == (422, "discount_reason_required"), note
        assert r.json()["errors"][0]["loc"] == ["body", "note"]
    for bad in (0, 101):
        r = await admin.post(P, json=body(e, discount_percent=bad))
        assert r.status_code == 422, bad
    # more than what is left after the discount: 20 % of 500 leaves 400
    r = await admin.post(P, json=body(e, amount="401"))
    assert (r.status_code, r.json()["code"]) == (409, "month_overpaid")
    await sql("UPDATE cohort SET price_month = 0 WHERE id = :i", i=cohort["id"])
    r = await admin.post(P, json=body(e))
    assert (r.status_code, r.json()["code"]) == (422, "discount_no_price")


async def test_edit_changes_and_removes_the_discount(admin: httpx.AsyncClient) -> None:
    cohort = await running_cohort(admin, price=500)
    e = await enroll(admin, cohort)
    p = (await admin.post(P, json=body(e))).json()
    # 10 % leaves room for 450: the money stays 400, the month is short by 50
    r = await admin.patch(f"{P}/{p['id']}", json={"discount_percent": 10})
    assert (r.status_code, r.json()["discount_amount"]) == (200, "50.00"), r.text
    assert (await month(admin, e))["remaining"] == "50.00"
    # the note is the reason: it cannot go while the discount stays
    r = await admin.patch(f"{P}/{p['id']}", json={"note": None})
    assert (r.status_code, r.json()["code"]) == (422, "discount_reason_required")
    # 30 % of 500 = 150: 400 + 150 is more than the price
    r = await admin.patch(f"{P}/{p['id']}", json={"discount_percent": 30})
    assert (r.status_code, r.json()["code"]) == (409, "month_overpaid")
    r = await admin.patch(f"{P}/{p['id']}", json={"discount_percent": None})
    assert r.status_code == 200 and r.json()["discount_percent"] is None
    assert r.json()["discount_amount"] == "0.00"
    assert (await month(admin, e))["remaining"] == "100.00"


async def test_the_form_gets_the_percent_of_the_previous_payment(
    admin: httpx.AsyncClient,
) -> None:
    cohort = await running_cohort(admin, price=500)
    e = await enroll(admin, cohort)
    other = await enroll(admin, cohort, "Другой")

    async def last(enrollment: str) -> Any:
        r = await admin.get(f"{P}/options", params={"enrollment_id": enrollment})
        return r.json()[0]["last_discount_percent"]

    assert await last(e) is None
    await admin.post(P, json=body(e, discount_percent=15, amount="425"))
    assert await last(e) == 15
    assert await last(other) is None  # another student's discount is not this one's
    await pay(admin, e, month=2, amount=500)
    assert await last(e) is None  # the latest payment had none


async def test_report_income_400_discounts_100(admin: httpx.AsyncClient) -> None:
    cohort = await running_cohort(admin, price=500, back=0)
    e = await enroll(admin, cohort)
    p = (await admin.post(P, json=body(e))).json()
    pending = (await admin.get(D + "/overview")).json()
    assert (pending["income"], pending["discounts"]) == ("0.00", "0.00")  # confirmed only
    await admin.post(f"{P}/{p['id']}/confirm")
    o = (await admin.get(D + "/overview")).json()
    assert (o["income"], o["discounts"], o["profit"]) == ("400.00", "100.00", "400.00")
    row = (await admin.get(D + "/by-month")).json()["items"][-1]
    assert (row["income"], row["discounts"]) == ("400.00", "100.00")
    totals = (await admin.get(P)).json()["summary"]
    assert (totals["confirmed"], totals["confirmed_discount"]) == ("400.00", "100.00")


async def test_list_and_export_show_the_discount(admin: httpx.AsyncClient) -> None:
    cohort = await running_cohort(admin, price=500)
    e = await enroll(admin, cohort)
    await admin.post(P, json=body(e))
    await pay(admin, e, month=2, amount=500)
    items = (await admin.get(P)).json()["items"]
    assert sorted((i["discount_percent"] or 0, i["discount_amount"]) for i in items) == [
        (0, "0.00"),
        (20, "100.00"),
    ]
    r = await admin.get(f"{P}/export")
    assert r.status_code == 200
    ws = load_workbook(BytesIO(r.content)).active
    assert ws is not None
    rows = list(ws.iter_rows(values_only=True))
    header = next(i for i, row in enumerate(rows) if row and "Скидка, %" in row)
    cols = rows[header]
    pct, amount = cols.index("Скидка, %"), cols.index("Скидка, сомони")
    got = sorted((row[pct] or 0, row[amount] or 0) for row in rows[header + 1 :] if row[0])
    assert got == [(0, 0), (20, 100)]


async def test_other_branch_cannot_discount(login_as: SignedIn, admin: httpx.AsyncClient) -> None:
    istar = await running_cohort(admin, name="I", branch="Истаравшан")
    ei = await enroll(admin, istar, "Чужой Студент", branch="Истаравшан")
    anna = await login_as("anna", await manager_role(), branch="Душанбе")
    r = await anna.post(P, json=body(ei))
    assert r.status_code == 404
    viewer = await login_as("vera", "manager", branch="Душанбе")
    await sql(
        "UPDATE role_permission SET level = 'view' WHERE section = 'payments' AND role_id = "
        "(SELECT role_id FROM app_user WHERE login = 'vera')"
    )
    mine = await running_cohort(admin, name="D")
    ed = await enroll(admin, mine)
    assert (await viewer.post(P, json=body(ed))).status_code == 403
    assert await sql("SELECT count(*) FROM payment") == [(0,)]


async def test_audit_names_the_discount(admin: httpx.AsyncClient) -> None:
    cohort = await running_cohort(admin, price=500)
    e = await enroll(admin, cohort, "Алиев Алишер")
    p = (await admin.post(P, json=body(e))).json()
    await admin.patch(f"{P}/{p['id']}", json={"discount_percent": 10})
    rows = await sql(
        "SELECT action, entity, label, diff FROM audit_log WHERE entity = 'payment' ORDER BY id"
    )
    texts = [sentence(Entry("Анна", a, en, lab, d)) for a, en, lab, d in rows]
    head = f"Анна: создана оплата Алиев Алишер ({cohort['code']}), мес. 1 — скидка 20 % (100 TJS)"
    assert texts[0].startswith(head), texts[0]
    assert "скидка 20 % (100 TJS) → 10 % (50 TJS)" in texts[1], texts[1]
    # a payment without a discount reads as before
    await pay(admin, e, month=2, amount=500)
    last = (await sql("SELECT diff FROM audit_log WHERE entity = 'payment' ORDER BY id"))[-1][0]
    assert "discount_percent" not in last
