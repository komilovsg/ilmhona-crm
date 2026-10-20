import httpx
import pytest

from app.main import app
from tests.conftest import SignedIn, make_role, make_user, role_id, sql

U = "/api/v1/users"


async def _new_user_body(login: str = "newbie") -> dict[str, str]:
    return {"login": login, "full_name": "Новичок", "role_id": str(await role_id("manager"))}


async def test_unauthenticated_is_401(client: httpx.AsyncClient) -> None:
    for path in (U, "/api/v1/roles", "/api/v1/audit", "/api/v1/branches", "/api/v1/auth/me"):
        r = await client.get(path)
        assert (r.status_code, r.json()["code"]) == (401, "not_authenticated"), path


async def test_every_route_but_the_public_ones_needs_a_session() -> None:
    """A new endpoint that forgets its permission dependency fails here."""
    public = {
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/logout"),
        ("GET", "/api/health"),
    }
    docs = {"/api/docs", "/api/openapi.json", "/api/docs/oauth2-redirect"}
    nil = "00000000-0000-0000-0000-000000000000"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Requested-With": "ilm"},
    ) as c:
        for route in app.routes:
            path = getattr(route, "path", "")
            if path in docs or not path.startswith("/api/"):
                continue
            for method in getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}:
                if (method, path) in public:
                    continue
                r = await c.request(
                    method, path.replace("{user_id}", nil).replace("{role_id}", nil)
                )
                assert r.status_code == 401, (method, path, r.status_code)


async def test_view_reads_but_cannot_write(login_as: SignedIn) -> None:
    viewer = await login_as("viewer", await make_role("Читатель", {"users": "view"}))
    assert (await viewer.get(U)).status_code == 200
    assert (await viewer.get("/api/v1/roles")).status_code == 200
    r = await viewer.post(U, json=await _new_user_body())
    assert (r.status_code, r.json()["code"]) == (403, "forbidden")
    assert (
        await viewer.post("/api/v1/roles", json={"name": "X", "permissions": {}})
    ).status_code == 403
    assert (await viewer.get("/api/v1/audit")).status_code == 403  # a different section


async def test_change_includes_delete(login_as: SignedIn, admin: httpx.AsyncClient) -> None:
    editor = await login_as("editor", await make_role("Редактор", {"users": "change"}))
    empty_role = await make_role("Пустая", {})
    victim = await make_user("victim", empty_role)
    assert (await editor.get(U)).status_code == 200  # change implies view
    empty = str(empty_role)
    r = await editor.post(U, json={**await _new_user_body(), "role_id": empty})
    assert r.status_code == 201
    assert (await editor.delete(f"{U}/{victim}")).status_code == 204
    assert (await editor.delete(f"{U}/{r.json()['user']['id']}")).status_code == 204


async def test_view_cannot_delete_or_edit_or_reset(login_as: SignedIn) -> None:
    viewer = await login_as("viewer", await make_role("Читатель", {"users": "view"}))
    victim = await make_user("victim", "instructor")
    assert (await viewer.delete(f"{U}/{victim}")).status_code == 403
    assert (await viewer.patch(f"{U}/{victim}", json={"full_name": "X"})).status_code == 403
    assert (await viewer.post(f"{U}/{victim}/activate")).status_code == 403
    assert (await viewer.post(f"{U}/{victim}/deactivate")).status_code == 403


async def test_no_access_without_a_row(login_as: SignedIn) -> None:
    instructor = await login_as("ins", "instructor")
    for path in (U, "/api/v1/roles", "/api/v1/audit"):
        assert (await instructor.get(path)).status_code == 403, path


@pytest.mark.parametrize("section", ["users", "audit"])
async def test_sections_are_independent(login_as: SignedIn, section: str) -> None:
    c = await login_as("one", await make_role("One", {section: "change"}))
    other = "audit" if section == "users" else "users"
    assert (await c.get(f"/api/v1/{section}")).status_code == 200
    assert (await c.get(f"/api/v1/{other}")).status_code == 403


async def test_superadmin_passes_everywhere(admin: httpx.AsyncClient) -> None:
    me = (await admin.get("/api/v1/auth/me")).json()
    assert set(me["permissions"].values()) == {"change"}
    assert len(me["permissions"]) == 13
    for path in (U, "/api/v1/roles", "/api/v1/audit"):
        assert (await admin.get(path)).status_code == 200


async def test_nobody_hands_out_more_than_they_have(
    login_as: SignedIn, admin: httpx.AsyncClient
) -> None:
    helper = await login_as(
        "helper", await make_role("Помощник", {"users": "change", "leads": "view"})
    )
    # superadmin role: never
    r = await helper.post(
        U, json={**await _new_user_body(), "role_id": str(await role_id("superadmin"))}
    )
    assert (r.status_code, r.json()["code"]) == (403, "role_not_assignable")
    # manager role has leads: change, the helper only view
    r = await helper.post(U, json=await _new_user_body())
    assert r.json()["code"] == "role_not_assignable"
    # a role within the helper's own rights is fine
    ok = await make_role("Только лиды", {"leads": "view"})
    r = await helper.post(U, json={**await _new_user_body(), "role_id": str(ok)})
    assert r.status_code == 201
    # the helper cannot create or widen roles beyond their rights
    r = await helper.post(
        "/api/v1/roles", json={"name": "Big", "permissions": {"payments": "change"}}
    )
    assert r.json()["code"] == "role_not_assignable"
    r = await helper.post("/api/v1/roles", json={"name": "Small", "permissions": {"leads": "view"}})
    assert r.status_code == 201


async def test_cannot_touch_a_user_above_you(login_as: SignedIn) -> None:
    helper = await login_as("helper", await make_role("Помощник", {"users": "change"}))
    boss = await make_user("boss", "superadmin")
    for call in (
        helper.post(f"{U}/{boss}/activate"),  # would be an account takeover
        helper.post(f"{U}/{boss}/deactivate"),
        helper.patch(f"{U}/{boss}", json={"full_name": "x"}),
        helper.delete(f"{U}/{boss}"),
    ):
        r = await call
        assert (r.status_code, r.json()["code"]) == (403, "role_not_assignable")
    assert (await sql("SELECT is_active FROM app_user WHERE login = 'boss'"))[0][0] is True
