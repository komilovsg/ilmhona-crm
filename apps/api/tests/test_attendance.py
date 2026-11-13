"""Stage 1b: attendance, grades, graduation at close, «Сегодня» / «Не заполнено»
(#12, #21, #23 backend, #24)."""

import asyncio
import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy.exc import IntegrityError

from app.cli import daily
from app.cohorts.status import today
from app.metrics import attendance_score
from tests.conftest import SignedIn, branch_id, make_role, sql
from tests.edu import C, body, make_cohort, make_course, make_room, make_student

L = "/api/v1/lessons"
E = "/api/v1/enrollments"


async def past_cohort(
    admin: httpx.AsyncClient, *, name: str = "A", **extra: Any
) -> tuple[dict[str, Any], list[str]]:
    """A cohort whose lessons are the 9 days from today-9 to yesterday (all held, every day)."""
    t = today()
    cohort = await make_cohort(
        admin,
        await make_course(f"Курс {name}"),
        await make_room(name=f"R-{name}"),
        start=t - timedelta(days=9),
        weeks=2,
        weekdays=[1, 2, 3, 4, 5, 6, 7],
        **extra,
    )
    await sql("DELETE FROM lesson WHERE lesson_date >= :t", t=t)
    await sql(
        "UPDATE cohort SET end_date = :e WHERE id = :i", e=t - timedelta(days=1), i=cohort["id"]
    )
    lessons = [le["id"] for le in (await admin.get(f"{C}/{cohort['id']}/lessons")).json()]
    assert len(lessons) == 9
    return cohort, lessons


async def enroll(admin: httpx.AsyncClient, cohort: dict[str, Any], name: str) -> str:
    sid = await make_student(name)
    r = await admin.post(f"{C}/{cohort['id']}/enrollments", json={"student_id": str(sid)})
    assert r.status_code == 201, r.text
    # enrolled before the first lesson of the course
    await sql(
        "UPDATE enrollment SET enrolled_at = :d WHERE id = :i",
        d=today() - timedelta(days=30),
        i=r.json()["id"],
    )
    return str(r.json()["id"])


async def mark(c: httpx.AsyncClient, lesson: str, enrollment: str, present: bool = True, **kw: Any):  # type: ignore[no-untyped-def]
    return await c.put(f"{L}/{lesson}/attendance/{enrollment}", json={"present": present, **kw})


async def row_of(c: httpx.AsyncClient, cohort: dict[str, Any], enrollment: str) -> dict[str, Any]:
    grid = (await c.get(f"{C}/{cohort['id']}/attendance")).json()
    return next(s for s in grid["students"] if s["enrollment_id"] == enrollment)


# ---- #12 ---------------------------------------------------------------------------------


async def test_bug_12_percent_is_of_held_lessons_and_unmarked_are_shown(
    admin: httpx.AsyncClient,
) -> None:
    cohort, lessons = await past_cohort(admin)
    e = await enroll(admin, cohort, "Алиев")
    assert (await mark(admin, lessons[0], e)).status_code == 200
    row = await row_of(admin, cohort, e)
    # the old system said 100 % here (1 of 1 marked); the truth is 1 of 9 held lessons
    assert (row["held"], row["present"], row["unmarked"]) == (9, 1, 8)
    assert row["percent"] == 11.1 and row["score"] == 2
    for lesson in lessons[1:4]:
        await mark(admin, lesson, e, present=False, reason="болел")
    row = await row_of(admin, cohort, e)
    assert (row["present"], row["absent"], row["unmarked"], row["percent"]) == (1, 3, 5, 11.1)


async def test_bug_12_attendance_score_rounds_20_x_present_over_held() -> None:
    assert attendance_score(9, 9) == 20
    assert attendance_score(5, 9) == 11  # 11.1
    assert attendance_score(1, 8) == 3  # 2.5 rounds up
    assert attendance_score(0, 9) == 0
    assert attendance_score(0, 0) == 0  # nothing held yet: no score, no division by zero


async def test_bug_12_student_enrolled_mid_course_counts_lessons_since_enrollment(
    admin: httpx.AsyncClient,
) -> None:
    cohort, lessons = await past_cohort(admin)
    late = await enroll(admin, cohort, "Опоздавший")
    # enrolled 4 days ago: lessons of the last 4 days (t-4 .. t-1) are his, earlier ones are not
    await sql(
        "UPDATE enrollment SET enrolled_at = :d WHERE id = :i",
        d=today() - timedelta(days=4),
        i=late,
    )
    row = await row_of(admin, cohort, late)
    assert (row["held"], row["unmarked"]) == (4, 4)
    for lesson in lessons[5:]:
        assert (await mark(admin, lesson, late)).status_code == 200
    row = await row_of(admin, cohort, late)
    assert (row["held"], row["present"], row["percent"], row["score"]) == (4, 4, 100.0, 20)
    # a lesson before he joined cannot be marked for him
    r = await mark(admin, lessons[0], late)
    assert (r.status_code, r.json()["code"]) == (422, "enrolled_after_lesson")
    # and the lesson screen does not list him there
    page = (await admin.get(f"{L}/{lessons[0]}/attendance")).json()
    assert page["students"] == []


async def test_bug_12_cancelled_lessons_are_not_held(admin: httpx.AsyncClient) -> None:
    cohort, lessons = await past_cohort(admin)
    e = await enroll(admin, cohort, "Алиев")
    assert (await admin.post(f"{L}/{lessons[0]}/cancel")).status_code == 200
    row = await row_of(admin, cohort, e)
    assert row["held"] == 8
    r = await mark(admin, lessons[0], e)
    assert (r.status_code, r.json()["code"]) == (409, "lesson_cancelled")
    r = await admin.post(f"{L}/{lessons[0]}/attendance/all-present")
    assert r.status_code == 409


async def test_bug_12_future_lessons_are_not_held(admin: httpx.AsyncClient) -> None:
    course, room = await make_course(), await make_room()
    cohort = await make_cohort(admin, course, room)  # starts next week
    e = await enroll(admin, cohort, "Алиев")
    row = await row_of(admin, cohort, e)
    assert (row["held"], row["unmarked"], row["percent"], row["score"]) == (0, 0, None, 0)


# ---- cells: the same cell, different cells -----------------------------------------------


async def test_cell_upsert_last_write_wins_and_audit_names_the_change(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    cohort, lessons = await past_cohort(admin)
    e = await enroll(admin, cohort, "Алиев Алишер")
    anna = await login_as("anna", await make_role("Отмечающий", {"attendance": "change"}))
    assert (await mark(admin, lessons[0], e, present=False, reason="болел")).status_code == 200
    assert (await mark(anna, lessons[0], e, present=True, reason="игнорируется")).status_code == 200
    rows = await sql("SELECT present, reason FROM attendance")
    assert [tuple(r) for r in rows] == [(True, None)]  # present clears the reason
    log = (await admin.get("/api/v1/audit", params={"action": "attendance.mark"})).json()
    texts = [i["text"] for i in log["items"]]
    assert texts[0].startswith("User anna: посещаемость Алиев Алишер")
    assert "отсутствует → присутствует" in texts[0]
    assert "не отмечено → отсутствует, причина: болел" in texts[1]


async def test_concurrent_marks_of_different_cells_both_survive(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    cohort, lessons = await past_cohort(admin)
    first, second = await enroll(admin, cohort, "Первый"), await enroll(admin, cohort, "Второй")
    ins = await login_as("ins", "instructor", branch="Душанбе")
    await sql(
        "UPDATE cohort SET instructor_id = (SELECT id FROM app_user WHERE login = 'ins') "
        "WHERE id = :i",
        i=cohort["id"],
    )
    results = await asyncio.gather(
        mark(admin, lessons[0], first, present=False, reason="уехал"),
        mark(ins, lessons[0], second, present=True),
    )
    assert [r.status_code for r in results] == [200, 200]
    rows = {
        str(r[0]): (r[1], r[2])
        for r in await sql("SELECT enrollment_id, present, reason FROM attendance")
    }
    assert rows == {first: (False, "уехал"), second: (True, None)}


async def test_all_present_fills_only_unmarked_cells(admin: httpx.AsyncClient) -> None:
    cohort, lessons = await past_cohort(admin)
    absent, _other = (
        await enroll(admin, cohort, "Отсутствует"),
        await enroll(admin, cohort, "Другой"),
    )
    await mark(admin, lessons[0], absent, present=False, reason="болел")
    page = (await admin.post(f"{L}/{lessons[0]}/attendance/all-present")).json()
    assert (page["marked"], page["total"]) == (2, 2)
    by_name = {s["student_name"]: s for s in page["students"]}
    assert by_name["Отсутствует"]["present"] is False  # not overwritten
    assert by_name["Другой"]["present"] is True
    log = (await admin.get("/api/v1/audit", params={"action": "attendance.mark_all"})).json()
    assert "все присутствуют, отмечено: 1" in log["items"][0]["text"]


async def test_cell_of_another_cohort_is_not_found(admin: httpx.AsyncClient) -> None:
    cohort, lessons = await past_cohort(admin)
    other, _ = await past_cohort(admin, name="B")
    stranger = await enroll(admin, other, "Чужой")
    r = await mark(admin, lessons[0], stranger)
    assert (r.status_code, r.json()["code"]) == (404, "not_found")
    assert (await sql("SELECT count(*) FROM attendance"))[0][0] == 0


# ---- grades ------------------------------------------------------------------------------


async def test_grade_total_is_attendance_plus_homework_plus_final(
    admin: httpx.AsyncClient,
) -> None:
    cohort, lessons = await past_cohort(admin)
    e = await enroll(admin, cohort, "Алиев")
    for lesson in lessons[:5]:
        await mark(admin, lesson, e)  # 5 of 9 held: round(100 / 9) = 11
    row = (await admin.get(f"{C}/{cohort['id']}/grades")).json()[0]
    assert (row["attendance_score"], row["homework"], row["final"], row["total"]) == (
        11,
        None,
        None,
        11,
    )
    assert row["version"] == 1
    r = await admin.patch(f"{E}/{e}/grade", json={"homework": 30, "final": 25})
    assert r.status_code == 200, r.text
    assert (r.json()["total"], r.json()["version"]) == (66, 2)
    r = await admin.patch(f"{E}/{e}/grade", json={"final": None})  # only the sent field changes
    assert (r.json()["homework"], r.json()["final"], r.json()["total"]) == (30, None, 41)


async def test_grade_version_conflict_and_range(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    cohort, _ = await past_cohort(admin)
    e = await enroll(admin, cohort, "Алиев")
    boris = await login_as("boris", await make_role("Оценщик", {"attendance": "change"}))
    loaded = (await admin.get(f"{C}/{cohort['id']}/grades")).json()[0]["version"]
    ok = await admin.patch(
        f"{E}/{e}/grade", json={"homework": 30}, headers={"X-Record-Version": str(loaded)}
    )
    assert ok.status_code == 200
    stale = await boris.patch(
        f"{E}/{e}/grade", json={"final": 20}, headers={"X-Record-Version": str(loaded)}
    )
    assert (stale.status_code, stale.json()["code"]) == (409, "stale_version")
    assert stale.json()["params"]["current"]["homework"] == 30
    assert (await sql("SELECT homework, final FROM grade"))[0] == (30, None)
    for bad in ({"homework": 41}, {"final": -1}):
        assert (await admin.patch(f"{E}/{e}/grade", json=bad)).status_code == 422
    r = await admin.patch(f"{E}/{e}/grade", json={"final": 20}, no_version=True)
    assert r.status_code == 428
    # the database refuses it too
    with pytest.raises(IntegrityError):
        await sql("UPDATE grade SET homework = 99")


# ---- graduation at close -----------------------------------------------------------------


async def test_closing_the_cohort_graduates_at_70_and_completes_the_rest(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    cohort, lessons = await past_cohort(admin)
    top = await enroll(admin, cohort, "Отличник")
    edge = await enroll(admin, cohort, "Почти")
    none = await enroll(admin, cohort, "Без оценок")
    gone = await enroll(admin, cohort, "Отчисленный")
    for lesson in lessons:
        await admin.post(f"{L}/{lesson}/attendance/all-present")  # attendance 20 for everyone
    await admin.patch(f"{E}/{top}", json={"status": "активный"})
    await admin.patch(f"{E}/{gone}", json={"status": "отчислен"})
    await admin.patch(f"{E}/{top}/grade", json={"homework": 30, "final": 20})  # 70
    await admin.patch(f"{E}/{edge}/grade", json={"homework": 30, "final": 19})  # 69
    assert await daily() == 1
    status = {str(i): s for i, s in await sql("SELECT id, status FROM enrollment")}
    assert status == {top: "выпускник", edge: "завершил", none: "завершил", gone: "отчислен"}
    log = (await admin.get("/api/v1/audit", params={"action": "cohort.close_enrollments"})).json()
    assert "зачислений завершено: 3, из них выпускников: 1" in log["items"][0]["text"]
    # a manager with the cohorts right may still correct a status by hand
    mgr = await login_as(
        "mgr", await make_role("Менеджер потоков", {"cohorts": "change"}), branch="Душанбе"
    )
    r = await mgr.patch(f"{E}/{edge}", json={"status": "выпускник"})
    assert r.status_code == 200 and r.json()["status"] == "выпускник"


# ---- the schedule rebuild keeps lessons with marks ---------------------------------------


async def test_rebuild_keeps_lessons_with_marks(admin: httpx.AsyncClient) -> None:
    course, room = await make_course(), await make_room()
    cohort = await make_cohort(admin, course, room, weekdays=[1, 3], weeks=4)
    e = await enroll(admin, cohort, "Алиев")
    lessons = (await admin.get(f"{C}/{cohort['id']}/lessons")).json()
    marked = lessons[1]  # a Wednesday
    # the API marks a lesson from its day on (a lesson of today that has not started yet is
    # still ahead for the rebuild); the mark is put in directly to keep the dates simple
    await sql(
        "INSERT INTO attendance (lesson_id, enrollment_id, present) VALUES (:l, :e, true)",
        l=marked["id"],
        e=e,
    )
    r = await admin.patch(f"{C}/{cohort['id']}", json={"weekdays": [2, 4]})
    assert r.status_code == 200, r.text
    after = (await admin.get(f"{C}/{cohort['id']}/lessons")).json()
    ids = {le["id"] for le in after}
    assert marked["id"] in ids  # kept although Wednesday left the schedule
    assert not {le["id"] for le in lessons[:1] + lessons[2:]} & ids  # unmarked ones were rebuilt
    assert len(after) == 1 + len([le for le in after if le["id"] != marked["id"]])
    # no lesson twice on one slot
    assert len({le["date"] + le["start"] for le in after}) == len(after)
    # the same schedule again: the kept lesson is not duplicated
    r = await admin.patch(f"{C}/{cohort['id']}", json={"weekdays": [2, 3, 4]})
    after = (await admin.get(f"{C}/{cohort['id']}/lessons")).json()
    assert len({le["date"] + le["start"] for le in after}) == len(after)
    assert marked["id"] in {le["id"] for le in after}
    # the database refuses to delete a marked lesson as well
    with pytest.raises(IntegrityError):
        await sql("DELETE FROM lesson WHERE id = :i", i=marked["id"])


# ---- #24 ---------------------------------------------------------------------------------


async def test_bug_24_instructor_marks_own_cohort_but_not_another_and_writes_nothing_else(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    ins = await login_as("ins", "instructor", branch="Душанбе")
    me = (await ins.get("/api/v1/auth/me")).json()["id"]
    mine, my_lessons = await past_cohort(admin, name="A", instructor_id=me)
    theirs, their_lessons = await past_cohort(admin, name="B")
    my_e, their_e = await enroll(admin, mine, "Мой"), await enroll(admin, theirs, "Чужой")

    assert (await mark(ins, my_lessons[0], my_e)).status_code == 200
    assert (await ins.post(f"{L}/{my_lessons[1]}/attendance/all-present")).status_code == 200
    assert (await ins.patch(f"{E}/{my_e}/grade", json={"homework": 35})).status_code == 200
    assert (await ins.get(f"{C}/{mine['id']}/attendance")).status_code == 200

    for r in (
        await mark(ins, their_lessons[0], their_e),
        await ins.post(f"{L}/{their_lessons[0]}/attendance/all-present"),
        await ins.get(f"{L}/{their_lessons[0]}/attendance"),
        await ins.get(f"{C}/{theirs['id']}/attendance"),
        await ins.get(f"{C}/{theirs['id']}/grades"),
        await ins.patch(f"{E}/{their_e}/grade", json={"homework": 40}),
    ):
        assert (r.status_code, r.json()["code"]) == (404, "not_found")
    assert (await sql("SELECT count(*) FROM attendance"))[0][0] == 2  # mine only
    # besides attendance and grades an instructor only adds new students to their own cohort
    # (test_bug_24_instructor_adds_new_students_to_own_cohort_...): an existing one is 403
    r = await ins.post(
        f"{C}/{mine['id']}/enrollments", json={"student_id": str(await make_student())}
    )
    assert (r.status_code, r.json()["code"]) == (403, "forbidden")
    r = await ins.patch(f"{C}/{mine['id']}", json={"capacity": 3})
    assert r.status_code == 403


NEW = {"new_student": {"full_name": "Новиков Нур", "phone": "+992 90 123 45 67"}}


async def test_bug_24_instructor_adds_new_students_to_own_cohort_and_removes_only_own_clean(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    """Owner decision 2026-11-13: an instructor adds new students to their own cohort and
    removes the ones they added that have no payment, mark or grade. Nothing else."""
    ins = await login_as("ins", "instructor", branch="Душанбе")
    other = await login_as("ins2", "instructor", branch="Душанбе")
    me = (await ins.get("/api/v1/auth/me")).json()["id"]
    mine, my_lessons = await past_cohort(admin, name="A", instructor_id=me)
    theirs, _ = await past_cohort(admin, name="B")

    r = await ins.post(f"{C}/{mine['id']}/enrollments", json=NEW)
    assert r.status_code == 201, r.text
    added = r.json()
    assert (added["created_by_me"], added["deletable"]) == (True, True)
    (student,) = await sql(
        "SELECT s.branch_id, s.created_by, e.created_by FROM student s "
        "JOIN enrollment e ON e.student_id = s.id WHERE s.id = :i",
        i=added["student_id"],
    )
    assert student[0] == uuid.UUID(mine["branch_id"])
    assert str(student[1]) == me and str(student[2]) == me
    actions = {a for (a,) in await sql("SELECT action FROM audit_log WHERE user_id = :u", u=me)}
    assert {"student.create", "enrollment.create"} <= actions

    # another cohort: invisible; an existing student: 403; no other write
    r = await ins.post(f"{C}/{theirs['id']}/enrollments", json=NEW)
    assert (r.status_code, r.json()["code"]) == (404, "not_found")
    sid = await make_student("Старый")
    r = await ins.post(f"{C}/{mine['id']}/enrollments", json={"student_id": str(sid)})
    assert (r.status_code, r.json()["code"]) == (403, "forbidden")
    eid = added["id"]
    for r in (
        await ins.patch(
            f"{E}/{eid}", json={"status": "отчислен"}, headers={"X-Record-Version": "1"}
        ),
        await ins.patch(
            f"{E}/{eid}/review", json={"needs_review": True}, headers={"X-Record-Version": "1"}
        ),
        await ins.patch(
            f"/api/v1/students/{added['student_id']}",
            json={"full_name": "X"},
            headers={"X-Record-Version": "1"},
        ),
        await ins.post("/api/v1/students", json={"full_name": "X"}),
        await ins.get("/api/v1/students"),
    ):
        assert r.status_code == 403, r.text

    # another instructor of the same branch does not see it
    assert (await other.delete(f"{E}/{eid}")).status_code == 404
    listed = (await ins.get(f"{C}/{mine['id']}/enrollments")).json()
    assert [x["deletable"] for x in listed] == [True]

    # own, clean: removed, and the student they created goes with it
    assert (await ins.delete(f"{E}/{eid}")).status_code == 204
    assert await sql("SELECT 1 FROM student WHERE id = :i", i=added["student_id"]) == []
    actions = [a for (a,) in await sql("SELECT action FROM audit_log WHERE user_id = :u", u=me)]
    assert {"enrollment.delete", "student.delete"} <= set(actions)

    # a mark, a grade or a payment keeps it
    async def add() -> str:
        r = await ins.post(f"{C}/{mine['id']}/enrollments", json=NEW)
        assert r.status_code == 201, r.text
        await sql(
            "UPDATE enrollment SET enrolled_at = :d WHERE id = :i",
            d=today() - timedelta(days=30),
            i=r.json()["id"],
        )
        return str(r.json()["id"])

    marked = await add()
    assert (await mark(ins, my_lessons[0], marked)).status_code == 200
    graded = await add()
    assert (await ins.patch(f"{E}/{graded}/grade", json={"homework": 5})).status_code == 200
    paid = await add()
    await sql(
        "INSERT INTO payment (enrollment_id, month_no, amount, method, paid_at, "
        "idempotency_key) VALUES (:e, 1, 100, 'alif', :d, gen_random_uuid())",
        e=paid,
        d=today(),
    )
    listed = (await ins.get(f"{C}/{mine['id']}/enrollments")).json()
    assert [x["deletable"] for x in listed] == [False, False, False]
    for e in (marked, graded, paid):
        r = await ins.delete(f"{E}/{e}")
        assert (r.status_code, r.json()["code"]) == (409, "enrollment_has_records")

    # one a manager added: not theirs
    by_admin = await enroll(admin, mine, "От менеджера")
    r = await ins.delete(f"{E}/{by_admin}")
    assert (r.status_code, r.json()["code"]) == (403, "enrollment_not_yours")
    assert (await sql("SELECT count(*) FROM enrollment WHERE cohort_id = :c", c=mine["id"]))[0][
        0
    ] == 4


async def test_bug_24_instructor_removal_keeps_a_student_held_elsewhere(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    ins = await login_as("ins", "instructor", branch="Душанбе")
    me = (await ins.get("/api/v1/auth/me")).json()["id"]
    mine, _ = await past_cohort(admin, name="A", instructor_id=me)
    theirs, _ = await past_cohort(admin, name="B")
    added = (await ins.post(f"{C}/{mine['id']}/enrollments", json=NEW)).json()
    r = await admin.post(
        f"{C}/{theirs['id']}/enrollments", json={"student_id": added["student_id"]}
    )
    assert r.status_code == 201
    assert (await ins.delete(f"{E}/{added['id']}")).status_code == 204
    # enrolled elsewhere too: the student stays
    assert len(await sql("SELECT 1 FROM student WHERE id = :i", i=added["student_id"])) == 1


async def test_manager_enroll_fills_created_by(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    me = (await admin.get("/api/v1/auth/me")).json()["id"]
    cohort, _ = await past_cohort(admin)
    r = await admin.post(f"{C}/{cohort['id']}/enrollments", json=NEW)
    assert r.status_code == 201
    (row,) = await sql(
        "SELECT s.created_by, e.created_by FROM enrollment e JOIN student s "
        "ON s.id = e.student_id WHERE e.id = :i",
        i=r.json()["id"],
    )
    assert (str(row[0]), str(row[1])) == (me, me)
    # a manager still removes any enrollment; the student stays
    assert (await admin.delete(f"{E}/{r.json()['id']}")).status_code == 204
    assert len(await sql("SELECT 1 FROM student WHERE id = :i", i=r.json()["student_id"])) == 1


async def test_attendance_rights_view_does_not_write_and_branch_scope(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    cohort, lessons = await past_cohort(admin)
    e = await enroll(admin, cohort, "Алиев")
    viewer = await login_as(
        "viewer", await make_role("Смотрящий", {"attendance": "view"}), branch="Душанбе"
    )
    assert (await viewer.get(f"{L}/{lessons[0]}/attendance")).status_code == 200
    r = await mark(viewer, lessons[0], e)
    assert (r.status_code, r.json()["code"]) == (403, "forbidden")
    assert (await viewer.patch(f"{E}/{e}/grade", json={"homework": 1})).status_code == 403
    nothing = await login_as("none", await make_role("Без прав", {"cohorts": "view"}))
    assert (await nothing.get(f"{C}/{cohort['id']}/attendance")).status_code == 403
    istar = await login_as(
        "istar", await make_role("Истаравшан", {"attendance": "change"}), branch="Истаравшан"
    )
    assert (await mark(istar, lessons[0], e)).status_code == 404  # another branch
    assert (await istar.get("/api/v1/me/today")).json()["unfilled"] == []


# ---- #21 ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("now", "started"),
    [("00:30", False), ("07:59", False), ("08:00", True), ("08:06", True), ("23:30", True)],
)
async def test_bug_21_today_and_unfilled_for_the_instructor(
    admin: httpx.AsyncClient,
    login_as: SignedIn,
    clock: Callable[[str], None],
    now: str,
    started: bool,
) -> None:
    """«Held» means started: today's 08:00 lesson is «not filled» once it has begun and one
    student is unmarked, never before. The clock is frozen, so the answer cannot depend on
    the hour the suite runs at."""
    clock(now)
    ins = await login_as("ins", "instructor", branch="Душанбе")
    me = (await ins.get("/api/v1/auth/me")).json()["id"]
    cohort, lessons = await past_cohort(admin, instructor_id=me)
    other, _ = await past_cohort(admin, name="B")  # somebody else's cohort
    await enroll(admin, other, "Чужой")
    a, b = await enroll(admin, cohort, "Алиев"), await enroll(admin, cohort, "Бобоев")
    # today's lesson (the helper removed it): add by hand
    t = today()
    r = await admin.post(
        f"{C}/{cohort['id']}/lessons",
        json={"date": t.isoformat(), "start_time": "08:00", "end_time": "09:00"},
    )
    assert r.status_code == 201, r.text
    today_id = r.json()["id"]
    await mark(admin, today_id, a)

    data = (await ins.get("/api/v1/me/today")).json()
    assert data["date"] == t.isoformat()
    assert [(x["lesson_id"], x["marked"], x["total"]) for x in data["today"]] == [(today_id, 1, 2)]
    # nine past lessons, none marked: all in «не заполнено» (the cohort is still ahead of its end);
    # today's lesson joins them only after it has started
    expected = set(lessons) | ({today_id} if started else set())
    assert {x["lesson_id"] for x in data["unfilled"]} == expected
    assert {x["cohort_code"] for x in data["unfilled"]} == {cohort["code"]}  # only the own cohort
    for lesson in lessons:
        await admin.post(f"{L}/{lesson}/attendance/all-present")
    data = (await ins.get("/api/v1/me/today")).json()
    assert [x["lesson_id"] for x in data["unfilled"]] == ([today_id] if started else [])

    # one student of one lesson left unmarked brings the lesson back
    await sql(
        "DELETE FROM attendance WHERE lesson_id = :l AND enrollment_id = :e", l=lessons[3], e=b
    )
    data = (await ins.get("/api/v1/me/today")).json()
    assert [(x["lesson_id"], x["marked"], x["total"]) for x in data["unfilled"]] == [
        (lessons[3], 1, 2),
        *([(today_id, 1, 2)] if started else []),
    ]


async def test_bug_21_finished_cohort_without_any_mark_is_listed(
    admin: httpx.AsyncClient,
) -> None:
    """The old system: a finished cohort with 0 of 14 marked and nobody noticed."""
    cohort, lessons = await past_cohort(admin)
    await enroll(admin, cohort, "Алиев")
    assert await daily() == 1  # the cohort finished
    assert (await sql("SELECT status FROM cohort"))[0][0] == "завершён"
    data = (await admin.get("/api/v1/me/today")).json()
    assert {x["lesson_id"] for x in data["unfilled"]} == set(lessons)
    assert all((x["marked"], x["total"]) == (0, 1) for x in data["unfilled"])


async def test_bug_21_unfilled_covers_30_days_and_skips_cancelled_and_empty_lessons(
    admin: httpx.AsyncClient,
) -> None:
    cohort, lessons = await past_cohort(admin)
    await enroll(admin, cohort, "Алиев")
    # lesson 0 is 9 days ago; push it 40 days back (older than 30 days) and cancel lesson 1
    await sql(
        "UPDATE lesson SET starts_at = starts_at - interval '40 days', "
        "ends_at = ends_at - interval '40 days', lesson_date = lesson_date - 40 WHERE id = :i",
        i=lessons[0],
    )
    await admin.post(f"{L}/{lessons[1]}/cancel")
    data = (await admin.get("/api/v1/me/today")).json()
    assert {x["lesson_id"] for x in data["unfilled"]} == set(lessons[2:])


async def test_bug_21_manager_sees_unfilled_grouped_by_instructor(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    anvar = await login_as("anvar", "instructor", branch="Душанбе")
    bahor = await login_as("bahor", "instructor", branch="Душанбе")
    ids = {
        n: (await c.get("/api/v1/auth/me")).json() for n, c in (("anvar", anvar), ("bahor", bahor))
    }
    c1, _ = await past_cohort(admin, name="A", instructor_id=ids["anvar"]["id"])
    c2, _ = await past_cohort(admin, name="B", instructor_id=ids["bahor"]["id"])
    for c in (c1, c2):
        await enroll(admin, c, "Студент")
    mgr = await login_as(
        "mgr",
        await make_role("Менеджер потоков", {"attendance": "view", "cohorts": "view"}),
        branch="Душанбе",
    )
    groups = (await mgr.get("/api/v1/me/today")).json()["unfilled_by_instructor"]
    assert {g["instructor_name"]: len(g["lessons"]) for g in groups} == {
        ids["anvar"]["full_name"]: 9,
        ids["bahor"]["full_name"]: 9,
    }
    # the instructor sees only their own group
    own = (await anvar.get("/api/v1/me/today")).json()["unfilled_by_instructor"]
    assert [g["instructor_name"] for g in own] == [ids["anvar"]["full_name"]]
    # a manager of another branch sees nothing
    far = await login_as(
        "far", await make_role("Другой филиал", {"attendance": "view"}), branch="Истаравшан"
    )
    assert (await far.get("/api/v1/me/today")).json()["unfilled_by_instructor"] == []


# ---- grid --------------------------------------------------------------------------------


async def test_grid_has_students_by_lessons_and_leaves_out_expelled(
    admin: httpx.AsyncClient,
) -> None:
    cohort, lessons = await past_cohort(admin)
    a, b = await enroll(admin, cohort, "Алиев"), await enroll(admin, cohort, "Бобоев")
    await enroll(admin, cohort, "Вафоев")
    await admin.patch(f"{E}/{(await enroll(admin, cohort, 'Гулов'))}", json={"status": "отчислен"})
    await mark(admin, lessons[2], a, present=False, reason="работа")
    await mark(admin, lessons[2], b)
    grid = (await admin.get(f"{C}/{cohort['id']}/attendance")).json()
    assert [le["id"] for le in grid["lessons"]] == lessons
    assert [s["student_name"] for s in grid["students"]] == ["Алиев", "Бобоев", "Вафоев"]
    first = grid["students"][0]
    assert first["marks"] == {lessons[2]: {"present": False, "reason": "работа"}}
    assert (first["held"], first["unmarked"]) == (9, 8)
    assert "enrolled_on" in first
    assert all(le["writable"] == (le["date"] <= str(today())) for le in grid["lessons"])
    _ = branch_id, body, uuid
