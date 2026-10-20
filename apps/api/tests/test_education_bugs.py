"""One test per bug of docs/ANALYSIS.md that stage 1a prevents (#4 #6 #7 #8 #11 #20 #24)."""

from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy.exc import IntegrityError

from app.cli import daily
from app.cohorts.status import today
from tests.conftest import SignedIn, branch_id, sql
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


async def raw_cohort(course: Any, room: Any, **cols: Any) -> Any:
    values: dict[str, Any] = {
        "course_id": course,
        "branch_id": await branch_id("Душанбе"),
        "room_id": room,
        "start_date": "2030-03-04",
        "end_date": "2030-04-04",
        "weekdays": [1, 3],
        "start_time": "10:00",
        "end_time": "11:30",
        "capacity": 10,
        "price_month": 100,
        **cols,
    }
    from datetime import date, time

    for key in ("start_date", "end_date"):
        if isinstance(values[key], str):
            values[key] = date.fromisoformat(values[key])
    for key in ("start_time", "end_time"):
        if isinstance(values[key], str):
            values[key] = time.fromisoformat(values[key])
    names = ", ".join(values)
    params = ", ".join(f":{k}" for k in values)
    rows = await sql(f"INSERT INTO cohort ({names}) VALUES ({params}) RETURNING id", **values)
    return rows[0][0]


# ---- #4 ----------------------------------------------------------------------------------


async def test_bug_04_student_cannot_be_in_a_cohort_twice(admin: httpx.AsyncClient) -> None:
    course, room = await make_course(), await make_room()
    cohort = await make_cohort(admin, course, room)
    student = await make_student("Алиев Али")
    url = f"{C}/{cohort['id']}/enrollments"
    assert (await admin.post(url, json={"student_id": str(student)})).status_code == 201
    r = await admin.post(url, json={"student_id": str(student)})
    assert (r.status_code, r.json()["code"]) == (409, "already_enrolled")
    assert (await sql("SELECT count(*) FROM enrollment"))[0][0] == 1
    # the database itself refuses it, not only the API
    with pytest.raises(IntegrityError, match="enrollment_cohort_student_key"):
        await sql(
            "INSERT INTO enrollment (cohort_id, student_id) VALUES (:c, :s)",
            c=cohort["id"],
            s=student,
        )


# ---- #6 ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("04:35", "05:35"),  # before 07:00
        ("22:35", "23:50"),  # after 22:00
        ("21:00", "22:30"),
        ("04:35", "17:00"),  # too early and 12 hours
        ("10:00", "10:20"),  # shorter than 30 min
        ("10:00", "14:30"),  # longer than 240 min
        ("11:00", "10:00"),  # backwards
    ],
)
async def test_bug_06_lesson_time_is_range_checked(
    admin: httpx.AsyncClient, start: str, end: str
) -> None:
    course, room = await make_course(), await make_room()
    r = await admin.post(
        C,
        json=body(
            course, room, start_time=start, end_time=end, branch_id=str(await branch_id("Душанбе"))
        ),
    )
    assert (r.status_code, r.json()["code"]) == (422, "validation_failed")


async def test_bug_06_boundaries_are_allowed_and_db_rejects_bad_times(
    admin: httpx.AsyncClient,
) -> None:
    course, room = await make_course(), await make_room()
    await make_cohort(admin, course, room, start_time="07:00", end_time="11:00")
    await make_cohort(admin, course, room, start_time="18:30", end_time="22:00")
    for start, end in (("04:35", "06:00"), ("20:00", "22:30"), ("10:00", "10:10")):
        with pytest.raises(IntegrityError, match="cohort_(time_range|duration)_check"):
            await raw_cohort(course, room, start_time=start, end_time=end)


async def test_bug_06_manual_lesson_is_range_checked_and_stored_in_dushanbe_time(
    admin: httpx.AsyncClient,
) -> None:
    course, room = await make_course(), await make_room()
    cohort = await make_cohort(admin, course, room)
    day = (next_monday() + timedelta(days=1)).isoformat()
    url = f"{C}/{cohort['id']}/lessons"
    r = await admin.post(url, json={"date": day, "start_time": "04:35", "end_time": "17:00"})
    assert r.status_code == 422
    r = await admin.post(url, json={"date": day, "start_time": "14:00", "end_time": "15:30"})
    assert r.status_code == 201 and (r.json()["start"], r.json()["end"]) == ("14:00", "15:30")
    (starts,) = (
        await sql(
            "SELECT starts_at FROM lesson WHERE lesson_date = :d",
            d=next_monday() + timedelta(days=1),
        )
    )[0]
    assert (
        starts.utcoffset() is not None and starts.utcoffset().total_seconds() == 0
    )  # stored aware (UTC)
    assert starts.hour == 9  # 14:00 in Asia/Dushanbe (UTC+5)


# ---- #7 ----------------------------------------------------------------------------------


async def test_bug_07_two_cohorts_cannot_hold_one_room_at_the_same_time(
    admin: httpx.AsyncClient,
) -> None:
    course, room = await make_course(), await make_room()
    first = await make_cohort(admin, course, room)
    r = await admin.post(
        C,
        json=body(
            course,
            room,
            start_time="11:00",
            end_time="12:30",
            branch_id=str(await branch_id("Душанбе")),
        ),
    )
    assert (r.status_code, r.json()["code"]) == (409, "room_busy")
    assert r.json()["params"]["cohort"] == first["code"]  # names who holds the room
    # the failed create left nothing behind
    assert (await sql("SELECT count(*) FROM cohort"))[0][0] == 1
    # touching lessons (10:00-11:30 then 11:30-13:00) and other days are fine
    await make_cohort(admin, course, room, start_time="11:30", end_time="13:00")
    await make_cohort(admin, course, room, weekdays=[2, 4])
    other_room = await make_room(name="Jobs")
    await make_cohort(admin, course, other_room)


async def test_bug_07_database_exclusion_and_cancelled_lessons(admin: httpx.AsyncClient) -> None:
    course, room = await make_course(), await make_room()
    cohort = await make_cohort(admin, course, room)
    lessons = (await admin.get(f"{C}/{cohort['id']}/lessons")).json()
    first = lessons[0]
    with pytest.raises(IntegrityError, match="lesson_room_no_overlap"):
        await sql(
            "INSERT INTO lesson (cohort_id, room_id, lesson_date, starts_at, ends_at) "
            "SELECT cohort_id, room_id, lesson_date, starts_at + interval '30 minutes', "
            "ends_at + interval '30 minutes' FROM lesson WHERE id = :i",
            i=first["id"],
        )
    # a cancelled lesson frees the room
    assert (await admin.post(f"/api/v1/lessons/{first['id']}/cancel")).status_code == 200
    other = await make_cohort(admin, course, room, weekdays=[2])
    r = await admin.post(
        f"{C}/{other['id']}/lessons",
        json={"date": first["date"], "start_time": "10:00", "end_time": "11:30"},
    )
    assert r.status_code == 201


async def test_bug_07_manual_add_and_move_check_the_room(admin: httpx.AsyncClient) -> None:
    course, room = await make_course(), await make_room()
    a = await make_cohort(admin, course, room, weekdays=[1])
    b = await make_cohort(admin, course, room, weekdays=[2])
    monday = next_monday()
    # add a lesson to B on Monday 10:30: collides with A
    r = await admin.post(
        f"{C}/{b['id']}/lessons",
        json={"date": monday.isoformat(), "start_time": "10:30", "end_time": "12:00"},
    )
    assert (r.status_code, r.json()["code"]) == (409, "room_busy")
    assert r.json()["params"]["cohort"] == a["code"]
    # moving B's Tuesday lesson onto Monday 10:00 collides too; moving to 12:00 does not
    lesson = (await admin.get(f"{C}/{b['id']}/lessons")).json()[0]
    r = await admin.patch(
        f"/api/v1/lessons/{lesson['id']}", json={"date": monday.isoformat(), "start_time": "10:00"}
    )
    assert (r.status_code, r.json()["code"]) == (409, "room_busy")
    r = await admin.patch(
        f"/api/v1/lessons/{lesson['id']}",
        json={"date": monday.isoformat(), "start_time": "12:00", "end_time": "13:00"},
    )
    assert r.status_code == 200 and r.json()["start"] == "12:00"
    # a lesson can be moved within its own slot (it does not collide with itself)
    r = await admin.patch(f"/api/v1/lessons/{lesson['id']}", json={"end_time": "13:30"})
    assert r.status_code == 200


# ---- #8 ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2001-07-01", "2001-08-01"),  # «Июль 2001»
        ("2019-12-01", "2020-02-01"),
        ("2035-12-01", "2036-02-01"),
        ("2030-05-01", "2030-05-01"),  # end not after start
        ("2030-05-10", "2030-05-01"),
    ],
)
async def test_bug_08_cohort_dates_are_range_checked(
    admin: httpx.AsyncClient, start: str, end: str
) -> None:
    course, room = await make_course(), await make_room()
    payload = body(course, room, branch_id=str(await branch_id("Душанбе")))
    payload.update(start_date=start, end_date=end)
    r = await admin.post(C, json=payload)
    assert (r.status_code, r.json()["code"]) == (422, "validation_failed")
    from datetime import date

    with pytest.raises(IntegrityError, match="cohort_dates"):
        await raw_cohort(
            course, room, start_date=date.fromisoformat(start), end_date=date.fromisoformat(end)
        )


async def test_bug_08_edge_dates_pass_and_update_is_checked(admin: httpx.AsyncClient) -> None:
    course, room = await make_course(), await make_room()
    payload = body(course, room, branch_id=str(await branch_id("Душанбе")))
    payload.update(start_date="2020-01-01", end_date="2020-01-31")
    assert (await admin.post(C, json=payload)).status_code == 201
    cohort = await make_cohort(admin, course, room)
    for patch in (
        {"start_date": "2001-07-01"},
        {"end_date": "2040-01-01"},
        {"end_date": cohort["start_date"]},
    ):
        r = await admin.patch(f"{C}/{cohort['id']}", json=patch)
        assert r.status_code == 422, patch


# ---- #11 ---------------------------------------------------------------------------------


async def test_bug_11_finishing_a_cohort_completes_its_active_enrollments(
    admin: httpx.AsyncClient,
) -> None:
    course, room = await make_course(), await make_room()
    cohort = await make_cohort(admin, course, room)
    assert cohort["status"] == "набор"
    ids = []
    for name in ("A", "B", "C"):
        r = await admin.post(
            f"{C}/{cohort['id']}/enrollments", json={"student_id": str(await make_student(name))}
        )
        ids.append(r.json()["id"])
    await admin.patch(f"/api/v1/enrollments/{ids[2]}", json={"status": "отчислен"})
    # the dates move into the past: the cohort is finished, active students are not
    r = await admin.patch(
        f"{C}/{cohort['id']}", json={"start_date": "2024-01-08", "end_date": "2024-03-08"}
    )
    assert r.status_code == 200 and r.json()["status"] == "завершён"
    statuses = {
        e["student_name"]: e["status"]
        for e in (await admin.get(f"{C}/{cohort['id']}/enrollments")).json()
    }
    assert statuses == {"A": "завершил", "B": "завершил", "C": "отчислен"}
    # and nobody can be made active again, or enrolled, in a finished cohort
    r = await admin.patch(f"/api/v1/enrollments/{ids[0]}", json={"status": "активный"})
    assert (r.status_code, r.json()["code"]) == (409, "cohort_closed")
    r = await admin.post(
        f"{C}/{cohort['id']}/enrollments", json={"student_id": str(await make_student("D"))}
    )
    assert (r.status_code, r.json()["code"]) == (409, "cohort_closed")
    audit = (await admin.get("/api/v1/audit", params={"action": "cohort.close_enrollments"})).json()
    assert audit["total"] == 1


# ---- #20 ---------------------------------------------------------------------------------


async def test_bug_20_daily_job_derives_status_from_dates(admin: httpx.AsyncClient) -> None:
    course, room = await make_course(), await make_room()
    t = today()
    stale = await raw_cohort(
        course,
        room,
        start_date=t - timedelta(days=60),
        end_date=t - timedelta(days=8),
        status="активный",
        start_time="08:00",
        end_time="09:00",
    )  # ended 8 days ago, still «активный» (the old system's G-… cohort)
    started = await raw_cohort(
        course,
        room,
        start_date=t - timedelta(days=1),
        end_date=t + timedelta(days=30),
        status="набор",
        start_time="09:30",
        end_time="10:30",
    )
    upcoming = await raw_cohort(
        course,
        room,
        start_date=t + timedelta(days=5),
        end_date=t + timedelta(days=40),
        status="набор",
        start_time="11:00",
        end_time="12:00",
    )
    cancelled = await raw_cohort(
        course,
        room,
        start_date=t - timedelta(days=60),
        end_date=t - timedelta(days=8),
        status="отменён",
        start_time="12:30",
        end_time="13:30",
    )
    student = await make_student()
    await sql("INSERT INTO enrollment (cohort_id, student_id) VALUES (:c, :s)", c=stale, s=student)

    assert await daily() == 2
    status = {i: s for i, s in await sql("SELECT id, status FROM cohort")}
    assert status[stale] == "завершён"
    assert status[started] == "активный"
    assert status[upcoming] == "набор"
    assert status[cancelled] == "отменён"  # manual and sticky
    assert (await sql("SELECT status FROM enrollment"))[0][0] == "завершил"  # #11 as well
    assert await daily() == 0  # idempotent
    # a cohort whose last day is today is still active; the day after it is finished
    assert await daily(t + timedelta(days=30)) == 1  # `upcoming` started; `started` ends today
    assert await daily(t + timedelta(days=31)) == 1  # `started` ended yesterday
    assert {i: s for i, s in await sql("SELECT id, status FROM cohort")}[started] == "завершён"
    log = (await admin.get("/api/v1/audit", params={"action": "cohort.status"})).json()
    assert log["total"] >= 2 and log["items"][0]["user_id"] is None


async def test_bug_20_status_is_also_set_on_every_write(admin: httpx.AsyncClient) -> None:
    course, room = await make_course(), await make_room()
    t = today()
    r = await admin.post(
        C,
        json=body(
            course,
            room,
            start=t - timedelta(days=3),
            weeks=4,
            branch_id=str(await branch_id("Душанбе")),
        ),
    )
    assert r.json()["status"] == "активный"
    cid = r.json()["id"]
    r = await admin.patch(
        f"{C}/{cid}",
        json={
            "start_date": (t + timedelta(days=9)).isoformat(),
            "end_date": (t + timedelta(days=40)).isoformat(),
        },
    )
    assert r.json()["status"] == "набор"
    # «отменён» is manual, sticky, and survives edits and the daily job
    assert (await admin.post(f"{C}/{cid}/cancel")).json()["status"] == "отменён"
    assert (await admin.patch(f"{C}/{cid}", json={"capacity": 5})).status_code == 409
    await sql(
        "UPDATE cohort SET end_date = :d, start_date = :s",
        d=t - timedelta(days=1),
        s=t - timedelta(days=9),
    )
    assert await daily() == 0
    assert (await admin.post(f"{C}/{cid}/restore")).json()["status"] == "завершён"


# ---- #24 ---------------------------------------------------------------------------------


async def test_bug_24_instructor_cannot_enroll_or_edit_students(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    course, room = await make_course(), await make_room()
    ins = await login_as("ins", "instructor", branch="Душанбе")
    me = (await ins.get("/api/v1/auth/me")).json()
    cohort = await make_cohort(admin, course, room, instructor_id=me["id"])
    student = await make_student()
    enrollment = (
        await admin.post(f"{C}/{cohort['id']}/enrollments", json={"student_id": str(student)})
    ).json()

    async def forbidden(r: httpx.Response) -> None:
        assert (r.status_code, r.json()["code"]) == (403, "forbidden"), r.text

    await forbidden(
        await ins.post(f"{C}/{cohort['id']}/enrollments", json={"student_id": str(student)})
    )
    await forbidden(
        await ins.post(
            f"{C}/{cohort['id']}/enrollments", json={"new_student": {"full_name": "Новый"}}
        )
    )
    await forbidden(
        await ins.patch(f"/api/v1/enrollments/{enrollment['id']}", json={"status": "отчислен"})
    )
    await forbidden(await ins.delete(f"/api/v1/enrollments/{enrollment['id']}"))
    await forbidden(await ins.post("/api/v1/students", json={"full_name": "X"}))
    await forbidden(await ins.patch(f"/api/v1/students/{student}", json={"full_name": "Y"}))
    await forbidden(await ins.patch(f"{C}/{cohort['id']}", json={"capacity": 3}))
    await forbidden(
        await ins.post(
            f"{C}/{cohort['id']}/lessons",
            json={"date": next_monday().isoformat(), "start_time": "15:00", "end_time": "16:00"},
        )
    )
    # reading their own cohort works
    assert (await ins.get(f"{C}/{cohort['id']}")).status_code == 200
    assert len((await ins.get(f"{C}/{cohort['id']}/enrollments")).json()) == 1
    # even if the owner hands the instructor role `change` rights, it stays read-only
    async with instructor_rights(cohorts="change", students="change"):
        await forbidden(
            await ins.post(f"{C}/{cohort['id']}/enrollments", json={"student_id": str(student)})
        )
        await forbidden(await ins.post("/api/v1/students", json={"full_name": "X"}))
    assert (await sql("SELECT count(*) FROM enrollment"))[0][0] == 1
