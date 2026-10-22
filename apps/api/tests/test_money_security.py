"""Stage 2 security review: money input edges, branch scope of writes, confirm races, audit."""

import asyncio
import uuid
from collections.abc import Callable

import httpx

from app.cohorts.status import today
from tests.conftest import SignedIn, make_role, make_user, sign_in, sql
from tests.edu import instructor_rights
from tests.money import (
    PO,
    I,
    P,
    S,
    enroll,
    make_payout,
    manager_role,
    pay,
    running_cohort,
)


def _body(enrollment: str, **kw: object) -> dict[str, object]:
    return {
        "idempotency_key": str(uuid.uuid4()),
        "enrollment_id": enrollment,
        "month_no": 1,
        "amount": "100",
        "method": "alif",
        "paid_at": today().isoformat(),
        **kw,
    }


BAD_AMOUNTS = (
    "NaN",
    "nan",
    "Infinity",
    "-Infinity",
    "inf",
    "sNaN",
    "1e999999999",
    "10000000000.00",  # 13 digits: past numeric(12, 2)
    "0.001",
    "1.005",
    "-0.01",
    "0",
    "0.00",
    "",
    "abc",
    True,
    None,
)


async def test_money_amounts_reject_nan_infinity_huge_and_fractions(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    uid = await make_user("ins", "instructor", branch="Душанбе")
    cohort = await running_cohort(admin, back=1, instructor_id=str(uid))
    e = await enroll(admin, cohort)
    payment = await pay(admin, e)
    for bad in BAD_AMOUNTS:
        r = await admin.post(P, json=_body(e, amount=bad))
        assert r.status_code == 422, (bad, r.text)
        r = await admin.patch(f"{P}/{payment['id']}", json={"amount": bad})
        assert r.status_code == (200 if bad is None else 422), (bad, r.text)
        if bad is not None:  # no amount = the cohort's rate (0 here, so refused as well)
            assert (await make_payout(admin, cohort, amount=bad)).status_code == 422, bad
    for bad in ("NaN", "Infinity", "-1", "0.001", "1e20", "10000000000.00"):
        r = await admin.patch(f"{S}/cohorts/{cohort['id']}/rate", json={"instructor_rate": bad})
        assert r.status_code == 422, (bad, r.text)
        r = await admin.patch(f"{I}/{uid}", json={"default_rate": bad})
        assert r.status_code == 422, (bad, r.text)
    # the biggest amount that fits is kept to the cent, and sums do not round
    await sql("UPDATE cohort SET price_month = 9999999999.99 WHERE id = :i", i=cohort["id"])
    big = await pay(admin, e, month=2, amount="9999999999.99", confirm=True)
    small = await pay(admin, e, month=3, amount="0.01", confirm=True)
    assert (big["amount"], small["amount"]) == ("9999999999.99", "0.01")
    summary = (await admin.get(P, params={"status": "подтверждено"})).json()["summary"]
    assert summary["confirmed"] == "10000000000.00"
    for month in (0, -1, 37, 2**31, 2**63, 1.5, "1.5", None):
        r = await admin.post(P, json=_body(e, month_no=month))
        assert r.status_code == 422, (month, r.text)
    assert (await sql("SELECT count(*) FROM payment"))[0][0] == 3


async def test_status_and_confirmer_cannot_be_forged(admin: httpx.AsyncClient) -> None:
    cohort = await running_cohort(admin)
    e = await enroll(admin, cohort)
    payment = await pay(admin, e)
    forged = {
        "status": "подтверждено",
        "confirmed_by": str(uuid.uuid4()),
        "confirmed_at": "2026-01-01T00:00:00Z",
        "version": 99,
        "id": str(uuid.uuid4()),
    }
    for field, value in forged.items():
        assert (await admin.post(P, json={**_body(e), field: value})).status_code == 422, field
        r = await admin.patch(f"{P}/{payment['id']}", json={field: value})
        assert r.status_code == 422, field
    r = await admin.patch(f"{P}/{payment['id']}", json={"enrollment_id": e})
    assert r.status_code == 422
    r = await admin.post(f"{P}/{payment['id']}/confirm", json={"confirmed_by": str(uuid.uuid4())})
    assert r.json()["confirmed_by_name"] == "User root"
    assert (await sql("SELECT count(*) FROM payment WHERE status = 'ожидает'"))[0][0] == 0


async def test_page_beyond_bigint_is_not_a_server_error(admin: httpx.AsyncClient) -> None:
    for url in (P, f"{P}/debtors", PO):
        r = await admin.get(url, params={"page": 10**18})
        assert r.status_code in (200, 422), (url, r.text)


async def test_branch_bound_user_cannot_change_an_all_branches_instructors_rate(
    login_as: SignedIn, admin: httpx.AsyncClient
) -> None:
    """The default rate of an instructor of all branches is copied into the other branch's new
    cohorts: a branch-bound user must not write it (users of all branches are not theirs to
    edit in «Пользователи» either)."""
    anywhere = await make_user("anywhere", "instructor")
    here = await make_user("here", "instructor", branch="Душанбе")
    anna = await login_as(
        "anna", await make_role("Кадры", {"instructors": "change"}), branch="Душанбе"
    )
    assert (await anna.get(f"{I}/{anywhere}")).status_code == 200  # still visible
    r = await anna.patch(f"{I}/{anywhere}", json={"default_rate": "99999"})
    assert (r.status_code, r.json()["code"]) == (403, "branch_forbidden")
    assert (await sql("SELECT default_rate FROM app_user WHERE id = :i", i=anywhere))[0][0] == 0
    assert (await anna.patch(f"{I}/{here}", json={"default_rate": "7"})).status_code == 200
    assert (await admin.patch(f"{I}/{anywhere}", json={"default_rate": "8"})).status_code == 200


async def test_branch_bound_user_cannot_touch_another_branchs_salaries(
    login_as: SignedIn, admin: httpx.AsyncClient
) -> None:
    uid = await make_user("ins", "instructor", branch="Истаравшан")
    istar = await running_cohort(admin, name="I", branch="Истаравшан", instructor_id=str(uid))
    payout = (await make_payout(admin, istar, amount="10")).json()
    anna = await login_as(
        "anna", await make_role("Кадры", {"instructors": "change"}), branch="Душанбе"
    )
    for r in (
        await make_payout(anna, istar, amount="5"),
        await anna.patch(f"{S}/cohorts/{istar['id']}/rate", json={"instructor_rate": "1"}),
        await anna.get(f"{PO}/{payout['id']}"),
        await anna.patch(f"{PO}/{payout['id']}", json={"amount": "1"}),
        await anna.delete(f"{PO}/{payout['id']}"),
    ):
        assert r.status_code == 404, (r.url, r.text)
    assert (await anna.get(PO, params={"branch_id": istar["branch_id"]})).json()["total"] == 0
    sched = (await anna.get(S, params={"month": "all", "cohort_id": istar["id"]})).json()
    assert sched["items"] == [] and sched["summary"]["paid_total"] == "0.00"
    assert (await sql("SELECT amount FROM instructor_payout"))[0][0] == 10


async def test_payment_picker_and_debtors_hide_the_other_branch(
    login_as: SignedIn, admin: httpx.AsyncClient
) -> None:
    istar = await running_cohort(admin, name="I", branch="Истаравшан")
    ei = await enroll(admin, istar, "Чужой Студент", branch="Истаравшан")
    anna = await login_as("anna", await manager_role(), branch="Душанбе")
    for params in (
        {},
        {"q": "Чужой"},
        {"cohort_id": istar["id"]},
        {"enrollment_id": ei},
    ):
        assert (await anna.get(f"{P}/options", params=params)).json() == [], params
    for params in ({}, {"cohort_id": istar["id"]}, {"branch_id": istar["branch_id"]}):
        assert (await anna.get(f"{P}/debtors", params=params)).json()["total"] == 0, params
        assert (await anna.get(P, params=params)).json()["total"] == 0, params
    export = await anna.get(f"{P}/debtors/export", params={"q": "Чужой"})
    assert export.status_code == 200 and "Чужой".encode() not in export.content


async def test_confirm_needs_the_version_the_confirmer_saw(admin: httpx.AsyncClient) -> None:
    """Confirming is a money decision on what the confirmer saw: an amount edited meanwhile must
    not be confirmed blindly (#25)."""
    cohort = await running_cohort(admin, price=5000)
    e = await enroll(admin, cohort)
    payment = await pay(admin, e, amount=500)
    seen = payment["version"]
    edited = await admin.patch(f"{P}/{payment['id']}", json={"amount": "5000"})
    assert edited.status_code == 200
    r = await admin.post(f"{P}/{payment['id']}/confirm", headers={"X-Record-Version": str(seen)})
    assert (r.status_code, r.json()["code"]) == (409, "stale_version")
    assert (await sql("SELECT status FROM payment"))[0][0] == "ожидает"
    r = await admin.post(
        f"{P}/{payment['id']}/confirm", headers={"X-Record-Version": "x"}, no_version=True
    )
    assert r.status_code == 400
    r = await admin.post(f"{P}/{payment['id']}/confirm", no_version=True)
    assert r.status_code == 428
    r = await admin.post(
        f"{P}/{payment['id']}/confirm", headers={"X-Record-Version": str(edited.json()["version"])}
    )
    assert r.status_code == 200 and r.json()["amount"] == "5000.00"
    r = await admin.post(f"{P}/{payment['id']}/unconfirm", headers={"X-Record-Version": str(seen)})
    assert (r.status_code, r.json()["code"]) == (409, "stale_version")


async def test_parallel_confirm_unconfirm_and_edit_stay_consistent(
    admin: httpx.AsyncClient,
) -> None:
    cohort = await running_cohort(admin)
    e = await enroll(admin, cohort)
    payment = await pay(admin, e)
    v = str(payment["version"])
    results = await asyncio.gather(
        admin.post(f"{P}/{payment['id']}/confirm", headers={"X-Record-Version": v}),
        admin.post(f"{P}/{payment['id']}/confirm", headers={"X-Record-Version": v}),
        admin.patch(f"{P}/{payment['id']}", json={"amount": "1"}, headers={"X-Record-Version": v}),
        admin.delete(f"{P}/{payment['id']}"),
    )
    codes = [r.status_code for r in results]
    assert codes.count(200) + codes.count(204) >= 1 and 500 not in codes, codes
    rows = await sql("SELECT status, amount, confirmed_at IS NOT NULL FROM payment")
    audit = await sql("SELECT action FROM audit_log WHERE entity = 'payment' ORDER BY id")
    actions = [a for (a,) in audit]
    if rows:
        status, amount, stamped = rows[0]
        assert stamped == (status == "подтверждено")
        assert actions.count("payment.confirm") == (1 if status == "подтверждено" else 0)
        if status == "подтверждено":
            assert "payment.update" not in actions or amount == 1
    else:
        assert actions[-1] == "payment.delete" and "payment.confirm" not in actions


async def test_confirm_or_edit_of_a_payment_deleted_meanwhile_is_404_not_500(
    admin: httpx.AsyncClient,
) -> None:
    cohort = await running_cohort(admin)
    e = await enroll(admin, cohort)
    for month in range(1, 9):
        payment = await pay(admin, e, month=month % cohort["months"] + 1)
        url, v = f"{P}/{payment['id']}", {"X-Record-Version": str(payment["version"])}
        results = await asyncio.gather(
            admin.delete(url),
            admin.post(f"{url}/confirm", headers=v),
            admin.patch(url, json={"note": "x"}, headers=v),
            admin.delete(url),
        )
        codes = sorted(r.status_code for r in results)
        assert 500 not in codes and codes.count(204) <= 1, codes
        await sql("DELETE FROM payment")


async def test_idempotency_key_of_another_user_or_branch_leaks_nothing(
    login_as: SignedIn, admin: httpx.AsyncClient
) -> None:
    dushanbe = await running_cohort(admin, name="D")
    istar = await running_cohort(admin, name="I", branch="Истаравшан")
    ed = await enroll(admin, dushanbe, "Свой")
    ei = await enroll(admin, istar, "Чужой", branch="Истаравшан")
    theirs = _body(ei, amount="377")
    assert (await admin.post(P, json=theirs)).status_code == 201
    anna = await login_as("anna", await manager_role(), branch="Душанбе")
    # her own enrollment with the other branch's key: no payment of theirs comes back
    r = await anna.post(P, json={**theirs, "enrollment_id": ed})
    assert r.status_code in (404, 409) and "Чужой" not in r.text and "377" not in r.text
    # the same body as theirs: 404 as if it did not exist
    r = await anna.post(P, json=theirs)
    assert r.status_code == 404 and "377" not in r.text
    assert (await sql("SELECT count(*) FROM payment"))[0][0] == 1


async def test_every_money_write_is_audited(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    uid = await make_user("ins", "instructor", branch="Душанбе")
    assert (await admin.patch(f"{I}/{uid}", json={"default_rate": "300"})).status_code == 200
    cohort = await running_cohort(admin, back=1, instructor_id=str(uid))
    created = await sql(
        "SELECT diff FROM audit_log WHERE action = 'cohort.create' AND entity_id = :i",
        i=cohort["id"],
    )
    assert created[0][0]["instructor_rate"] == [None, "300.00"]
    e = await enroll(admin, cohort)
    payment = await pay(admin, e, confirm=True)
    await admin.post(f"{P}/{payment['id']}/unconfirm")
    await admin.patch(f"{P}/{payment['id']}", json={"amount": "1"})
    await admin.delete(f"{P}/{payment['id']}")
    await admin.patch(f"{S}/cohorts/{cohort['id']}/rate", json={"instructor_rate": "350"})
    payout = (await make_payout(admin, cohort)).json()
    await admin.patch(f"{PO}/{payout['id']}", json={"amount": "1"})
    await admin.delete(f"{PO}/{payout['id']}")
    actions = [a for (a,) in await sql("SELECT action FROM audit_log ORDER BY id")]
    for action in (
        "user.update",
        "payment.create",
        "payment.confirm",
        "payment.unconfirm",
        "payment.update",
        "payment.delete",
        "cohort.update",
        "payout.create",
        "payout.update",
        "payout.delete",
    ):
        assert action in actions, action


async def test_instructor_with_widened_matrix_still_reaches_no_foreign_money(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    me_id = await make_user("ins", "instructor", branch="Душанбе")
    other_id = await make_user("other", "instructor", branch="Душанбе")
    theirs = await running_cohort(admin, name="T", back=1, instructor_id=str(other_id))
    e = await enroll(admin, theirs, "Их студент")
    payment = await pay(admin, e, confirm=True)
    payout = (await make_payout(admin, theirs, amount="10")).json()
    me = browser()
    await sign_in(me, "ins")
    async with instructor_rights(payments="change", instructors="change", dashboard="view"):
        for r in (
            await me.get(P),
            await me.get(f"{P}/{payment['id']}"),
            await me.get(f"{P}/options"),
            await me.get(f"{P}/debtors/export"),
            await me.get(f"{P}/by-cohort/{theirs['id']}"),
            await me.post(f"{P}/{payment['id']}/unconfirm", headers={"X-Record-Version": "1"}),
            await me.post(P, json=_body(e)),
            await me.get("/api/v1/metrics/finance"),
            await make_payout(me, theirs, amount="5"),
            await me.patch(f"{I}/{me_id}", json={"default_rate": "1"}),
        ):
            assert r.status_code in (403, 404), (r.url, r.status_code)
        for r in (
            await me.get(f"{I}/{other_id}"),
            await me.get(f"{PO}/{payout['id']}"),
            await me.get(S, params={"instructor_id": str(other_id), "month": "all"}),
        ):
            assert r.status_code == 404, r.url
        assert (await me.get(PO, params={"cohort_id": theirs["id"]})).json()["total"] == 0
        cards = (await me.get(I, params={"q": "other"})).json()["items"]
        assert cards == []
    assert (await sql("SELECT status FROM payment"))[0][0] == "подтверждено"
