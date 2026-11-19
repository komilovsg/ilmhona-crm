"""«Ведёт занятия»: who may be a cohort's instructor is the `teaches` flag, not the role. The
role still gives rights; the instructor role still narrows the scope to own cohorts."""

import asyncio

import httpx
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import SERVER_URL, TEST_DB, SignedIn, make_role, make_user, sql
from tests.edu import C, body, make_cohort, make_course, make_room

INS = "/api/v1/instructors"


async def uid(login: str) -> str:
    return str((await sql("SELECT id FROM app_user WHERE login = :l", l=login))[0][0])


async def test_teaching_superadmin_is_assignable_and_sees_everything(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    boss = await login_as("boss", "superadmin", teaches=True)
    boss_id = await uid("boss")
    course = await make_course()
    mine = await make_cohort(admin, course, await make_room(name="A"), instructor_id=boss_id)
    other = await make_cohort(
        admin, course, await make_room(name="B"), start_time="14:00", end_time="15:00"
    )
    r = await admin.patch(f"{C}/{other['id']}", json={"instructor_id": boss_id})
    assert r.status_code == 200, r.text
    await make_cohort(admin, course, await make_room(name="C"))
    # not scoped to own cohorts: the superadmin sees all three
    listed = (await boss.get(C)).json()
    assert listed["total"] == 3 and mine["id"] in {c["id"] for c in listed["items"]}


async def test_instructor_role_with_flag_stays_scoped(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    ins = await login_as("ins", "instructor", branch="Душанбе")
    course = await make_course()
    mine = await make_cohort(
        admin, course, await make_room(name="A"), instructor_id=await uid("ins")
    )
    await make_cohort(admin, course, await make_room(name="B"))
    listed = (await ins.get(C)).json()
    assert [c["id"] for c in listed["items"]] == [mine["id"]]
    assert (await ins.get("/api/v1/auth/me")).json()["teaches"] is True


async def test_not_teaching_user_is_invalid_instructor(
    admin: httpx.AsyncClient,
) -> None:
    await make_user("mgr", "manager", branch="Душанбе")
    await make_user("sa2", "superadmin")  # teaches=false
    course = await make_course()
    for n, login in enumerate(("mgr", "sa2")):
        r = await admin.post(
            C,
            json=body(
                course,
                await make_room(name=f"R{n}"),
                branch_id=str((await sql("SELECT id FROM branch WHERE name = 'Душанбе'"))[0][0]),
                instructor_id=await uid(login),
            ),
        )
        assert (r.status_code, r.json()["code"]) == (422, "instructor_invalid"), login
    cohort = await make_cohort(admin, course, await make_room(name="Z"))
    r = await admin.patch(f"{C}/{cohort['id']}", json={"instructor_id": await uid("mgr")})
    assert r.json()["code"] == "instructor_invalid"


async def test_instructor_choices_follow_the_flag(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    await make_user("boss", "superadmin", teaches=True)
    await make_user("mgr", "manager", branch="Душанбе")
    await make_user("ins", "instructor", branch="Душанбе")
    await make_user("plain_ins", "instructor", branch="Душанбе", teaches=False)
    names = {i["full_name"] for i in (await admin.get(f"{C}/instructors")).json()}
    assert names == {"User boss", "User ins"}


async def test_teaching_user_without_instructors_right_sees_only_own_money(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    role = await make_role("Преподающий", {"cohorts": "view"})
    me = await login_as("teacher", role, branch="Душанбе", teaches=True)
    me_id = await uid("teacher")
    await make_user("ins2", "instructor", branch="Душанбе")
    plain = await login_as("plain", role, branch="Душанбе")
    r = await me.get(f"{INS}/{me_id}")
    assert r.status_code == 200 and r.json()["id"] == me_id
    r = await me.get(f"{INS}/{await uid('ins2')}")
    assert r.status_code == 404
    assert (await me.get("/api/v1/salaries?month=all")).status_code == 200
    assert (await me.get("/api/v1/payouts")).status_code == 200
    # the flag is the only way in: a non-teaching user has no instructors right
    assert (await plain.get(f"{INS}/{await uid('plain')}")).status_code == 403
    assert (await plain.get("/api/v1/payouts")).status_code == 403
    # and the list of instructors stays closed to them
    assert (await me.get(INS)).status_code == 403


async def test_teaching_superadmin_card_and_other_card(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    boss = await login_as("boss", "superadmin", teaches=True)
    await make_user("ins", "instructor", branch="Душанбе")
    assert (await boss.get(f"{INS}/{await uid('boss')}")).status_code == 200
    assert (await boss.get(f"{INS}/{await uid('ins')}")).status_code == 200  # existing rights
    ids = {i["id"] for i in (await boss.get(INS)).json()["items"]}
    assert ids == {await uid("boss"), await uid("ins")}


async def test_users_api_carries_teaches(admin: httpx.AsyncClient) -> None:
    from tests.conftest import role_id

    r = await admin.post(
        "/api/v1/users",
        json={
            "login": "newbie",
            "full_name": "Новый",
            "role_id": str(await role_id("manager")),
            "teaches": True,
        },
    )
    assert r.status_code == 201 and r.json()["user"]["teaches"] is True
    user = r.json()["user"]
    r = await admin.patch(f"/api/v1/users/{user['id']}", json={"teaches": False})
    assert r.status_code == 200 and r.json()["teaches"] is False
    r = await admin.post(
        "/api/v1/users",
        json={"login": "plain", "full_name": "Обычный", "role_id": str(await role_id("manager"))},
    )
    assert r.json()["user"]["teaches"] is False
    audit = await sql(
        "SELECT diff FROM audit_log WHERE action = 'user.update' AND entity_id = :i", i=user["id"]
    )
    assert "teaches" in audit[0][0]


async def test_migration_0020_flags_instructor_role_users() -> None:
    name = f"{TEST_DB}_mig_teaches"
    url = SERVER_URL.set(database=name)
    server = create_async_engine(SERVER_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")
    async with server.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url.render_as_string(hide_password=False))
    engine = create_async_engine(url)
    try:
        await asyncio.to_thread(command.upgrade, cfg, "0019")
        async with engine.begin() as conn:
            for login, code in (("a", "instructor"), ("b", "manager"), ("c", "superadmin")):
                await conn.execute(
                    text(
                        "INSERT INTO app_user (login, full_name, role_id, password_hash) "
                        "SELECT CAST(:l AS text), CAST(:l AS text), id, 'x' FROM role WHERE code = :c"
                    ),
                    {"l": login, "c": code},
                )
        await asyncio.to_thread(command.upgrade, cfg, "0020")
        async with engine.connect() as conn:
            rows = (await conn.execute(text("SELECT login, teaches FROM app_user"))).all()
        assert dict(rows) == {"a": True, "b": False, "c": False}
        await asyncio.to_thread(command.downgrade, cfg, "0019")
        async with engine.connect() as conn:
            cols = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE table_name = 'app_user' AND column_name = 'teaches'"
                    )
                )
            ).scalar_one()
        assert cols == 0
    finally:
        await engine.dispose()
        async with server.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await server.dispose()
