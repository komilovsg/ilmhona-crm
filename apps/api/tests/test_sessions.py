"""«Мои устройства и сессии»: the list, ending sessions, «remember me», the superadmin's view."""

import httpx

from app.auth.devices import device_name
from tests.conftest import PASSWORD, SignedIn, make_client, make_role, make_user, sql

A = "/api/v1/auth"
MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)
IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
)


async def _in(login: str, agent: str, remember: bool = False) -> httpx.AsyncClient:
    c = make_client()
    r = await c.post(
        f"{A}/login",
        json={"login": login, "password": PASSWORD, "remember": remember},
        headers={"User-Agent": agent},
    )
    assert r.status_code == 200, r.text
    return c


def test_device_name() -> None:
    assert device_name(MAC) == "Chrome · macOS"
    assert device_name(IPHONE) == "Safari · iOS"
    assert device_name("Mozilla/5.0 (Windows NT 10.0) Chrome/130 Safari/537 Edg/130") == (
        "Edge · Windows"
    )
    assert device_name(None) == "Неизвестное устройство"


async def test_list_marks_current_device() -> None:
    await make_user("anna", "manager")
    pc = await _in("anna", MAC)
    phone = await _in("anna", IPHONE)
    rows = (await phone.get(f"{A}/sessions")).json()
    assert {r["device"] for r in rows} == {"Chrome · macOS", "Safari · iOS"}
    assert [r["device"] for r in rows if r["current"]] == ["Safari · iOS"]
    assert all(r["created_at"] and r["last_used_at"] for r in rows)
    assert len((await pc.get(f"{A}/sessions")).json()) == 2


async def test_ending_a_session_kills_access_at_once() -> None:
    """The access token carries the family (`sid`): revoking it stops the other device now,
    not when its 15-minute token runs out."""
    await make_user("anna", "manager")
    pc = await _in("anna", MAC)
    phone = await _in("anna", IPHONE)
    assert (await phone.get(f"{A}/me")).status_code == 200
    other = next(r for r in (await pc.get(f"{A}/sessions")).json() if not r["current"])
    assert (await pc.delete(f"{A}/sessions/{other['id']}")).status_code == 204
    assert (await phone.get(f"{A}/me")).status_code == 401
    assert (await phone.post(f"{A}/refresh")).status_code == 401
    assert (await pc.get(f"{A}/me")).status_code == 200
    assert len((await pc.get(f"{A}/sessions")).json()) == 1


async def test_end_all_other_sessions() -> None:
    await make_user("anna", "manager")
    one, two, three = await _in("anna", MAC), await _in("anna", IPHONE), await _in("anna", MAC)
    r = await one.post(f"{A}/sessions/end-others")
    assert r.json() == {"ended": 2}
    assert (await two.get(f"{A}/me")).status_code == 401
    assert (await three.get(f"{A}/me")).status_code == 401
    assert (await one.get(f"{A}/me")).status_code == 200


async def test_ending_own_current_session_signs_out() -> None:
    await make_user("anna", "manager")
    c = await _in("anna", MAC)
    me = (await c.get(f"{A}/sessions")).json()[0]
    assert (await c.delete(f"{A}/sessions/{me['id']}")).status_code == 204
    assert (await c.get(f"{A}/me")).status_code == 401


async def test_other_users_session_is_404() -> None:
    await make_user("anna", "manager")
    await make_user("boris", "manager")
    anna = await _in("anna", MAC)
    boris = await _in("boris", IPHONE)
    theirs = (await boris.get(f"{A}/sessions")).json()[0]["id"]
    r = await anna.delete(f"{A}/sessions/{theirs}")
    assert (r.status_code, r.json()["code"]) == (404, "not_found")
    assert (await boris.get(f"{A}/me")).status_code == 200
    unknown = "00000000-0000-4000-8000-000000000000"
    assert (await anna.delete(f"{A}/sessions/{unknown}")).status_code == 404


async def test_remember_me_cookie_attributes() -> None:
    await make_user("anna", "manager")
    async with make_client() as c:
        r = await c.post(f"{A}/login", json={"login": "anna", "password": PASSWORD})
        cookies = r.headers.get_list("set-cookie")
        assert len(cookies) == 2
        assert all("max-age" not in x.lower() for x in cookies)  # session cookies
        assert all("httponly" in x.lower() for x in cookies)
        hours = await sql("SELECT extract(epoch FROM expires_at - now()) / 3600 FROM refresh_token")
        assert 11.9 < float(hours[0][0]) <= 12
    await sql("DELETE FROM refresh_token")
    async with make_client() as c:
        r = await c.post(
            f"{A}/login", json={"login": "anna", "password": PASSWORD, "remember": True}
        )
        cookies = r.headers.get_list("set-cookie")
        assert all(f"max-age={30 * 86400}" in x.lower() for x in cookies)
        days = await sql("SELECT extract(epoch FROM expires_at - now()) / 86400 FROM refresh_token")
        assert 29.9 < float(days[0][0]) <= 30.001  # db now() vs app clock skew


async def test_remember_choice_and_device_survive_refresh() -> None:
    await make_user("anna", "manager")
    c = await _in("anna", MAC)
    assert (await c.post(f"{A}/refresh")).status_code == 204
    rows = await sql("SELECT remember, user_agent, expires_at - now() FROM refresh_token")
    assert len(rows) == 2 and all(r[0] is False and r[1] == MAC for r in rows)
    assert all(r[2].total_seconds() < 12 * 3600 + 5 for r in rows)
    assert (await c.get(f"{A}/sessions")).json()[0]["remember"] is False
    r = await c.post(f"{A}/refresh")
    assert all("max-age" not in x.lower() for x in r.headers.get_list("set-cookie"))


async def test_idle_session_expires() -> None:
    await make_user("anna", "manager")
    c = await _in("anna", MAC)
    await sql("UPDATE refresh_token SET expires_at = now() - interval '1 minute'")
    assert (await c.post(f"{A}/refresh")).status_code == 401


async def test_expired_session_is_not_listed() -> None:
    await make_user("anna", "manager")
    c = await _in("anna", MAC)
    await _in("anna", IPHONE)
    await sql(
        "UPDATE refresh_token SET expires_at = now() - interval '1 hour' WHERE user_agent = :a",
        a=IPHONE,
    )
    assert [r["device"] for r in (await c.get(f"{A}/sessions")).json()] == ["Chrome · macOS"]


async def test_password_change_keeps_this_device_only() -> None:
    await make_user("anna", "manager")
    pc = await _in("anna", MAC)
    phone = await _in("anna", IPHONE)
    r = await pc.post(
        f"{A}/change-password",
        json={"current_password": PASSWORD, "new_password": "N3w-Passw0rd!z"},
    )
    assert r.status_code == 200
    assert (await phone.get(f"{A}/me")).status_code == 401
    rows = (await pc.get(f"{A}/sessions")).json()
    assert [x["device"] for x in rows] == ["Chrome · macOS"]


async def test_superadmin_sees_and_ends_any_users_sessions(admin: httpx.AsyncClient) -> None:
    uid = await make_user("anna", "manager", branch="Душанбе")
    anna = await _in("anna", IPHONE)
    rows = (await admin.get(f"/api/v1/users/{uid}/sessions")).json()
    assert [r["device"] for r in rows] == ["Safari · iOS"]
    path = f"/api/v1/users/{uid}/sessions/{rows[0]['id']}"
    assert (await admin.delete(path)).status_code == 204
    assert (await anna.get(f"{A}/me")).status_code == 401
    assert (await admin.delete(path)).status_code == 404


async def test_only_superadmin_manages_other_users_sessions(login_as: SignedIn) -> None:
    uid = await make_user("anna", "manager")
    manager = await login_as("hanna", "manager")  # no `users` right at all
    assert (await manager.get(f"/api/v1/users/{uid}/sessions")).status_code == 403
    role = await make_role("Кадры", {"users": "change"})
    hr = await login_as("hr", role)
    assert (await hr.get(f"/api/v1/users/{uid}/sessions")).status_code == 403  # not a superadmin
    assert (await hr.delete(f"/api/v1/users/{uid}/sessions/{uid}")).status_code == 403


async def test_session_endings_are_audited() -> None:
    await make_user("anna", "manager")
    pc = await _in("anna", MAC)
    await _in("anna", IPHONE)
    await pc.post(f"{A}/sessions/end-others")
    rows = await sql("SELECT action FROM audit_log WHERE action LIKE 'auth.session%'")
    assert [r[0] for r in rows] == ["auth.session_end_others"]


async def test_branch_bound_superadmin_sees_only_own_branch_sessions(login_as: SignedIn) -> None:
    uid = await make_user("anna", "manager", branch="Истаравшан")
    await _in("anna", MAC)
    boss = await login_as("boss", "superadmin", branch="Душанбе")
    assert (await boss.get(f"/api/v1/users/{uid}")).status_code == 404
    assert (await boss.get(f"/api/v1/users/{uid}/sessions")).status_code == 404
    sid = (await sql("SELECT family_id FROM refresh_token WHERE user_agent = :a", a=MAC))[0][0]
    assert (await boss.delete(f"/api/v1/users/{uid}/sessions/{sid}")).status_code == 404


async def test_session_cookies_have_no_expiry_without_remember() -> None:
    await make_user("anna", "manager")
    c = await _in("anna", MAC)
    r = await c.post(f"{A}/refresh")
    assert all("expires" not in x.lower() for x in r.headers.get_list("set-cookie"))
