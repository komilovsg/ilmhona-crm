"""Branch scope, instructor scope, rights, and instructor validation for education data."""

import httpx

from tests.conftest import SignedIn, branch_id, make_role, make_user, sql
from tests.edu import (
    C,
    body,
    instructor_rights,
    make_cohort,
    make_course,
    make_room,
    make_student,
    next_monday,
)

STUDENTS = "/api/v1/students"
MGR = {"cohorts": "change", "students": "change", "rooms": "change"}


async def _manager(login_as: SignedIn, branch: str = "Душанбе") -> httpx.AsyncClient:
    role = await make_role(f"Менеджер {branch}", MGR)
    return await login_as(f"mgr_{branch}", role, branch=branch)


async def test_other_branch_is_404_everywhere(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    mgr = await _manager(login_as)
    course = await make_course()
    istar_room = await make_room("Истаравшан", "Istaravshan-1")
    cohort = await make_cohort(admin, course, istar_room, branch="Истаравшан")
    student = await make_student("Чужой", branch="Истаравшан")
    enrollment = (
        await admin.post(f"{C}/{cohort['id']}/enrollments", json={"student_id": str(student)})
    ).json()
    lesson = (await admin.get(f"{C}/{cohort['id']}/lessons")).json()[0]
    calls = [
        mgr.get(f"{C}/{cohort['id']}"),
        mgr.patch(f"{C}/{cohort['id']}", json={"capacity": 5}),
        mgr.delete(f"{C}/{cohort['id']}"),
        mgr.post(f"{C}/{cohort['id']}/cancel"),
        mgr.get(f"{C}/{cohort['id']}/lessons"),
        mgr.post(
            f"{C}/{cohort['id']}/lessons",
            json={"date": next_monday().isoformat(), "start_time": "15:00", "end_time": "16:00"},
        ),
        mgr.patch(f"/api/v1/lessons/{lesson['id']}", json={"start_time": "12:00"}),
        mgr.post(f"/api/v1/lessons/{lesson['id']}/cancel"),
        mgr.get(f"{C}/{cohort['id']}/enrollments"),
        mgr.post(f"{C}/{cohort['id']}/enrollments", json={"student_id": str(student)}),
        mgr.patch(f"/api/v1/enrollments/{enrollment['id']}", json={"status": "отчислен"}),
        mgr.delete(f"/api/v1/enrollments/{enrollment['id']}"),
        mgr.get(f"{STUDENTS}/{student}"),
        mgr.patch(f"{STUDENTS}/{student}", json={"full_name": "x"}),
        mgr.delete(f"{STUDENTS}/{student}"),
        mgr.patch(f"/api/v1/rooms/{istar_room}", json={"name": "x"}),
        mgr.delete(f"/api/v1/rooms/{istar_room}"),
    ]
    for call in calls:
        r = await call
        assert (r.status_code, r.json()["code"]) == (404, "not_found"), r.request.url
    # lists show nothing of the other branch
    assert (await mgr.get(C)).json()["total"] == 0
    assert (await mgr.get(STUDENTS)).json()["total"] == 0
    assert (await mgr.get("/api/v1/rooms")).json() == []
    other = str(await branch_id("Истаравшан"))
    assert (await mgr.get(C, params={"branch_id": other})).json()["total"] == 0
    # nothing was changed behind the 404s
    assert (await sql("SELECT count(*) FROM enrollment"))[0][0] == 1
    assert (await sql("SELECT capacity FROM cohort"))[0][0] == 10


async def test_branch_bound_manager_creates_into_own_branch_only(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    mgr = await _manager(login_as)
    course = await make_course()
    room = await make_room("Душанбе", "Lovelace")
    istar_room = await make_room("Истаравшан", "Istaravshan-1")
    cohort = await make_cohort(mgr, course, room)  # branch_id sent = own: fine
    assert cohort["branch_name"] == "Душанбе"
    r = await mgr.post(
        C, json=body(course, istar_room, branch_id=str(await branch_id("Истаравшан")))
    )
    assert (r.status_code, r.json()["code"]) == (403, "branch_forbidden")
    r = await mgr.post(C, json=body(course, istar_room))  # no branch: own; the room is unseen
    assert (r.status_code, r.json()["code"]) == (404, "not_found")
    r = await mgr.post(
        STUDENTS, json={"full_name": "Новый", "branch_id": str(await branch_id("Истаравшан"))}
    )
    assert r.json()["code"] == "branch_forbidden"
    r = await mgr.post(STUDENTS, json={"full_name": "Новый"})
    assert r.status_code == 201 and r.json()["branch_name"] == "Душанбе"
    # an unbound admin must say which branch
    r = await admin.post(STUDENTS, json={"full_name": "Без филиала"})
    assert r.status_code == 422


async def test_instructor_sees_only_own_cohorts(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    course = await make_course()
    ins = await login_as("ins", "instructor", branch="Душанбе")
    await make_user("ins2", "instructor", branch="Душанбе")
    my_id = (await ins.get("/api/v1/auth/me")).json()["id"]
    other_id = str((await sql("SELECT id FROM app_user WHERE login = 'ins2'"))[0][0])
    room_a, room_b = await make_room(name="A"), await make_room(name="B")
    mine = await make_cohort(admin, course, room_a, instructor_id=my_id)
    foreign = await make_cohort(admin, course, room_b, instructor_id=other_id)
    free = await make_cohort(admin, course, await make_room(name="C"))
    student = await make_student("Чужой студент")
    enrollment = (
        await admin.post(f"{C}/{foreign['id']}/enrollments", json={"student_id": str(student)})
    ).json()
    lesson = (await admin.get(f"{C}/{foreign['id']}/lessons")).json()[0]

    listed = (await ins.get(C)).json()
    assert [c["code"] for c in listed["items"]] == [mine["code"]] and listed["total"] == 1
    assert (await ins.get(f"{C}/{mine['id']}")).status_code == 200
    for cohort in (foreign, free):
        for url in (
            f"{C}/{cohort['id']}",
            f"{C}/{cohort['id']}/lessons",
            f"{C}/{cohort['id']}/enrollments",
        ):
            r = await ins.get(url)
            assert (r.status_code, r.json()["code"]) == (404, "not_found"), url
    r = await ins.patch(f"/api/v1/lessons/{lesson['id']}", json={"start_time": "12:00"})
    assert r.status_code == 403
    r = await ins.patch(f"/api/v1/enrollments/{enrollment['id']}", json={"status": "отчислен"})
    assert r.status_code == 403
    # the numbers follow the same scope
    summary = (await ins.get("/api/v1/metrics/education")).json()
    assert summary["cohorts"]["всего"] == 1


async def test_instructor_students_view_is_limited_to_own_cohorts(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    async with instructor_rights(students="view"):
        course = await make_course()
        ins = await login_as("ins", "instructor", branch="Душанбе")
        my_id = (await ins.get("/api/v1/auth/me")).json()["id"]
        mine = await make_cohort(admin, course, await make_room(name="A"), instructor_id=my_id)
        other = await make_cohort(admin, course, await make_room(name="B"))
        mine_student, other_student = await make_student("Мой"), await make_student("Не мой")
        await admin.post(f"{C}/{mine['id']}/enrollments", json={"student_id": str(mine_student)})
        await admin.post(f"{C}/{other['id']}/enrollments", json={"student_id": str(other_student)})
        assert [s["full_name"] for s in (await ins.get(STUDENTS)).json()["items"]] == ["Мой"]
        assert (await ins.get(f"{STUDENTS}/{mine_student}")).status_code == 200
        assert (await ins.get(f"{STUDENTS}/{other_student}")).status_code == 404


async def test_rights_matrix_gates_reads_and_writes(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    viewer = await login_as(
        "viewer",
        await make_role("Смотрящий", {"cohorts": "view", "students": "view", "rooms": "view"}),
    )
    nobody = await login_as("nobody", await make_role("Никто", {"leads": "view"}))
    course, room = await make_course(), await make_room()
    cohort = await make_cohort(admin, course, room)
    assert (await viewer.get(C)).status_code == 200
    assert (await viewer.get(STUDENTS)).status_code == 200
    assert (await viewer.get("/api/v1/rooms")).status_code == 200
    for r in (
        await viewer.post(C, json=body(course, room)),
        await viewer.post(STUDENTS, json={"full_name": "x"}),
        await viewer.post("/api/v1/rooms", json={"name": "x", "capacity": 5}),
        await viewer.post(
            "/api/v1/courses", json={"name": "x", "duration_months": 1, "format": "online"}
        ),
        await viewer.post(f"{C}/{cohort['id']}/cancel"),
        await viewer.delete(f"{C}/{cohort['id']}"),
    ):
        assert (r.status_code, r.json()["code"]) == (403, "forbidden")
    for url in (C, STUDENTS, "/api/v1/rooms", "/api/v1/courses", "/api/v1/metrics/education"):
        assert (await nobody.get(url)).status_code == 403, url
    unauth = httpx.AsyncClient(transport=viewer._transport, base_url="http://test")
    assert (await unauth.get(C)).status_code == 401
    await unauth.aclose()


async def test_instructor_of_a_cohort_must_be_an_active_instructor_of_its_branch(
    admin: httpx.AsyncClient,
) -> None:
    course, room = await make_course(), await make_room()
    good = await make_user("good", "instructor", branch="Душанбе")
    anywhere = await make_user("anywhere", "instructor")  # no branch = all branches
    wrong_branch = await make_user("istar", "instructor", branch="Истаравшан")
    inactive = await make_user("sleepy", "instructor", branch="Душанбе", active=False)
    manager = await make_user("boss", "manager", branch="Душанбе")
    for who in (wrong_branch, inactive, manager, "00000000-0000-0000-0000-000000000000"):
        r = await admin.post(
            C,
            json=body(
                course, room, instructor_id=str(who), branch_id=str(await branch_id("Душанбе"))
            ),
        )
        assert (r.status_code, r.json()["code"]) == (422, "instructor_invalid"), who
    ok = await make_cohort(admin, course, room, instructor_id=str(good))
    assert ok["instructor_name"] == "User good"
    other_room = await make_room(name="B")
    ok2 = await make_cohort(admin, course, other_room, instructor_id=str(anywhere))
    # editing: the same rule, and the instructor can be cleared
    r = await admin.patch(f"{C}/{ok['id']}", json={"instructor_id": str(inactive)})
    assert r.json()["code"] == "instructor_invalid"
    r = await admin.patch(f"{C}/{ok2['id']}", json={"instructor_id": None})
    assert r.status_code == 200 and r.json()["instructor_id"] is None
    # the form's choices: active instructors of the branch (and unbound ones), nobody else
    dush = str(await branch_id("Душанбе"))
    names = [
        i["full_name"]
        for i in (await admin.get(f"{C}/instructors", params={"branch_id": dush})).json()
    ]
    assert names == ["User anywhere", "User good"]


async def test_room_must_belong_to_the_cohorts_branch(admin: httpx.AsyncClient) -> None:
    course = await make_course()
    istar_room = await make_room("Истаравшан", "Istaravshan-1")
    r = await admin.post(
        C, json=body(course, istar_room, branch_id=str(await branch_id("Душанбе")))
    )
    assert (r.status_code, r.json()["code"]) == (422, "room_branch_mismatch")
