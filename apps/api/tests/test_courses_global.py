"""Courses are shared by both branches: only users without a branch change them."""

import httpx

from tests.conftest import SignedIn, make_role
from tests.edu import make_course

C = "/api/v1/courses"
BODY = {"name": "Design", "duration_months": 3, "format": "offline"}


async def test_a_branch_bound_user_cannot_create_edit_or_delete_courses(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    role = await make_role("Менеджер ЦО", {"rooms": "change", "cohorts": "view"})
    mgr = await login_as("dush", role, branch="Душанбе")
    course = await make_course("Python")
    for call in (
        mgr.post(C, json=BODY),
        mgr.patch(f"{C}/{course}", json={"duration_months": 6}),
        mgr.delete(f"{C}/{course}"),
    ):
        r = await call
        assert (r.status_code, r.json()["code"]) == (403, "course_global_only")
    # reading stays open, nothing changed
    assert [c["name"] for c in (await mgr.get(C)).json()] == ["Python"]
    assert (await mgr.get(C)).json()[0]["duration_months"] == 3


async def test_a_user_without_a_branch_manages_courses(login_as: SignedIn) -> None:
    role = await make_role("Менеджер без филиала", {"rooms": "change"})
    mgr = await login_as("anywhere", role)
    created = await mgr.post(C, json=BODY)
    assert created.status_code == 201
    cid = created.json()["id"]
    assert (await mgr.patch(f"{C}/{cid}", json={"duration_months": 6})).json()[
        "duration_months"
    ] == 6
    assert (await mgr.delete(f"{C}/{cid}")).status_code == 204
