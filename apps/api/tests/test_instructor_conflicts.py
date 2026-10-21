"""One instructor, one lesson at a time: EXCLUDE (instructor × time) on lesson, a readable 409
(instructor_busy) on every path that makes or moves lessons, and old overlaps marked, not fatal."""

import asyncio
import uuid
from datetime import time, timedelta
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.cohorts.schedule import local_dt
from tests.conftest import SERVER_URL, TEST_DB, branch_id, make_user, sql
from tests.edu import C, body, make_cohort, make_course, make_room, next_monday

L = "/api/v1/lessons"


async def _instructor(login: str = "ins", branch: str | None = None) -> str:
    return str(await make_user(login, "instructor", branch=branch))


async def _lesson_instructors(cohort: dict[str, Any]) -> set[Any]:
    rows = await sql("SELECT DISTINCT instructor_id FROM lesson WHERE cohort_id = :c", c=cohort["id"])
    return {str(r[0]) if r[0] else None for r in rows}


def _busy(r: httpx.Response) -> dict[str, Any]:
    assert (r.status_code, r.json()["code"]) == (409, "instructor_busy"), r.text
    return r.json()["params"]  # type: ignore[no-any-return]


async def test_instructor_double_booking_same_branch(admin: httpx.AsyncClient) -> None:
    ins = await _instructor()
    course = await make_course()
    a = await make_cohort(admin, course, await make_room(name="R1"), instructor_id=ins)
    assert await _lesson_instructors(a) == {ins}  # copied onto every lesson
    # another room, the same instructor, an overlapping time
    room2 = await make_room(name="R2")
    dushanbe = str(await branch_id("Душанбе"))
    r = await admin.post(
        C, json=body(course, room2, start_time="11:00", end_time="12:00", instructor_id=ins,
                     branch_id=dushanbe),
    )  # fmt: skip
    params = _busy(r)
    assert params["cohort"] == a["code"]
    assert params["start"] == "10:00" and params["end"] == "11:30"
    assert (await sql("SELECT count(*) FROM cohort"))[0][0] == 1  # nothing left behind
    # touching times, other days, or another instructor are fine
    await make_cohort(admin, course, room2, start_time="11:30", end_time="13:00", instructor_id=ins)
    await make_cohort(admin, course, await make_room(name="R3"), weekdays=[2], instructor_id=ins)
    other = await _instructor("ins2")
    await make_cohort(admin, course, await make_room(name="R4"), instructor_id=other)
    # the database refuses it even when the API is bypassed
    with pytest.raises(IntegrityError, match="lesson_instructor_no_overlap"):
        await sql(
            "INSERT INTO lesson (cohort_id, room_id, lesson_date, starts_at, ends_at) "
            "SELECT cohort_id, :r, lesson_date, starts_at, ends_at FROM lesson "
            "WHERE cohort_id = :c ORDER BY starts_at LIMIT 1",
            r=await make_room(name="R5"),
            c=a["id"],
        )


async def test_instructor_double_booking_cross_branch(
    admin: httpx.AsyncClient, login_as: Any
) -> None:
    ins = await _instructor()  # no branch: may teach in both
    course = await make_course()
    a = await make_cohort(admin, course, await make_room(name="R1"), instructor_id=ins)
    ist = await make_room("Истаравшан", "R-Ist")
    r = await admin.post(
        C, json=body(course, ist, instructor_id=ins, branch_id=str(await branch_id("Истаравшан")))
    )
    params = _busy(r)
    assert params["cohort"] == "другого филиала"  # the other branch's cohort is not named
    assert a["code"] not in r.text
    # a branch manager sees the same, without the code
    manager = await login_as("man", "manager", branch="Истаравшан")
    r = await manager.post(C, json=body(course, ist, instructor_id=ins))
    assert _busy(r)["cohort"] == "другого филиала"


async def test_instructor_double_booking_cancelled_lesson_is_ignored(
    admin: httpx.AsyncClient,
) -> None:
    ins = await _instructor()
    course = await make_course()
    a = await make_cohort(admin, course, await make_room(name="R1"), weekdays=[1], instructor_id=ins)
    b = await make_cohort(admin, course, await make_room(name="R2"), weekdays=[2], instructor_id=ins)
    first = (await admin.get(f"{C}/{a['id']}/lessons")).json()[0]
    slot = {"date": first["date"], "start_time": "10:00", "end_time": "11:30"}
    _busy(await admin.post(f"{C}/{b['id']}/lessons", json=slot))
    assert (await admin.post(f"{L}/{first['id']}/cancel")).status_code == 200
    r = await admin.post(f"{C}/{b['id']}/lessons", json=slot)
    assert r.status_code == 201, r.text


async def test_instructor_double_booking_instructor_change_rechecks(
    admin: httpx.AsyncClient,
) -> None:
    one, two, three = await _instructor("i1"), await _instructor("i2"), await _instructor("i3")
    course = await make_course()
    a = await make_cohort(admin, course, await make_room(name="R1"), instructor_id=one)
    b = await make_cohort(admin, course, await make_room(name="R2"), instructor_id=two)
    r = await admin.patch(
        f"{C}/{b['id']}", json={"instructor_id": one}, headers={"X-Record-Version": "1"}
    )
    assert _busy(r)["cohort"] == a["code"]
    after = (await admin.get(f"{C}/{b['id']}")).json()
    assert after["instructor_id"] == two and await _lesson_instructors(b) == {two}
    # a free instructor takes the lessons ahead with them
    r = await admin.patch(
        f"{C}/{b['id']}",
        json={"instructor_id": three},
        headers={"X-Record-Version": str(after["version"])},
    )
    assert r.status_code == 200, r.text
    assert await _lesson_instructors(b) == {three}
    # ... and clearing the instructor frees them
    r = await admin.patch(
        f"{C}/{b['id']}",
        json={"instructor_id": None},
        headers={"X-Record-Version": str(r.json()["version"])},
    )
    assert r.status_code == 200 and await _lesson_instructors(b) == {None}


async def test_instructor_double_booking_moving_a_lesson(admin: httpx.AsyncClient) -> None:
    ins = await _instructor()
    course = await make_course()
    a = await make_cohort(admin, course, await make_room(name="R1"), weekdays=[1], instructor_id=ins)
    b = await make_cohort(admin, course, await make_room(name="R2"), weekdays=[2], instructor_id=ins)
    monday = next_monday()
    _busy(
        await admin.post(
            f"{C}/{b['id']}/lessons",
            json={"date": monday.isoformat(), "start_time": "11:00", "end_time": "12:00"},
        )
    )
    lesson = (await admin.get(f"{C}/{b['id']}/lessons")).json()[0]
    r = await admin.patch(
        f"{L}/{lesson['id']}",
        json={"date": monday.isoformat(), "start_time": "10:30", "end_time": "12:00"},
        headers={"X-Record-Version": str(lesson["version"])},
    )
    assert _busy(r)["cohort"] == a["code"]
    r = await admin.patch(
        f"{L}/{lesson['id']}",
        json={"date": monday.isoformat(), "start_time": "12:00", "end_time": "13:00"},
        headers={"X-Record-Version": str(lesson["version"])},
    )
    assert r.status_code == 200, r.text
    # moving within its own slot does not collide with itself
    r = await admin.patch(
        f"{L}/{lesson['id']}",
        json={"start_time": "12:30", "end_time": "13:30"},
        headers={"X-Record-Version": str(r.json()["version"])},
    )
    assert r.status_code == 200, r.text


async def test_instructor_double_booking_schedule_regeneration(admin: httpx.AsyncClient) -> None:
    ins = await _instructor()
    course = await make_course()
    a = await make_cohort(admin, course, await make_room(name="R1"), weekdays=[1], instructor_id=ins)
    b = await make_cohort(admin, course, await make_room(name="R2"), weekdays=[2], instructor_id=ins)
    before = await sql("SELECT count(*) FROM lesson WHERE cohort_id = :c", c=b["id"])
    r = await admin.patch(
        f"{C}/{b['id']}", json={"weekdays": [1, 2]}, headers={"X-Record-Version": "1"}
    )
    assert _busy(r)["cohort"] == a["code"]
    # the failed change left B's schedule and lessons as they were
    assert (await admin.get(f"{C}/{b['id']}")).json()["weekdays"] == [2]
    assert await sql("SELECT count(*) FROM lesson WHERE cohort_id = :c", c=b["id"]) == before
    r = await admin.patch(
        f"{C}/{b['id']}",
        json={"weekdays": [1, 2], "start_time": "12:00", "end_time": "13:30"},
        headers={"X-Record-Version": "1"},
    )
    assert r.status_code == 200, r.text


async def test_instructor_conflict_mark_shows_on_the_cohort_and_clears(
    admin: httpx.AsyncClient,
) -> None:
    """An old overlap (as migration 0015 or the import leaves it): marked on both lessons, shown
    on the cohort, cleared once one of them is cancelled."""
    ins = await _instructor()
    course = await make_course()
    a = await make_cohort(admin, course, await make_room(name="R1"), weekdays=[1], instructor_id=ins)
    b = await make_cohort(admin, course, await make_room(name="R2"), weekdays=[2], instructor_id=ins)
    first = (await admin.get(f"{C}/{a['id']}/lessons")).json()[0]
    await sql("UPDATE lesson SET instructor_conflict = true WHERE id = :i", i=first["id"])
    await sql(
        "INSERT INTO lesson (cohort_id, room_id, lesson_date, starts_at, ends_at, "
        "instructor_conflict) SELECT :b, :r, lesson_date, starts_at, ends_at, true "
        "FROM lesson WHERE id = :i",
        b=b["id"],
        r=b["room_id"],
        i=first["id"],
    )
    assert (await admin.get(f"{C}/{a['id']}")).json()["instructor_conflicts"] == 1
    assert (await admin.get(f"{C}/{b['id']}")).json()["instructor_conflicts"] == 1
    lessons = (await admin.get(f"{C}/{a['id']}/lessons")).json()
    assert [le["instructor_conflict"] for le in lessons][:2] == [True, False]
    # nothing new may overlap a marked lesson either
    _busy(
        await admin.post(
            f"{C}/{b['id']}/lessons",
            json={
                "date": first["date"], "start_time": "11:00", "end_time": "12:00",
                "room_id": str(await make_room(name="R3")),
            },
        )
    )  # fmt: skip
    assert (await admin.post(f"{L}/{first['id']}/cancel")).status_code == 200
    assert (await admin.get(f"{C}/{a['id']}")).json()["instructor_conflicts"] == 0
    assert (await admin.get(f"{C}/{b['id']}")).json()["instructor_conflicts"] == 0


# ---- migration 0015 on data that already overlaps ------------------------------------------


async def test_migration_0015_marks_existing_overlaps_instead_of_failing() -> None:
    name = f"{TEST_DB}_mig_ic"
    url = SERVER_URL.set(database=name)
    server = create_async_engine(SERVER_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")
    async with server.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url.render_as_string(hide_password=False))
    engine = create_async_engine(url)
    try:
        await asyncio.to_thread(command.upgrade, cfg, "0014")
        day = next_monday()
        ids = {k: uuid.uuid4() for k in ("ins", "r1", "r2", "r3", "co", "a", "b", "c")}
        async with engine.begin() as conn:

            async def q(sql_text: str, **params: Any) -> None:
                await conn.execute(text(sql_text), {**ids, **params})

            await q(
                "INSERT INTO app_user (id, full_name, login, password_hash, role_id) "
                "SELECT :ins, 'Инструктор', 'ins', 'x', id FROM role WHERE code = 'instructor'"
            )
            for room in ("r1", "r2", "r3"):
                await q(
                    "INSERT INTO room (id, branch_id, name, capacity) "
                    "SELECT :id, id, :n, 10 FROM branch WHERE name = 'Душанбе'",
                    id=ids[room],
                    n=room,
                )
            await q(
                "INSERT INTO course (id, name, default_price_month, duration_months, format) "
                "VALUES (:co, 'Python', 100, 3, 'offline')"
            )
            for cohort, room in (("a", "r1"), ("b", "r2"), ("c", "r3")):
                await q(
                    "INSERT INTO cohort (id, course_id, branch_id, instructor_id, room_id, "
                    "start_date, end_date, weekdays, start_time, end_time, capacity, "
                    "price_month) SELECT :id, :co, id, :ins, :room, :d, CAST(:d AS date) + 14, '{1}', '10:00', "
                    "'11:30', 10, 100 FROM branch WHERE name = 'Душанбе'",
                    id=ids[cohort],
                    room=ids[room],
                    d=day,
                )
            # A and B overlap (10:00-11:30, 11:00-12:00); C's cancelled lesson overlaps both;
            # A's second lesson the next week overlaps nothing
            for cohort, room, at, hours, cancelled in (
                ("a", "r1", day, ("10:00", "11:30"), False),
                ("b", "r2", day, ("11:00", "12:00"), False),
                ("c", "r3", day, ("10:00", "11:30"), True),
                ("a", "r1", day + timedelta(days=7), ("10:00", "11:30"), False),
            ):
                await q(
                    "INSERT INTO lesson (cohort_id, room_id, lesson_date, starts_at, ends_at, "
                    "cancelled) VALUES (:c, :r, :d, :s, :e, :x)",
                    c=ids[cohort],
                    r=ids[room],
                    d=at,
                    s=local_dt(at, time.fromisoformat(hours[0])),
                    e=local_dt(at, time.fromisoformat(hours[1])),
                    x=cancelled,
                )
        await asyncio.to_thread(command.upgrade, cfg, "head")  # does not fail
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT cohort_id, lesson_date, instructor_id, instructor_conflict "
                        "FROM lesson ORDER BY lesson_date, cohort_id"
                    )
                )
            ).all()
        marked = {(r[0], r[1]) for r in rows if r[3]}
        assert marked == {(ids["a"], day), (ids["b"], day)}  # both sides, nothing else
        assert {r[2] for r in rows} == {ids["ins"]}  # the cohort's instructor on every lesson
        # from now on the database refuses a new overlap
        with pytest.raises(IntegrityError, match="lesson_instructor_no_overlap"):
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO lesson (cohort_id, room_id, lesson_date, starts_at, ends_at) "
                        "SELECT :c, :r, lesson_date, starts_at, ends_at FROM lesson "
                        "WHERE cohort_id = :a AND lesson_date = :d"
                    ),
                    {"c": ids["c"], "r": ids["r3"], "a": ids["a"], "d": day + timedelta(days=7)},
                )
        await asyncio.to_thread(command.downgrade, cfg, "0014")  # and it goes back cleanly
    finally:
        await engine.dispose()
        async with server.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await server.dispose()
