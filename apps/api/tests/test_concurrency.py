"""#25: in the old system two people editing one record summed or multiplied values. Here every
update names the version it loaded; an older one is a 409 that shows who changed the record."""

import asyncio
from pathlib import Path

import httpx

from tests.conftest import SignedIn, make_user, sql
from tests.edu import make_cohort, make_course, make_room, make_student

S = "/api/v1/students"


def at(version: int) -> dict[str, str]:
    return {"X-Record-Version": str(version)}


async def test_bug_25_second_edit_of_the_same_student_is_a_409_and_nothing_is_lost(
    login_as: SignedIn,
) -> None:
    anna = await login_as("anna", "manager")
    boris = await login_as("boris", "manager")
    sid = await make_student("Алиев Алишер", phone="+992900000001")
    loaded_by_both = (await anna.get(f"{S}/{sid}")).json()
    assert loaded_by_both["version"] == 1

    first = await anna.patch(
        f"{S}/{sid}", json={"phone": "+992930000002"}, headers=at(loaded_by_both["version"])
    )
    assert first.status_code == 200 and first.json()["version"] == 2

    second = await boris.patch(
        f"{S}/{sid}", json={"full_name": "Алишер А."}, headers=at(loaded_by_both["version"])
    )
    assert second.status_code == 409
    problem = second.json()
    assert problem["code"] == "stale_version"
    params = problem["params"]
    assert params["version"] == 2
    assert params["changed_by"] == "User anna" and params["changed_at"]
    assert params["current"]["phone"] == "+992930000002"
    # the rejected edit changed nothing, the first edit is intact
    now = (await boris.get(f"{S}/{sid}")).json()
    assert (now["full_name"], now["phone"], now["version"]) == (
        "Алиев Алишер",
        "+992930000002",
        2,
    )


async def test_bug_25_edits_of_different_fields_after_a_reload_both_survive(
    login_as: SignedIn,
) -> None:
    anna = await login_as("anna", "manager")
    boris = await login_as("boris", "manager")
    sid = await make_student("Алиев Алишер", phone="+992900000001")
    v1 = (await anna.get(f"{S}/{sid}")).json()["version"]
    await anna.patch(f"{S}/{sid}", json={"phone": "+992930000002"}, headers=at(v1))
    assert (
        await boris.patch(f"{S}/{sid}", json={"full_name": "Алишер А."}, headers=at(v1))
    ).status_code == 409
    # Boris reloads and sends only his own field on top of the fresh version
    fresh = (await boris.get(f"{S}/{sid}")).json()
    ok = await boris.patch(
        f"{S}/{sid}", json={"full_name": "Алишер А."}, headers=at(fresh["version"])
    )
    assert ok.status_code == 200
    assert (ok.json()["full_name"], ok.json()["phone"], ok.json()["version"]) == (
        "Алишер А.",
        "+992930000002",
        3,
    )


async def test_bug_25_two_edits_at_the_same_moment_one_wins_one_is_rejected(
    login_as: SignedIn,
) -> None:
    anna = await login_as("anna", "manager")
    boris = await login_as("boris", "manager")
    sid = await make_student("Алиев Алишер")
    results = await asyncio.gather(
        anna.patch(f"{S}/{sid}", json={"phone": "+992900000001"}, headers=at(1)),
        boris.patch(f"{S}/{sid}", json={"full_name": "Борис"}, headers=at(1)),
    )
    assert sorted(r.status_code for r in results) == [200, 409]
    assert (await sql("SELECT version FROM student WHERE id = :i", i=sid))[0][0] == 2


async def test_bug_25_version_bumps_on_a_change_and_stays_on_a_no_op(
    admin: httpx.AsyncClient,
) -> None:
    sid = await make_student("Алиев Алишер", phone="+992900000001")
    same = await admin.patch(f"{S}/{sid}", json={"phone": "+992900000001"})
    assert same.json()["version"] == 1  # nothing changed, nothing to conflict with
    for expected, phone in ((2, "+992900000002"), (3, "+992900000003")):
        r = await admin.patch(f"{S}/{sid}", json={"phone": phone})
        assert r.json()["version"] == expected
    # a change made outside the endpoints (a job, a script) moves the version on as well
    await sql("UPDATE student SET gender = 'male' WHERE id = :i", i=sid)
    assert (await admin.get(f"{S}/{sid}")).json()["version"] == 4


async def test_bug_25_an_update_without_a_version_is_refused(admin: httpx.AsyncClient) -> None:
    sid = await make_student("Алиев Алишер")
    r = await admin.patch(f"{S}/{sid}", json={"phone": "+992900000001"}, no_version=True)
    assert (r.status_code, r.json()["code"]) == (428, "version_required")
    r = await admin.patch(
        f"{S}/{sid}", json={"phone": "+992900000001"}, headers={"X-Record-Version": "abc"}
    )
    assert r.status_code == 400
    assert (await sql("SELECT phone FROM student WHERE id = :i", i=sid))[0][0] is None


async def test_bug_25_every_update_endpoint_checks_the_version(admin: httpx.AsyncClient) -> None:
    room, course = await make_room(), await make_course()
    cohort = await make_cohort(admin, course, room)
    student = await make_student("Студент")
    enrolled = (
        await admin.post(
            f"/api/v1/cohorts/{cohort['id']}/enrollments", json={"student_id": str(student)}
        )
    ).json()
    lesson = (await admin.get(f"/api/v1/cohorts/{cohort['id']}/lessons")).json()[0]
    role = (await admin.post("/api/v1/roles", json={"name": "Гонка", "permissions": {}})).json()
    user = await make_user("someone", "instructor")
    me = (await admin.get("/api/v1/auth/me")).json()
    cases = [
        (f"/api/v1/users/{user}", {"full_name": "Х"}),
        ("/api/v1/auth/me", {"full_name": "Я"}),
        (f"/api/v1/rooms/{room}", {"capacity": 7}),
        (f"/api/v1/courses/{course}", {"duration_months": 5}),
        (f"/api/v1/cohorts/{cohort['id']}", {"capacity": 12}),
        (f"/api/v1/lessons/{lesson['id']}", {"start_time": "12:00", "end_time": "13:00"}),
        (f"/api/v1/enrollments/{enrolled['id']}", {"status": "отчислен"}),
        (f"/api/v1/students/{student}", {"full_name": "Новое"}),
    ]
    for url, body in cases:
        assert (await admin.patch(url, json=body, no_version=True)).status_code == 428, url
        stale = await admin.patch(url, json=body, headers=at(99))
        assert (stale.status_code, stale.json()["code"]) == (409, "stale_version"), url
        assert stale.json()["params"]["current"], url
        ok = await admin.patch(url, json=body)  # the current version: through
        assert ok.status_code == 200, (url, ok.text)
    assert me["version"] == 1
    # the role matrix save follows the same rule, and a matrix-only change bumps the role
    put = {"name": "Гонка", "permissions": {"leads": "view"}}
    assert (
        await admin.put(f"/api/v1/roles/{role['id']}", json=put, no_version=True)
    ).status_code == 428
    stale = await admin.put(f"/api/v1/roles/{role['id']}", json=put, headers=at(99))
    assert (stale.status_code, stale.json()["code"]) == (409, "stale_version")
    assert stale.json()["params"]["current"]["permissions"] == {}
    ok = await admin.put(f"/api/v1/roles/{role['id']}", json=put, headers=at(role["version"]))
    assert ok.status_code == 200 and ok.json()["version"] == role["version"] + 1


async def test_bug_25_two_admins_saving_the_role_matrix_do_not_overwrite_each_other(
    login_as: SignedIn,
) -> None:
    one = await login_as("root1", "superadmin")
    two = await login_as("root2", "superadmin")
    role = (await one.post("/api/v1/roles", json={"name": "Бухгалтер", "permissions": {}})).json()
    url = f"/api/v1/roles/{role['id']}"
    a = await one.put(
        url, json={"name": "Бухгалтер", "permissions": {"payments": "change"}}, headers=at(1)
    )
    assert a.status_code == 200
    b = await two.put(
        url, json={"name": "Бухгалтер", "permissions": {"leads": "view"}}, headers=at(1)
    )
    assert b.status_code == 409
    assert b.json()["params"]["changed_by"] == "User root1"
    assert (await two.get(url)).json()["permissions"] == {"payments": "change"}


async def test_bug_25_a_stale_edit_leaves_no_audit_entry(admin: httpx.AsyncClient) -> None:
    sid = await make_student("Алиев Алишер")
    await admin.patch(f"{S}/{sid}", json={"phone": "+992900000001"})
    before = (await sql("SELECT count(*) FROM audit_log WHERE action = 'student.update'"))[0][0]
    await admin.patch(f"{S}/{sid}", json={"phone": "+992900000009"}, headers=at(1))
    after = (await sql("SELECT count(*) FROM audit_log WHERE action = 'student.update'"))[0][0]
    assert before == after == 1


async def test_stale_retry_of_an_already_saved_change_is_a_200(login_as: SignedIn) -> None:
    """A double submit / lost response: the version is old but the record already holds what the
    client sends, so it is answered with the current record, not a conflict with itself."""
    anna = await login_as("anna", "manager")
    sid = await make_student("Алиев Алишер", phone="+992900000001")
    first = await anna.patch(f"{S}/{sid}", json={"phone": "+992930000002"}, headers=at(1))
    assert first.status_code == 200 and first.json()["version"] == 2
    again = await anna.patch(f"{S}/{sid}", json={"phone": "+992930000002"}, headers=at(1))
    assert again.status_code == 200
    assert again.json()["version"] == 2 and again.json()["phone"] == "+992930000002"
    # a different value at the old version is still a real conflict
    other = await anna.patch(f"{S}/{sid}", json={"phone": "+992930000003"}, headers=at(1))
    assert (other.status_code, other.json()["code"]) == (409, "stale_version")


def test_no_standard_conditional_request_headers_in_the_repo() -> None:
    """Vercel's edge evaluates these itself and answers 412 on proxied /api responses even though
    the API already saved the change: the version travels in X-Record-Version only."""
    root = Path(__file__).resolve().parents[3]
    needles = ("if" + "-match", "if" + "-none-match")
    skip = {"node_modules", ".next", ".venv", ".git", "__pycache__", ".mypy_cache", ".ruff_cache"}
    exts = {".py", ".ts", ".tsx", ".md", ".mjs", ".json", ".yml"}
    hits = []
    for base in (root / "apps", root / "docs", root / "CLAUDE.md"):
        for f in [base] if base.is_file() else base.rglob("*"):
            if f.is_file() and f.suffix in exts and not skip & set(f.parts):
                text = f.read_text(errors="ignore").lower()
                hits += [str(f) for n in needles if n in text]
    assert not hits, hits
