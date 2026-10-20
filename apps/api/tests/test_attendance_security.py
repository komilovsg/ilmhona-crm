"""Stage 1b security review: the instructor's first write path (attendance, grades)."""

from datetime import timedelta

import httpx

from app.cohorts.status import today
from tests.conftest import SignedIn, sql
from tests.edu import C, make_cohort, make_course, make_room
from tests.test_attendance import enroll, mark, past_cohort

L = "/api/v1/lessons"
E = "/api/v1/enrollments"


async def test_expelled_enrollment_cannot_be_marked(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    ins = await login_as("ins", "instructor", branch="Душанбе")
    me = (await ins.get("/api/v1/auth/me")).json()["id"]
    cohort, lessons = await past_cohort(admin, instructor_id=me)
    gone = await enroll(admin, cohort, "Отчисленный")
    assert (await admin.patch(f"{E}/{gone}", json={"status": "отчислен"})).status_code == 200
    for c in (ins, admin):
        r = await mark(c, lessons[0], gone)
        assert (r.status_code, r.json()["code"]) == (404, "not_found")
    assert (await sql("SELECT count(*) FROM attendance"))[0][0] == 0


async def test_future_lesson_cannot_be_marked(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    """A mark on a lesson still ahead would pin it (a marked lesson survives every schedule
    rebuild and keeps its room): only lessons of today or earlier take marks."""
    ins = await login_as("ins", "instructor", branch="Душанбе")
    me = (await ins.get("/api/v1/auth/me")).json()["id"]
    cohort = await make_cohort(admin, await make_course(), await make_room(), instructor_id=me)
    e = await enroll(admin, cohort, "Алиев")
    ahead = (await admin.get(f"{C}/{cohort['id']}/lessons")).json()[0]
    assert ahead["date"] > today().isoformat()
    for c in (ins, admin):
        r = await mark(c, ahead["id"], e, present=False, reason="x")
        assert (r.status_code, r.json()["code"]) == (409, "lesson_not_held")
        r = await c.post(f"{L}/{ahead['id']}/attendance/all-present")
        assert (r.status_code, r.json()["code"]) == (409, "lesson_not_held")
    assert (await sql("SELECT count(*) FROM attendance"))[0][0] == 0
    # the same lesson takes marks on its own day, even before it starts (marked at the door)
    await sql(
        "UPDATE lesson SET lesson_date = :t, "
        "starts_at = (CAST(:t AS date) + time '21:00') AT TIME ZONE 'Asia/Dushanbe', "
        "ends_at = (CAST(:t AS date) + time '21:30') AT TIME ZONE 'Asia/Dushanbe' WHERE id = :i",
        t=today(),
        i=ahead["id"],
    )
    await sql(
        "UPDATE enrollment SET enrolled_at = :d WHERE id = :i", d=today() - timedelta(days=1), i=e
    )
    assert (await mark(ins, ahead["id"], e)).status_code == 200


async def test_instructor_cross_references_and_no_status_override(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    ins = await login_as("ins", "instructor", branch="Душанбе")
    me = (await ins.get("/api/v1/auth/me")).json()["id"]
    mine, my_lessons = await past_cohort(admin, name="A", instructor_id=me)
    mine2, _ = await past_cohort(admin, name="C", instructor_id=me)
    theirs, their_lessons = await past_cohort(admin, name="B")
    my_e, my2_e = await enroll(admin, mine, "Мой"), await enroll(admin, mine2, "Мой2")
    their_e = await enroll(admin, theirs, "Чужой")
    for lesson, e in (
        (my_lessons[0], their_e),  # own lesson, foreign enrollment
        (their_lessons[0], my_e),  # foreign lesson, own enrollment
        (my_lessons[0], my2_e),  # own lesson, enrollment of another own cohort
    ):
        r = await mark(ins, lesson, e)
        assert (r.status_code, r.json()["code"]) == (404, "not_found")
    assert (await sql("SELECT count(*) FROM attendance"))[0][0] == 0
    # «все присутствуют» on the own lesson touches only that cohort's students
    assert (await ins.post(f"{L}/{my_lessons[0]}/attendance/all-present")).status_code == 200
    assert {str(r[0]) for r in await sql("SELECT enrollment_id FROM attendance")} == {my_e}
    # no enrollment status / graduation override, no extra fields smuggled in
    r = await ins.patch(f"{E}/{my_e}", json={"status": "выпускник"})
    assert r.status_code == 403
    r = await ins.put(
        f"{L}/{my_lessons[1]}/attendance/{my_e}", json={"present": True, "marked_by": me}
    )
    assert r.status_code == 422
    r = await ins.patch(f"{E}/{my_e}/grade", json={"homework": 1, "status": "выпускник"})
    assert r.status_code == 422
    assert (await sql("SELECT status FROM enrollment WHERE id = :i", i=my_e))[0][0] == "активный"


async def test_empty_grade_patch_does_not_bump_the_version(admin: httpx.AsyncClient) -> None:
    """An empty PATCH changed nothing but bumped the version (and wrote no audit entry), so any
    grader could make every other editor's save fail with stale_version."""
    cohort, _ = await past_cohort(admin)
    e = await enroll(admin, cohort, "Алиев")
    assert (await admin.patch(f"{E}/{e}/grade", json={"homework": 10})).status_code == 200
    r = await admin.patch(f"{E}/{e}/grade", json={}, headers={"If-Match": "2"})
    assert r.status_code == 200 and r.json()["version"] == 2
    r = await admin.patch(f"{E}/{e}/grade", json={"homework": 10}, headers={"If-Match": "2"})
    assert r.status_code == 200 and r.json()["version"] == 2
