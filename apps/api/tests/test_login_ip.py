"""Login lockout per (login, client address) with a higher per-login ceiling, and the daily purge."""

import httpx

from app.cli import purge_login_attempts
from tests.conftest import PASSWORD, make_client, make_user, sign_in, sql

A = "/api/v1/auth"


async def _bad(c: httpx.AsyncClient, login: str, times: int) -> None:
    for _ in range(times):
        await c.post(f"{A}/login", json={"login": login, "password": "bad-bad-1!"})


async def test_lockout_is_per_login_and_address() -> None:
    """Five bad tries from one address lock that address only: the real user, elsewhere, signs in."""
    await make_user("anna", "manager")
    async with make_client("203.0.113.7") as attacker, make_client("198.51.100.4") as anna:
        await _bad(attacker, "anna", 5)
        r = await attacker.post(f"{A}/login", json={"login": "anna", "password": PASSWORD})
        assert (r.status_code, r.json()["code"]) == (429, "too_many_attempts")
        await sign_in(anna, "anna")  # another address is not locked
    # the attacker's address is locked for anna only, not for a different login
    await make_user("boris", "manager")
    async with make_client("203.0.113.7") as same:
        await sign_in(same, "boris")


async def test_per_login_ceiling_across_addresses() -> None:
    """Many addresses, one try each: the higher per-login ceiling still locks the login."""
    await make_user("anna", "manager")
    for n in range(30):
        async with make_client(f"192.0.2.{n + 1}") as c:
            await _bad(c, "anna", 1)
    async with make_client("198.51.100.99") as anna:
        r = await anna.post(f"{A}/login", json={"login": "anna", "password": PASSWORD})
        assert (r.status_code, r.json()["code"]) == (429, "too_many_attempts")
    await sql("UPDATE login_attempt SET locked_until = now() - interval '1 minute'")
    async with make_client("198.51.100.99") as anna:
        await sign_in(anna, "anna")


async def test_success_resets_only_its_own_address_counter() -> None:
    await make_user("anna", "manager")
    async with make_client("203.0.113.7") as other, make_client("198.51.100.4") as anna:
        await _bad(other, "anna", 3)
        await _bad(anna, "anna", 2)
        await sign_in(anna, "anna")
    rows = await sql("SELECT ip, failures FROM login_ip_attempt WHERE login = 'anna'")
    assert [tuple(r) for r in rows] == [("203.0.113.7", 3)]


async def test_daily_purges_old_login_attempts() -> None:
    await sql(
        "INSERT INTO login_attempt (login, failures, updated_at) VALUES "
        "('old', 2, now() - interval '2 days'), ('fresh', 1, now())"
    )
    await sql(
        "INSERT INTO login_ip_attempt (login, ip, failures, updated_at) VALUES "
        "('old', '203.0.113.7', 2, now() - interval '2 days'), ('fresh', '203.0.113.7', 1, now())"
    )
    assert await purge_login_attempts() == 2
    assert [r[0] for r in await sql("SELECT login FROM login_attempt")] == ["fresh"]
    assert [r[0] for r in await sql("SELECT login FROM login_ip_attempt")] == ["fresh"]
