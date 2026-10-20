from datetime import UTC, datetime, timedelta

import httpx

from app.main import app
from tests.conftest import PASSWORD, SignedIn, make_client, make_user, role_id, sign_in, sql

A = "/api/v1/auth"


async def test_login_sets_httponly_cookies_and_me_works(client: httpx.AsyncClient) -> None:
    await make_user("anna", "manager", branch="Душанбе")
    body = await sign_in(client, "anna")
    assert body["login"] == "anna"
    assert body["branch"]["name"] == "Душанбе"
    assert body["permissions"]["leads"] == "change"
    assert "users" not in body["permissions"]
    r = await client.get(f"{A}/me")
    assert r.status_code == 200
    assert r.json()["role"]["code"] == "manager"


async def test_set_cookie_flags() -> None:
    await make_user("anna", "manager")
    async with make_client() as c:
        r = await c.post(f"{A}/login", json={"login": "anna", "password": PASSWORD})
        flags = [h.lower() for h in r.headers.get_list("set-cookie")]
    assert len(flags) == 2
    assert all("httponly" in f and "samesite=lax" in f for f in flags)
    assert any(f.startswith("ilm_refresh=") and "path=/api/v1/auth" in f for f in flags)


async def test_unknown_login_and_wrong_password_look_the_same(client: httpx.AsyncClient) -> None:
    await make_user("anna", "manager")
    wrong = await client.post(f"{A}/login", json={"login": "anna", "password": "nope-nope-1!"})
    unknown = await client.post(f"{A}/login", json={"login": "ghost", "password": "nope-nope-1!"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["code"] == unknown.json()["code"] == "invalid_credentials"
    assert wrong.json() == {**unknown.json(), "instance": wrong.json()["instance"]}


async def test_deactivated_user_cannot_sign_in_and_loses_session(
    client: httpx.AsyncClient,
) -> None:
    await make_user("anna", "manager")
    await sign_in(client, "anna")
    await sql("UPDATE app_user SET is_active = false")
    assert (await client.get(f"{A}/me")).status_code == 401
    r = await client.post(f"{A}/login", json={"login": "anna", "password": PASSWORD})
    assert r.json()["code"] == "invalid_credentials"


async def test_lockout_after_repeated_failures(client: httpx.AsyncClient) -> None:
    await make_user("anna", "manager")
    for _ in range(5):
        r = await client.post(f"{A}/login", json={"login": "anna", "password": "bad-bad-1!"})
        assert r.json()["code"] == "invalid_credentials"
    # locked: even the right password is refused
    r = await client.post(f"{A}/login", json={"login": "anna", "password": PASSWORD})
    assert r.status_code == 429
    assert r.json()["code"] == "too_many_attempts"
    # after the window it works again
    await sql("UPDATE login_attempt SET locked_until = now() - interval '1 minute'")
    await sign_in(client, "anna")


async def test_lockout_is_the_same_for_unknown_logins(client: httpx.AsyncClient) -> None:
    for _ in range(5):
        await client.post(f"{A}/login", json={"login": "ghost", "password": "bad-bad-1!"})
    r = await client.post(f"{A}/login", json={"login": "ghost", "password": "bad-bad-1!"})
    assert r.json()["code"] == "too_many_attempts"


async def test_success_resets_failure_counter(client: httpx.AsyncClient) -> None:
    await make_user("anna", "manager")
    for _ in range(4):
        await client.post(f"{A}/login", json={"login": "anna", "password": "bad-bad-1!"})
    await sign_in(client, "anna")
    for _ in range(4):
        await client.post(f"{A}/login", json={"login": "anna", "password": "bad-bad-1!"})
    await sign_in(client, "anna")


async def test_missing_csrf_header_is_refused() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        r = await c.post(f"{A}/login", json={"login": "a", "password": "b"})
    assert r.status_code == 403
    assert r.json()["code"] == "csrf_header_missing"


async def test_temp_password_forces_change_and_blocks_everything_else(
    admin: httpx.AsyncClient, client: httpx.AsyncClient
) -> None:
    rid = await role_id("manager")
    created = (
        await admin.post(
            "/api/v1/users", json={"login": "newbie", "full_name": "Новичок", "role_id": str(rid)}
        )
    ).json()
    temp = created["temp_password"]
    assert created["user"]["must_change_password"] is True
    body = await sign_in(client, "newbie", temp)
    assert body["must_change_password"] is True
    # the only allowed call is change-password (refresh and logout keep working too)
    for path in (
        "/api/v1/users",
        "/api/v1/auth/me",
        "/api/v1/roles",
        "/api/v1/audit",
        "/api/v1/branches",
    ):
        r = await client.get(path)
        assert (r.status_code, r.json()["code"]) == (403, "password_change_required"), path
    r = await client.post(
        f"{A}/change-password", json={"current_password": temp, "new_password": "Brand-new-1"}
    )
    assert r.status_code == 200
    assert r.json()["must_change_password"] is False
    assert (await client.get(f"{A}/me")).status_code == 200
    # the temp password is dead
    async with make_client() as other:
        r = await other.post(f"{A}/login", json={"login": "newbie", "password": temp})
        assert r.status_code == 401


async def test_expired_temp_password_is_a_clear_error(client: httpx.AsyncClient) -> None:
    await make_user("late", "manager", must_change=True)
    await sql(
        "UPDATE app_user SET temp_password_expires_at = :t", t=datetime.now(UTC) - timedelta(days=1)
    )
    r = await client.post(f"{A}/login", json={"login": "late", "password": PASSWORD})
    assert r.status_code == 401
    assert r.json()["code"] == "temp_password_expired"
    # a wrong password for the same account stays a plain invalid_credentials
    r = await client.post(f"{A}/login", json={"login": "late", "password": "bad-bad-1!"})
    assert r.json()["code"] == "invalid_credentials"


async def test_unexpired_temp_password_works(client: httpx.AsyncClient) -> None:
    await make_user("fresh", "manager", must_change=True)
    await sql(
        "UPDATE app_user SET temp_password_expires_at = :t", t=datetime.now(UTC) + timedelta(days=6)
    )
    body = await sign_in(client, "fresh")
    assert body["must_change_password"] is True


async def test_change_password_rules(client: httpx.AsyncClient) -> None:
    await make_user("anna", "manager")
    await sign_in(client, "anna")
    url = f"{A}/change-password"
    r = await client.post(
        url, json={"current_password": "wrong-one-1!", "new_password": "Brand-new-1"}
    )
    assert r.json()["code"] == "wrong_password"
    r = await client.post(url, json={"current_password": PASSWORD, "new_password": PASSWORD})
    assert r.json()["code"] == "same_password"
    r = await client.post(url, json={"current_password": PASSWORD, "new_password": "weak"})
    assert r.json()["code"] == "weak_password"
    r = await client.post(url, json={"current_password": PASSWORD, "new_password": "Brand-new-1"})
    assert r.status_code == 200


async def test_refresh_rotates_and_reuse_kills_the_family(client: httpx.AsyncClient) -> None:
    await make_user("anna", "manager")
    await sign_in(client, "anna")
    old = client.cookies.get("ilm_refresh", path="/api/v1/auth")
    assert old
    r = await client.post(f"{A}/refresh")
    assert r.status_code == 204
    new = client.cookies.get("ilm_refresh", path="/api/v1/auth")
    assert new and new != old
    assert (await client.get(f"{A}/me")).status_code == 200
    # the old token comes back well after rotation: theft is assumed, the family dies
    await sql(
        "UPDATE refresh_token SET used_at = now() - interval '1 hour' WHERE used_at IS NOT NULL"
    )
    async with make_client() as thief:
        thief.cookies.set("ilm_refresh", old, path="/api/v1/auth")
        assert (await thief.post(f"{A}/refresh")).status_code == 401
    assert (await client.post(f"{A}/refresh")).status_code == 401


async def test_refresh_without_cookie_is_401(client: httpx.AsyncClient) -> None:
    assert (await client.post(f"{A}/refresh")).status_code == 401


async def test_logout_revokes_refresh(client: httpx.AsyncClient) -> None:
    await make_user("anna", "manager")
    await sign_in(client, "anna")
    refresh = client.cookies.get("ilm_refresh", path="/api/v1/auth")
    assert (await client.post(f"{A}/logout")).status_code == 204
    assert (await client.get(f"{A}/me")).status_code == 401
    async with make_client() as c:
        c.cookies.set("ilm_refresh", refresh, path="/api/v1/auth")
        assert (await c.post(f"{A}/refresh")).status_code == 401


async def test_profile_update(client: httpx.AsyncClient, login_as: SignedIn) -> None:
    c = await login_as("anna", "manager")
    r = await c.patch(
        f"{A}/me", json={"full_name": "Анна И.", "phone": "+992900000001", "email": "a@x.tj"}
    )
    assert r.status_code == 200
    assert (r.json()["full_name"], r.json()["phone"]) == ("Анна И.", "+992900000001")
