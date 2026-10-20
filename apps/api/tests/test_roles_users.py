import httpx

from tests.conftest import make_role, make_user, role_id, sql

R = "/api/v1/roles"
U = "/api/v1/users"


async def test_seeded_roles_and_matrix(admin: httpx.AsyncClient) -> None:
    roles = {r["code"]: r for r in (await admin.get(R)).json()}
    assert roles["superadmin"]["locked"] and len(roles["superadmin"]["permissions"]) == 13
    assert roles["manager"]["permissions"]["leads"] == "change"
    assert roles["instructor"]["permissions"]["attendance"] == "change"
    assert "users" not in roles["manager"]["permissions"]
    sections = (await admin.get(f"{R}/sections")).json()
    assert len(sections) == 13 and sections[0] == {"key": "dashboard", "label": "Дашборд"}
    names = {b[0] for b in await sql("SELECT name FROM branch")}
    assert names == {"Душанбе", "Истаравшан"}


async def test_superadmin_role_cannot_be_edited_or_deleted(admin: httpx.AsyncClient) -> None:
    rid = str(await role_id("superadmin"))
    r = await admin.put(f"{R}/{rid}", json={"name": "Другое", "permissions": {"users": "view"}})
    assert (r.status_code, r.json()["code"]) == (403, "role_locked")
    r = await admin.delete(f"{R}/{rid}")
    assert (r.status_code, r.json()["code"]) == (403, "role_locked")
    assert len((await admin.get(f"{R}/{rid}")).json()["permissions"]) == 13


async def test_system_roles_are_editable_but_not_deletable(admin: httpx.AsyncClient) -> None:
    rid = str(await role_id("manager"))
    r = await admin.put(f"{R}/{rid}", json={"name": "Менеджер", "permissions": {"leads": "view"}})
    assert r.status_code == 200 and r.json()["permissions"] == {"leads": "view"}
    r = await admin.delete(f"{R}/{rid}")
    assert r.json()["code"] == "role_system"


async def test_custom_role_lifecycle(admin: httpx.AsyncClient) -> None:
    r = await admin.post(
        R, json={"name": "Бухгалтер", "permissions": {"payments": "change", "audit": "view"}}
    )
    assert r.status_code == 201
    rid = r.json()["id"]
    assert r.json()["permissions"] == {"payments": "change", "audit": "view"}
    r = await admin.put(
        R + f"/{rid}",
        json={"name": "Бухгалтер 2", "permissions": {"audit": "change", "leads": "view"}},
    )
    assert r.json()["permissions"] == {"audit": "change", "leads": "view"}
    assert r.json()["name"] == "Бухгалтер 2"
    assert (await admin.delete(f"{R}/{rid}")).status_code == 204
    assert (await admin.get(f"{R}/{rid}")).status_code == 404


async def test_role_validation_and_name_taken(admin: httpx.AsyncClient) -> None:
    r = await admin.post(R, json={"name": "X", "permissions": {"nope": "view"}})
    assert (r.status_code, r.json()["code"]) == (422, "validation_failed")
    r = await admin.post(R, json={"name": "X", "permissions": {"leads": "delete"}})
    assert r.status_code == 422
    assert (await admin.post(R, json={"name": "Dup", "permissions": {}})).status_code == 201
    r = await admin.post(R, json={"name": "Dup", "permissions": {}})
    assert (r.status_code, r.json()["code"]) == (409, "name_taken")


async def test_role_in_use_cannot_be_deleted(admin: httpx.AsyncClient) -> None:
    rid = await make_role("Занята", {"leads": "view"})
    await make_user("holder", rid)
    r = await admin.delete(f"{R}/{rid}")
    assert (r.status_code, r.json()["code"], r.json()["params"]) == (
        409,
        "role_in_use",
        {"users_count": 1},
    )


async def test_user_crud_and_uniqueness(admin: httpx.AsyncClient) -> None:
    ins = str(await role_id("instructor"))
    body = {"login": "kamol", "full_name": "Камол", "phone": "+992900000010", "role_id": ins}
    r = await admin.post(U, json=body)
    assert r.status_code == 201
    user = r.json()["user"]
    assert user["must_change_password"] and user["temp_password_expires_at"]
    assert len(r.json()["temp_password"]) == 12
    assert "password_hash" not in user
    r = await admin.post(U, json={**body, "login": "Kamol"})
    assert (r.status_code, r.json()["code"]) == (409, "login_taken")
    r = await admin.post(U, json={**body, "login": "other"})
    assert (r.status_code, r.json()["code"]) == (409, "phone_taken")
    r = await admin.patch(f"{U}/{user['id']}", json={"phone": None, "email": "k@x.tj"})
    assert (r.json()["phone"], r.json()["email"]) == (None, "k@x.tj")
    assert (await admin.get(U, params={"q": "камол"})).json()["total"] == 1
    assert (await admin.get(U, params={"q": "zzz"})).json()["total"] == 0


async def test_activate_gives_a_new_password_for_seven_days(
    admin: httpx.AsyncClient, client: httpx.AsyncClient
) -> None:
    uid = await make_user("sleepy", "instructor", active=False)
    assert (
        await client.post("/api/v1/auth/login", json={"login": "sleepy", "password": "Passw0rd!x"})
    ).status_code == 401
    r = await admin.post(f"{U}/{uid}/activate")
    assert r.status_code == 200
    out = r.json()
    assert out["user"]["is_active"] and out["user"]["must_change_password"]
    (days,) = (
        await sql(
            "SELECT round(extract(epoch FROM temp_password_expires_at - now()) / 86400) FROM app_user WHERE login = 'sleepy'"
        )
    )[0]
    assert days == 7
    login = await client.post(
        "/api/v1/auth/login", json={"login": "sleepy", "password": out["temp_password"]}
    )
    assert login.status_code == 200 and login.json()["must_change_password"] is True


async def test_reset_revokes_open_sessions(admin: httpx.AsyncClient, login_as) -> None:  # type: ignore[no-untyped-def]
    c = await login_as("anna", "manager")
    uid = (await sql("SELECT id FROM app_user WHERE login = 'anna'"))[0][0]
    assert (await admin.post(f"{U}/{uid}/reset-password")).status_code == 200
    assert (await c.post("/api/v1/auth/refresh")).status_code == 401
    # the short access token still works until it expires, but the reset user must change password
    assert (await c.get("/api/v1/auth/me")).json()["code"] == "password_change_required"


async def test_guards_against_locking_everyone_out(admin: httpx.AsyncClient) -> None:
    me = (await admin.get("/api/v1/auth/me")).json()["id"]
    r = await admin.post(f"{U}/{me}/deactivate")
    assert r.json()["code"] == "cannot_deactivate_self"
    assert (await admin.delete(f"{U}/{me}")).json()["code"] == "cannot_deactivate_self"
    second = await make_user("second", "superadmin")
    root_only = await make_user("third", "manager")
    # two superadmins: one may be deactivated; the last one never
    assert (await admin.post(f"{U}/{second}/deactivate")).status_code == 200
    r = await admin.patch(f"{U}/{me}", json={"role_id": str(await role_id("manager"))})
    assert r.json()["code"] == "last_superadmin"
    assert root_only
