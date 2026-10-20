import httpx

from tests.conftest import SignedIn, branch_id, make_role, make_user, role_id

U = "/api/v1/users"


async def _dushanbe_manager(login_as: SignedIn) -> httpx.AsyncClient:
    role = await make_role(
        "Менеджер ЦО",
        {
            "users": "change",
            "audit": "view",
            "cohorts": "view",
            "attendance": "change",
            "instructors": "view",
        },
    )
    return await login_as("dushanbe_mgr", role, branch="Душанбе")


async def test_manager_of_dushanbe_gets_404_on_a_user_of_istaravshan(login_as: SignedIn) -> None:
    mgr = await _dushanbe_manager(login_as)
    other = await make_user("istar_ins", "instructor", branch="Истаравшан")
    mine = await make_user("dush_ins", "instructor", branch="Душанбе")
    for call in (
        mgr.get(f"{U}/{other}"),
        mgr.patch(f"{U}/{other}", json={"full_name": "x"}),
        mgr.post(f"{U}/{other}/activate"),
        mgr.post(f"{U}/{other}/deactivate"),
        mgr.delete(f"{U}/{other}"),
    ):
        r = await call
        assert (r.status_code, r.json()["code"]) == (404, "not_found")
    assert (await mgr.get(f"{U}/{mine}")).status_code == 200


async def test_list_shows_own_branch_only(login_as: SignedIn) -> None:
    mgr = await _dushanbe_manager(login_as)
    await make_user("dush_ins", "instructor", branch="Душанбе")
    await make_user("istar_ins", "instructor", branch="Истаравшан")
    await make_user("global_ins", "instructor")  # no branch = all branches: not in scope
    logins = {u["login"] for u in (await mgr.get(U)).json()["items"]}
    assert logins == {"dushanbe_mgr", "dush_ins"}
    # asking for the other branch does not widen it
    other = await branch_id("Истаравшан")
    assert (await mgr.get(U, params={"branch_id": str(other)})).json()["total"] == 0


async def test_unbound_user_sees_everyone(admin: httpx.AsyncClient) -> None:
    await make_user("a", "instructor", branch="Душанбе")
    await make_user("b", "instructor", branch="Истаравшан")
    assert (await admin.get(U)).json()["total"] == 3


async def test_create_is_forced_into_own_branch(login_as: SignedIn) -> None:
    mgr = await _dushanbe_manager(login_as)
    ins = str(await role_id("instructor"))
    r = await mgr.post(U, json={"login": "new1", "full_name": "Н", "role_id": ins})
    assert r.status_code == 201
    assert r.json()["user"]["branch_name"] == "Душанбе"
    r = await mgr.post(
        U,
        json={
            "login": "new2",
            "full_name": "Н",
            "role_id": ins,
            "branch_id": str(await branch_id("Истаравшан")),
        },
    )
    assert (r.status_code, r.json()["code"]) == (403, "branch_forbidden")


async def test_cannot_move_a_user_to_another_branch(login_as: SignedIn) -> None:
    mgr = await _dushanbe_manager(login_as)
    mine = await make_user("dush_ins", "instructor", branch="Душанбе")
    other = str(await branch_id("Истаравшан"))
    r = await mgr.patch(f"{U}/{mine}", json={"branch_id": other})
    assert r.json()["code"] == "branch_forbidden"
    r = await mgr.patch(f"{U}/{mine}", json={"branch_id": None})  # nor widen to all branches
    assert r.status_code == 200 and r.json()["branch_name"] == "Душанбе"


async def test_branch_bound_user_cannot_write_roles(login_as: SignedIn) -> None:
    mgr = await _dushanbe_manager(login_as)
    r = await mgr.post("/api/v1/roles", json={"name": "Z", "permissions": {"leads": "view"}})
    assert (r.status_code, r.json()["code"]) == (403, "branch_forbidden")


async def test_branches_list_is_scoped(login_as: SignedIn, admin: httpx.AsyncClient) -> None:
    mgr = await _dushanbe_manager(login_as)
    assert [b["name"] for b in (await mgr.get("/api/v1/branches")).json()] == ["Душанбе"]
    assert [b["name"] for b in (await admin.get("/api/v1/branches")).json()] == [
        "Душанбе",
        "Истаравшан",
    ]


async def test_audit_is_scoped(login_as: SignedIn, admin: httpx.AsyncClient) -> None:
    mgr = await _dushanbe_manager(login_as)
    ins = str(await role_id("instructor"))
    for login, branch in (("dush1", "Душанбе"), ("istar1", "Истаравшан")):
        r = await admin.post(
            U,
            json={
                "login": login,
                "full_name": "X",
                "role_id": ins,
                "branch_id": str(await branch_id(branch)),
            },
        )
        assert r.status_code == 201
    items = (await mgr.get("/api/v1/audit", params={"action": "user.create"})).json()["items"]
    assert len(items) == 1
    assert items[0]["diff"]["login"][1] == "dush1"
