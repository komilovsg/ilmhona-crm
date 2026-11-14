"""Which default layout a user gets, partial saves, and who may save at all."""

import httpx

from tests.conftest import SignedIn, make_role, sql
from tests.test_role_dashboards import PREF, ids, layout, manager, v


async def test_layout_follows_the_branch_not_the_role(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    # an all-branches user who is not the superadmin gets the leadership order, filtered by rights
    role = await make_role(
        "Руководитель", {"dashboard": "view", "payments": "view", "cohorts": "view"}
    )
    boss = await login_as("boss", role)
    got = await layout(boss)
    assert ids(got, visible=True) == [
        "academy_goal",
        "month_hero",
        "timeline",
        "attention",
        "branches_months",
        "courses_income",
        "overview",
    ]
    assert "goals" not in ids(got) and "notes" not in ids(got)
    # a user bound to one branch gets «Мой день», the superadmin role included
    bound = await login_as("bound", "superadmin", branch="Душанбе")
    assert ids(await layout(bound), visible=True)[:2] == ["academy_goal", "queues"]
    assert ids(await layout(admin), visible=True)[1] == "month_hero"


async def test_partial_save_keeps_default_visibility(login_as: SignedIn) -> None:
    mgr = await manager(login_as)
    before = await layout(mgr)
    assert "month_hero" in ids(before, visible=False)
    r = await mgr.put(PREF, json={"order": ["week"], "hidden": []}, headers=v(0))
    assert r.status_code == 200, r.text
    saved = r.json()
    assert ids(saved)[0] == "week"
    assert "month_hero" in ids(saved, visible=False)  # default-hidden stays hidden
    assert set(ids(saved, visible=True)) == set(ids(before, visible=True))
    stored = (await sql("SELECT dashboard FROM user_pref"))[0][0]
    assert "month_hero" in stored["hidden"] and "queues" not in stored["hidden"]


async def test_instructor_cannot_save_a_layout(login_as: SignedIn) -> None:
    ins = await login_as("ins", "instructor", branch="Душанбе")
    r = await ins.put(PREF, json={"order": ["week"], "hidden": []}, headers=v(0))
    assert r.status_code == 403
    r = await ins.put(PREF, json={"reset": True}, headers=v(0))
    assert r.status_code == 403
    assert (await sql("SELECT count(*) FROM user_pref"))[0][0] == 0
    assert (await sql("SELECT count(*) FROM audit_log WHERE entity = 'user_pref'"))[0][0] == 0
