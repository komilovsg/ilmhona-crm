"""A month takes payments up to the cohort's price (pending + confirmed), never more; two people
paying the same month at once: one wins, the other sees who paid. The hold tells the others who is
entering a payment right now (UX only)."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.cohorts.status import today
from app.core import clock as app_clock
from tests.conftest import SignedIn, sql
from tests.money import P, add_months, enroll, manager_role, pay, running_cohort, this_month

H = f"{P}/month/hold"


def body(enrollment: str, **kw: Any) -> dict[str, Any]:
    return {
        "idempotency_key": str(uuid.uuid4()),
        "enrollment_id": enrollment,
        "month_no": 2,
        "amount": "700",
        "method": "наличные",
        "paid_at": today().isoformat(),
        **kw,
    }


async def status(c: httpx.AsyncClient, e: str, month: int = 2) -> dict[str, Any]:
    r = await c.get(f"{P}/month", params={"enrollment_id": e, "month_no": month})
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


async def test_partial_payments_up_to_the_price_then_the_month_is_full(
    admin: httpx.AsyncClient,
) -> None:
    cohort = await running_cohort(admin, price=700)
    e = await enroll(admin, cohort)
    await pay(admin, e, month=2, amount=300, confirm=True)
    await pay(admin, e, month=2, amount=200)  # pending counts too
    over = await admin.post(P, json=body(e, amount="201"))
    assert (over.status_code, over.json()["code"]) == (409, "month_overpaid")
    params = over.json()["params"]
    assert (params["month_no"], params["price"], params["paid"], params["remaining"]) == (
        2,
        "700.00",
        "500.00",
        "200.00",
    )
    assert [(x["amount"], x["status"], x["created_by"]) for x in params["payments"]] == [
        ("300.00", "подтверждено", "User root"),
        ("200.00", "ожидает", "User root"),
    ]
    assert (await admin.post(P, json=body(e, amount="200"))).status_code == 201
    full = await admin.post(P, json=body(e, amount="1"))
    assert (full.status_code, full.json()["code"]) == (409, "month_already_paid")
    assert full.json()["params"]["remaining"] == "0.00"
    # other months are untouched
    assert (await admin.post(P, json=body(e, month_no=3))).status_code == 201
    s = await status(admin, e)
    assert (s["paid"], s["remaining"], s["full"]) == ("700.00", "0.00", True)


async def test_a_cohort_without_a_price_has_no_cap(admin: httpx.AsyncClient) -> None:
    cohort = await running_cohort(admin)
    e = await enroll(admin, cohort)
    await sql("UPDATE cohort SET price_month = 0 WHERE id = :i", i=cohort["id"])
    assert (await admin.post(P, json=body(e, amount="900"))).status_code == 201


async def test_edit_obeys_the_same_rule(admin: httpx.AsyncClient) -> None:
    cohort = await running_cohort(admin, price=500)
    e = await enroll(admin, cohort)
    await pay(admin, e, month=1, amount=500)
    p2 = await pay(admin, e, month=2, amount=300)
    # moving into a full month
    r = await admin.patch(f"{P}/{p2['id']}", json={"month_no": 1})
    assert (r.status_code, r.json()["code"]) == (409, "month_already_paid")
    # raising over the price (its own old amount does not count twice)
    r = await admin.patch(f"{P}/{p2['id']}", json={"amount": "501"})
    assert (r.status_code, r.json()["code"]) == (409, "month_overpaid")
    assert r.json()["params"]["remaining"] == "500.00"
    assert (await admin.patch(f"{P}/{p2['id']}", json={"amount": "500"})).status_code == 200
    assert (await admin.patch(f"{P}/{p2['id']}", json={"amount": "100"})).status_code == 200
    # a legacy overpaid month can still be lowered or edited otherwise
    await sql("UPDATE payment SET amount = 800 WHERE id = :i", i=p2["id"])
    assert (await admin.patch(f"{P}/{p2['id']}", json={"amount": "600"})).status_code == 200
    assert (await admin.patch(f"{P}/{p2['id']}", json={"note": "x"})).status_code == 200


async def test_two_people_paying_the_same_month_at_once_one_wins(
    login_as: SignedIn, admin: httpx.AsyncClient
) -> None:
    """The owner's case: superadmin and manager open «Оплата» for month 2 and both save."""
    cohort = await running_cohort(admin, price=700)
    e = await enroll(admin, cohort)
    anna = await login_as("anna", await manager_role(), branch="Душанбе")
    for _ in range(3):
        results = await asyncio.gather(
            admin.post(P, json=body(e)),
            anna.post(P, json=body(e)),
            admin.post(P, json=body(e)),
            anna.post(P, json=body(e)),
        )
        codes = sorted(r.status_code for r in results)
        assert codes == [201, 409, 409, 409], codes
        winner = next(r for r in results if r.status_code == 201).json()
        for lost in (r for r in results if r.status_code == 409):
            problem = lost.json()
            assert problem["code"] == "month_already_paid"
            (first,) = problem["params"]["payments"]
            assert first["id"] == winner["id"] and first["amount"] == "700.00"
            assert first["created_by"] in ("User root", "User anna") and first["created_at"]
        assert (await sql("SELECT count(*) FROM payment"))[0][0] == 1
        await sql("DELETE FROM payment")


async def test_parallel_retries_of_one_create_are_one_payment(admin: httpx.AsyncClient) -> None:
    cohort = await running_cohort(admin, price=700)
    e = await enroll(admin, cohort)
    same = body(e)
    results = await asyncio.gather(*(admin.post(P, json=same) for _ in range(4)))
    assert sorted(r.status_code for r in results) == [200, 200, 200, 201]
    assert len({r.json()["id"] for r in results}) == 1


async def test_partial_payment_gets_the_note_of_what_is_left(admin: httpx.AsyncClient) -> None:
    cohort = await running_cohort(admin, price=700)
    e = await enroll(admin, cohort)
    first = await admin.post(P, json=body(e, amount="250.50", partial=True, note="от брата"))
    assert first.json()["note"] == "Частичная оплата. Осталось оплатить 449.50 TJS. от брата"
    # a smaller amount without the flag is partial as well
    second = await admin.post(P, json=body(e, amount="49.50"))
    assert second.json()["note"] == "Частичная оплата. Осталось оплатить 400 TJS"
    last = await admin.post(P, json=body(e, amount="400", partial=True))
    assert last.json()["note"] == "Месяц оплачен полностью"
    # «Полностью»: the amount is what is left, no note
    full = await admin.post(P, json=body(e, month_no=3, amount="700"))
    assert full.json()["note"] is None
    s = await status(admin, e)
    assert [(x["amount"], x["method"], x["status"]) for x in s["payments"]] == [
        ("250.50", "наличные", "ожидает"),
        ("49.50", "наличные", "ожидает"),
        ("400.00", "наличные", "ожидает"),
    ]


async def test_month_states_and_due_months(admin: httpx.AsyncClient) -> None:
    cohort = await running_cohort(admin, back=2, weeks=30, price=500)
    e = await enroll(admin, cohort)
    await pay(admin, e, month=1, amount=500, confirm=True)
    await pay(admin, e, month=2, amount=200)
    r = await admin.get(f"{P}/enrollment/{e}")
    assert r.status_code == 200, r.text
    m = r.json()
    states = {s["month_no"]: (s["state"], s["paid"], s["pending"]) for s in m["month_states"]}
    assert states[1] == ("оплачен", "500.00", "0.00")
    assert states[2] == ("частично", "200.00", "200.00")
    assert states[3] == ("не оплачен", "0.00", "0.00")
    assert len(states) == m["months"]
    # started months: 1, 2, 3 (this one)
    assert m["due_months"] == [
        {"month_no": 2, "remaining": "300.00"},
        {"month_no": 3, "remaining": "500.00"},
    ]
    debtors = (await admin.get(f"{P}/debtors")).json()["items"]
    assert debtors[0]["due_months"] == m["due_months"]
    late = await enroll(admin, cohort, "Поздний", since=add_months(this_month(), 0))
    late_money = (await admin.get(f"{P}/enrollment/{late}")).json()
    assert late_money["due_months"] == [{"month_no": 3, "remaining": "500.00"}]
    opts = (await admin.get(f"{P}/options", params={"enrollment_id": e})).json()
    assert opts[0]["full_months"] == [1]


# ---- the hold ----------------------------------------------------------------------------


async def test_hold_acquire_conflict_refresh_release_and_expire(
    login_as: SignedIn, admin: httpx.AsyncClient
) -> None:
    cohort = await running_cohort(admin, price=700)
    e = await enroll(admin, cohort)
    anna = await login_as("anna", await manager_role(), branch="Душанбе")
    mine = await admin.post(H, json={"enrollment_id": e, "month_no": 2})
    assert mine.status_code == 200, mine.text
    assert (mine.json()["acquired"], mine.json()["mine"], mine.json()["held_by"]) == (
        True,
        True,
        None,
    )
    # anna sees it and cannot take it
    theirs = (await anna.post(H, json={"enrollment_id": e, "month_no": 2})).json()
    assert theirs["acquired"] is False and theirs["held_by"]["name"] == "User root"
    s = await status(anna, e)
    assert s["held_by"]["name"] == "User root" and s["until"] and s["mine"] is False
    assert (s["price"], s["paid"], s["remaining"], s["full"]) == ("700.00", "0.00", "700.00", False)
    # a refresh keeps it ours and moves the expiry
    until = (await status(anna, e))["until"]
    app_clock.freeze(datetime.now(UTC) + timedelta(seconds=60))
    assert (await admin.post(H, json={"enrollment_id": e, "month_no": 2})).json()["acquired"]
    assert (await status(anna, e))["until"] > until
    # anna's release does not drop root's hold
    assert (await anna.delete(H, params={"enrollment_id": e, "month_no": 2})).status_code == 204
    assert (await status(anna, e))["held_by"]["name"] == "User root"
    # it expires by itself: then anna takes it
    app_clock.freeze(datetime.now(UTC) + timedelta(seconds=60 + 121))
    assert (await status(anna, e))["held_by"] is None
    assert (await anna.post(H, json={"enrollment_id": e, "month_no": 2})).json()["acquired"]
    app_clock.freeze(None)
    # root released by switching month or deleting
    s = await status(admin, e)
    assert s["held_by"]["name"] == "User anna"
    assert (await anna.post(H, json={"enrollment_id": e, "month_no": 3})).json()["acquired"]
    assert (await status(admin, e))["held_by"] is None  # one month per enrollment at a time
    assert (await anna.delete(H, params={"enrollment_id": e, "month_no": 3})).status_code == 204
    assert (await status(admin, e, 3))["held_by"] is None
    # holds are not audited
    assert (await sql("SELECT count(*) FROM audit_log WHERE entity = 'payment_hold'"))[0][0] == 0


async def test_hold_never_blocks_the_rule_and_a_create_releases_it(
    login_as: SignedIn, admin: httpx.AsyncClient
) -> None:
    cohort = await running_cohort(admin, price=700)
    e = await enroll(admin, cohort)
    anna = await login_as("anna", await manager_role(), branch="Душанбе")
    await admin.post(H, json={"enrollment_id": e, "month_no": 2})
    # anna is not the holder: the server still lets her pay (the rule decides, not the hold)
    assert (await anna.post(P, json=body(e, amount="300"))).status_code == 201
    assert (await admin.post(P, json=body(e, amount="400"))).status_code == 201
    assert (await status(anna, e))["held_by"] is None  # root's create dropped root's hold
    r = await anna.post(P, json=body(e, amount="1"))
    assert r.json()["code"] == "month_already_paid"


async def test_hold_and_status_follow_scope_and_rights(
    login_as: SignedIn, admin: httpx.AsyncClient
) -> None:
    istar = await running_cohort(admin, name="I", branch="Истаравшан")
    ei = await enroll(admin, istar, "Чужой", branch="Истаравшан")
    anna = await login_as("anna", await manager_role(), branch="Душанбе")
    assert (
        await anna.get(f"{P}/month", params={"enrollment_id": ei, "month_no": 1})
    ).status_code == 404
    assert (await anna.post(H, json={"enrollment_id": ei, "month_no": 1})).status_code == 404
    assert (await anna.delete(H, params={"enrollment_id": ei, "month_no": 1})).status_code == 404
    assert (await anna.get(f"{P}/enrollment/{ei}")).status_code == 404
    ins = await login_as("ins", "instructor", branch="Истаравшан")
    assert (
        await ins.get(f"{P}/month", params={"enrollment_id": ei, "month_no": 1})
    ).status_code == 403
    assert (await ins.post(H, json={"enrollment_id": ei, "month_no": 1})).status_code == 403
    r = await admin.post(H, json={"enrollment_id": ei, "month_no": istar["months"] + 1})
    assert r.json()["code"] == "payment_month_invalid"
    unknown = {"enrollment_id": str(uuid.uuid4()), "month_no": 1}
    assert (await admin.post(H, json=unknown)).status_code == 404
