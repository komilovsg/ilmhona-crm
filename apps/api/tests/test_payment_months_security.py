"""Security of the month rule and the hold: lock order (no deadlock with paths that lock the
enrollment first), one hold per user (nobody greys out every form), rights and scope."""

import asyncio
import uuid
from typing import Any

import httpx
from sqlalchemy import text

from app.core.db import sessionmaker
from app.permissions import MANAGER_DEFAULT
from tests.conftest import SignedIn, make_role, sql
from tests.money import P, enroll, manager_role, pay, running_cohort
from tests.test_payment_months import body, status

H = f"{P}/month/hold"


async def _wait_for_a_lock_waiter() -> None:
    for _ in range(200):
        rows = await sql(
            "SELECT count(*) FROM pg_stat_activity "
            "WHERE datname = current_database() AND wait_event_type = 'Lock'"
        )
        if rows[0][0]:
            return
        await asyncio.sleep(0.02)
    raise AssertionError("the request never waited on the lock")


async def test_payment_edit_locks_the_enrollment_before_the_payment(
    admin: httpx.AsyncClient,
) -> None:
    """Enrollment-first paths (a create, an enrollment delete whose RESTRICT check key-shares the
    payments) must not deadlock with an edit that raises the amount (500 for one of them)."""
    cohort = await running_cohort(admin, price=700)
    e = await enroll(admin, cohort)
    p2 = await pay(admin, e, month=2, amount=300)
    async with sessionmaker() as other:
        await other.execute(text("SELECT 1 FROM enrollment WHERE id = :i FOR UPDATE"), {"i": e})
        edit = asyncio.create_task(admin.patch(f"{P}/{p2['id']}", json={"amount": "400"}))
        await _wait_for_a_lock_waiter()
        await other.execute(
            text("SELECT 1 FROM payment WHERE enrollment_id = :i FOR KEY SHARE"), {"i": e}
        )
        await other.commit()
    r = await edit
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == "400.00"


async def test_hold_waits_for_a_create_of_the_same_enrollment(admin: httpx.AsyncClient) -> None:
    """Same user, two tabs: a hold switching months and a create (enrollment lock, then drop of
    the user's hold) must take turns, not deadlock."""
    cohort = await running_cohort(admin, price=700)
    e = await enroll(admin, cohort)
    assert (await admin.post(H, json={"enrollment_id": e, "month_no": 2})).json()["acquired"]
    async with sessionmaker() as other:
        await other.execute(text("SELECT 1 FROM enrollment WHERE id = :i FOR UPDATE"), {"i": e})
        hold = asyncio.create_task(admin.post(H, json={"enrollment_id": e, "month_no": 3}))
        await _wait_for_a_lock_waiter()
        await other.execute(
            text("DELETE FROM payment_hold WHERE enrollment_id = :i AND month_no = 2"), {"i": e}
        )
        await other.commit()
    r = await hold
    assert r.status_code == 200, r.text
    assert r.json()["acquired"] is True


async def test_one_user_holds_one_month_at_a_time_across_enrollments(
    login_as: SignedIn, admin: httpx.AsyncClient
) -> None:
    """The form greys out «Сохранить» while someone else holds the month: one user must not be
    able to hold every enrollment of the branch at once."""
    cohort = await running_cohort(admin, price=700)
    e1 = await enroll(admin, cohort, "Первый")
    e2 = await enroll(admin, cohort, "Второй")
    anna = await login_as("anna", await manager_role(), branch="Душанбе")
    assert (await admin.post(H, json={"enrollment_id": e1, "month_no": 2})).json()["acquired"]
    assert (await admin.post(H, json={"enrollment_id": e2, "month_no": 1})).json()["acquired"]
    assert (await status(anna, e1))["held_by"] is None
    assert (await status(anna, e2, 1))["held_by"]["name"] == "User root"
    rows = await sql("SELECT count(*) FROM payment_hold")
    assert rows[0][0] == 1


async def test_roles_without_payments_see_no_month_hold_or_card(
    login_as: SignedIn, admin: httpx.AsyncClient
) -> None:
    cohort = await running_cohort(admin, price=700)
    e = await enroll(admin, cohort)
    await pay(admin, e, month=2, amount=300)
    rights: dict[str, Any] = {k: v for k, v in MANAGER_DEFAULT.items() if k != "payments"}
    bob = await login_as("bob", await make_role("Без денег", rights), branch="Душанбе")
    q = {"enrollment_id": e, "month_no": 2}
    assert (await bob.get(f"{P}/month", params=q)).status_code == 403
    assert (await bob.post(H, json=q)).status_code == 403
    assert (await bob.delete(H, params=q)).status_code == 403
    assert (await bob.get(f"{P}/enrollment/{e}")).status_code == 403
    viewer = await make_role("Только просмотр", {**MANAGER_DEFAULT, "payments": "view"})
    vic = await login_as("vic", viewer, branch="Душанбе")
    assert (await vic.get(f"{P}/month", params=q)).status_code == 200
    assert (await vic.post(H, json=q)).status_code == 403
    assert (await vic.post(P, json=body(e, amount="1"))).status_code == 403


async def test_unknown_enrollment_month_and_hold_are_404(admin: httpx.AsyncClient) -> None:
    q = {"enrollment_id": str(uuid.uuid4()), "month_no": 1}
    assert (await admin.get(f"{P}/month", params=q)).status_code == 404
    assert (await admin.get(f"{P}/enrollment/{q['enrollment_id']}")).status_code == 404
