"""Regression tests of the stage 0 security review."""

import asyncio

import httpx
import pytest

from app.core.config import DEV_JWT_SECRET, Settings
from app.core.proxy import ProxySecretRequired
from app.main import app
from tests.conftest import PASSWORD, SignedIn, make_client, make_role, make_user, sign_in, sql

A = "/api/v1/auth"
NEW = "N3w-passw0rd!"


async def test_password_change_ends_other_devices_at_once(browser: SignedIn) -> None:
    await make_user("anna", "manager")
    laptop, phone = browser(), browser()
    await sign_in(laptop, "anna")
    await sign_in(phone, "anna")
    r = await laptop.post(
        f"{A}/change-password", json={"current_password": PASSWORD, "new_password": NEW}
    )
    assert r.status_code == 200
    assert (await phone.get(f"{A}/me")).status_code == 401  # not after the access TTL
    assert (await laptop.get(f"{A}/me")).status_code == 200


async def test_access_token_copied_before_logout_is_dead(client: httpx.AsyncClient) -> None:
    await make_user("anna", "manager")
    await sign_in(client, "anna")
    stolen = client.cookies.get("ilm_access")
    assert (await client.post(f"{A}/logout")).status_code == 204
    async with make_client() as thief:
        thief.cookies.set("ilm_access", stolen)
        assert (await thief.get(f"{A}/me")).status_code == 401


async def test_access_token_survives_refresh_rotation(client: httpx.AsyncClient) -> None:
    await make_user("anna", "manager")
    await sign_in(client, "anna")
    for _ in range(3):
        assert (await client.post(f"{A}/refresh")).status_code == 204
        assert (await client.get(f"{A}/me")).status_code == 200


async def test_refresh_token_used_twice_at_once_gives_one_session(
    client: httpx.AsyncClient,
) -> None:
    await make_user("anna", "manager")
    await sign_in(client, "anna")
    token = client.cookies.get("ilm_refresh", path="/api/v1/auth")
    clients = [make_client() for _ in range(5)]
    for c in clients:
        c.cookies.set("ilm_refresh", token, path="/api/v1/auth")
    try:
        codes = await asyncio.gather(*(c.post(f"{A}/refresh") for c in clients))
    finally:
        for c in clients:
            await c.aclose()
    assert sorted(r.status_code for r in codes) == [204, 401, 401, 401, 401]
    assert (await sql("SELECT count(*) FROM refresh_token"))[0][0] == 2


async def test_expired_temp_password_cannot_be_changed_in_an_old_session(
    client: httpx.AsyncClient,
) -> None:
    await make_user("anna", "manager", must_change=True)
    await sql("UPDATE app_user SET temp_password_expires_at = now() + interval '1 day'")
    await sign_in(client, "anna")
    await sql("UPDATE app_user SET temp_password_expires_at = now() - interval '1 minute'")
    assert (await client.post(f"{A}/refresh")).status_code == 401
    r = await client.post(
        f"{A}/change-password", json={"current_password": PASSWORD, "new_password": NEW}
    )
    assert r.json()["code"] == "temp_password_expired"


async def test_cannot_delete_a_role_above_own_rights(login_as: SignedIn) -> None:
    hr = await make_role("HR", {"users": "change"})
    finance = await make_role("Финансы", {"payments": "change"})
    c = await login_as("hr", hr)
    r = await c.delete(f"/api/v1/roles/{finance}")
    assert (r.status_code, r.json()["code"]) == (403, "role_not_assignable")


SECRET = "s" * 40


@pytest.fixture
async def guarded() -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ProxySecretRequired(app, [SECRET.encode()])),
        base_url="http://test",
        headers={"X-Requested-With": "ilm"},
    ) as c:
        yield c


async def test_api_refuses_callers_that_bypass_the_web_proxy(guarded: httpx.AsyncClient) -> None:
    await make_user("anna", "manager")
    body = {"login": "anna", "password": PASSWORD}
    r = await guarded.post(f"{A}/login", json=body)
    assert (r.status_code, r.json()["code"]) == (403, "proxy_required")
    r = await guarded.post(f"{A}/login", json=body, headers={"X-Proxy-Secret": "wrong"})
    assert r.status_code == 403
    r = await guarded.post(f"{A}/login", json=body, headers={"X-Proxy-Secret": SECRET})
    assert r.status_code == 200
    assert (await guarded.get("/api/health")).status_code == 200


def _prod(**kw: object) -> Settings:
    base: dict[str, object] = {
        "env": "production",
        "jwt_secret": "x" * 48,
        "cookie_secure": True,
        "proxy_shared_secret": SECRET,
    }
    return Settings(**{**base, **kw})  # type: ignore[arg-type]


def test_production_settings_refuse_unsafe_values() -> None:
    _prod().check()
    for bad in (
        {"jwt_secret": DEV_JWT_SECRET},
        {"jwt_secret": "short-secret"},
        {"cookie_secure": False},
        {"proxy_shared_secret": ""},
        {"proxy_shared_secret": "short"},
    ):
        with pytest.raises(RuntimeError):
            _prod(**bad).check()


def test_api_docs_are_off_in_production() -> None:
    assert not _prod().api_docs
    assert Settings(env="development").api_docs
