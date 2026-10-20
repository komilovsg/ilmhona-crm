"""Security regressions for stage 1a: cross-branch references and history leaks."""

import httpx

from tests.conftest import SignedIn, make_role, sql
from tests.edu import C, body, instructor_rights, make_cohort, make_course, make_room, make_student

STUDENTS = "/api/v1/students"
MGR = {"cohorts": "change", "students": "change", "rooms": "change"}


async def test_student_history_shows_only_cohorts_in_scope(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    async with instructor_rights(students="view"):
        course = await make_course()
        ins = await login_as("ins", "instructor", branch="Душанбе")
        my_id = (await ins.get("/api/v1/auth/me")).json()["id"]
        mine = await make_cohort(admin, course, await make_room(name="A"), instructor_id=my_id)
        other = await make_cohort(admin, course, await make_room(name="B"))
        student = await make_student("Общий")
        for cohort in (mine, other):
            r = await admin.post(
                f"{C}/{cohort['id']}/enrollments", json={"student_id": str(student)}
            )
            assert r.status_code == 201
        detail = (await ins.get(f"{STUDENTS}/{student}")).json()
        assert [e["cohort_code"] for e in detail["enrollments"]] == [mine["code"]]
        assert detail["enrollments_count"] == 1
        listed = (await ins.get(STUDENTS)).json()["items"]
        assert [s["enrollments_count"] for s in listed] == [1]


async def test_student_history_hides_other_branch_cohorts(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    mgr = await login_as("mgr", await make_role("Менеджер филиала", MGR), branch="Душанбе")
    course = await make_course()
    istar = await make_cohort(
        admin, course, await make_room("Истаравшан", "I-1"), branch="Истаравшан"
    )
    student = await make_student("Свой")
    # a cross-branch enrollment that predates the API check (import, old data)
    await sql(
        "INSERT INTO enrollment (cohort_id, student_id) VALUES (:c, :s)",
        c=istar["id"],
        s=student,
    )
    detail = (await mgr.get(f"{STUDENTS}/{student}")).json()
    assert detail["enrollments"] == [] and detail["enrollments_count"] == 0
    assert (await mgr.get(STUDENTS)).json()["items"][0]["enrollments_count"] == 0


async def test_student_of_another_branch_cannot_be_enrolled(admin: httpx.AsyncClient) -> None:
    course = await make_course()
    cohort = await make_cohort(admin, course, await make_room())
    stranger = await make_student("Чужой", branch="Истаравшан")
    r = await admin.post(f"{C}/{cohort['id']}/enrollments", json={"student_id": str(stranger)})
    assert (r.status_code, r.json()["code"]) == (422, "student_branch_mismatch")
    assert (await sql("SELECT count(*) FROM enrollment"))[0][0] == 0


async def test_other_branch_room_looks_missing_to_a_branch_user(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    mgr = await login_as("mgr", await make_role("Менеджер филиала", MGR), branch="Душанбе")
    course, room = await make_course(), await make_room()
    istar_room = await make_room("Истаравшан", "I-1")
    cohort = await make_cohort(admin, course, room)
    lesson = (await admin.get(f"{C}/{cohort['id']}/lessons")).json()[0]
    calls = [
        mgr.post(C, json=body(course, istar_room)),
        mgr.patch(f"{C}/{cohort['id']}", json={"room_id": str(istar_room)}),
        mgr.post(
            f"{C}/{cohort['id']}/lessons",
            json={
                "date": lesson["date"],
                "start_time": "18:00",
                "end_time": "19:00",
                "room_id": str(istar_room),
            },
        ),
        mgr.patch(f"/api/v1/lessons/{lesson['id']}", json={"room_id": str(istar_room)}),
    ]
    for call in calls:
        r = await call
        assert (r.status_code, r.json()["code"]) == (404, "not_found"), r.request.url
