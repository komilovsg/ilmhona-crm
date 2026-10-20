import httpx

from tests.conftest import SignedIn, make_user, role_id, sql

U = "/api/v1/users"


async def _audit(c: httpx.AsyncClient, **params: str) -> list[dict]:  # type: ignore[type-arg]
    r = await c.get("/api/v1/audit", params=params)
    assert r.status_code == 200
    return r.json()["items"]  # type: ignore[no-any-return]


async def test_user_create_update_activate_deactivate_delete_are_audited(
    admin: httpx.AsyncClient,
) -> None:
    ins = str(await role_id("instructor"))
    created = (
        await admin.post(U, json={"login": "kamol", "full_name": "Камол", "role_id": ins})
    ).json()
    uid, temp = created["user"]["id"], created["temp_password"]
    await admin.patch(f"{U}/{uid}", json={"full_name": "Камол Р.", "phone": "+992900000002"})
    await admin.post(f"{U}/{uid}/activate")
    await admin.post(f"{U}/{uid}/deactivate")
    await admin.delete(f"{U}/{uid}")

    items = await _audit(admin, entity="app_user", entity_id=uid)
    actions = [i["action"] for i in reversed(items)]
    assert actions == [
        "user.create",
        "user.update",
        "user.reset_password",
        "user.deactivate",
        "user.delete",
    ]
    by_action = {i["action"]: i for i in items}
    assert by_action["user.create"]["diff"]["login"] == [None, "kamol"]
    assert by_action["user.update"]["diff"] == {
        "full_name": ["Камол", "Камол Р."],
        "phone": [None, "+992900000002"],
    }
    assert by_action["user.deactivate"]["diff"] == {"is_active": [True, False]}
    assert by_action["user.delete"]["diff"]["login"] == ["kamol", None]
    assert all(i["user_login"] == "root" for i in items)
    # nothing secret is ever written to the log
    dump = str(await sql("SELECT diff::text FROM audit_log"))
    assert temp not in dump and "argon2" not in dump and "password_hash" not in dump


async def test_role_changes_are_audited(admin: httpx.AsyncClient) -> None:
    r = await admin.post(
        "/api/v1/roles", json={"name": "Бухгалтер", "permissions": {"payments": "view"}}
    )
    rid = r.json()["id"]
    await admin.put(
        f"/api/v1/roles/{rid}",
        json={"name": "Бухгалтер", "permissions": {"payments": "change", "leads": "view"}},
    )
    await admin.delete(f"/api/v1/roles/{rid}")
    items = {i["action"]: i for i in await _audit(admin, entity="role", entity_id=rid)}
    assert items["role.create"]["diff"]["permissions"] == {"payments": [None, "view"]}
    assert items["role.update"]["diff"] == {
        "permissions": {"payments": ["view", "change"], "leads": [None, "view"]}
    }
    assert items["role.delete"]["diff"]["name"] == ["Бухгалтер", None]


async def test_login_password_change_and_profile_are_audited(login_as: SignedIn) -> None:
    c = await login_as("anna", "manager")
    await c.patch("/api/v1/auth/me", json={"full_name": "Анна", "phone": None, "email": None})
    await c.post(
        "/api/v1/auth/change-password",
        json={"current_password": "Passw0rd!x", "new_password": "Brand-new-1"},
    )
    actions = {a[0] for a in await sql("SELECT action FROM audit_log")}
    assert {"auth.login", "profile.update", "auth.change_password"} <= actions


async def test_a_failed_write_leaves_no_entry(admin: httpx.AsyncClient) -> None:
    ins = str(await role_id("instructor"))
    body = {"login": "dup", "full_name": "X", "role_id": ins}
    assert (await admin.post(U, json=body)).status_code == 201
    assert (await admin.post(U, json={**body, "login": "DUP"})).status_code == 409  # citext
    n = (await sql("SELECT count(*) FROM audit_log WHERE action = 'user.create'"))[0][0]
    assert n == 1


async def test_filters_and_paging(admin: httpx.AsyncClient) -> None:
    ins = str(await role_id("instructor"))
    for i in range(5):
        await admin.post(U, json={"login": f"user{i}", "full_name": "X", "role_id": ins})
    root = (await admin.get("/api/v1/auth/me")).json()["id"]
    page1 = (
        await admin.get("/api/v1/audit", params={"action": "user.create", "page_size": "2"})
    ).json()
    assert (page1["total"], len(page1["items"])) == (5, 2)
    page3 = (
        await admin.get(
            "/api/v1/audit", params={"action": "user.create", "page_size": "2", "page": "3"}
        )
    ).json()
    assert len(page3["items"]) == 1
    ids = [i["id"] for i in page1["items"]]
    assert ids == sorted(ids, reverse=True)  # newest first
    assert len(await _audit(admin, user_id=root)) >= 5
    nobody = await make_user("quiet", "manager")
    assert await _audit(admin, user_id=str(nobody)) == []
    assert await _audit(admin, entity="role") == []
