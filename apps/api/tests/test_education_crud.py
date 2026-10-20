"""CRUD, schedule generation, lessons, enrollments, audit and the metrics/list agreement."""

from datetime import timedelta

import httpx

from app.cohorts.status import today
from tests.conftest import SignedIn, branch_id, make_role, sql
from tests.edu import C, body, make_cohort, make_course, make_room, make_student, next_monday

R, S = "/api/v1/rooms", "/api/v1/students"


async def test_rooms_and_courses_crud(admin: httpx.AsyncClient) -> None:
    dush = str(await branch_id("Душанбе"))
    r = await admin.post(R, json={"branch_id": dush, "name": "Lovelace", "capacity": 20})
    assert r.status_code == 201
    room = r.json()
    dup = await admin.post(R, json={"branch_id": dush, "name": "Lovelace", "capacity": 5})
    assert (dup.status_code, dup.json()["code"]) == (409, "room_name_taken")
    # same name in the other branch is fine
    istar = str(await branch_id("Истаравшан"))
    assert (
        await admin.post(R, json={"branch_id": istar, "name": "Lovelace", "capacity": 8})
    ).status_code == 201
    assert (
        await admin.post(R, json={"branch_id": dush, "name": "Big", "capacity": 101})
    ).status_code == 422
    assert (
        await admin.post(R, json={"branch_id": dush, "name": "Zero", "capacity": 0})
    ).status_code == 422
    r = await admin.patch(f"{R}/{room['id']}", json={"capacity": 25})
    assert r.json()["capacity"] == 25

    c = await admin.post(
        "/api/v1/courses",
        json={
            "name": "Python",
            "direction": "IT",
            "default_price_month": "450.50",
            "duration_months": 3,
            "format": "offline",
        },
    )
    assert c.status_code == 201 and c.json()["default_price_month"] == "450.50"
    course = c.json()
    dup = await admin.post(
        "/api/v1/courses",
        json={"name": "Python", "duration_months": 1, "format": "online"},
    )
    assert dup.json()["code"] == "course_name_taken"
    bad = await admin.post(
        "/api/v1/courses",
        json={"name": "Bad", "default_price_month": "-1", "duration_months": 1, "format": "online"},
    )
    assert bad.status_code == 422
    r = await admin.put(
        f"/api/v1/courses/{course['id']}",
        json={"name": "Python 2", "duration_months": 4, "format": "online"},
    )
    assert r.json()["name"] == "Python 2" and r.json()["format"] == "online"

    # in use: cannot delete
    await make_cohort(admin, uuid_of(course), uuid_of(room))
    r = await admin.delete(f"{R}/{room['id']}")
    assert (r.status_code, r.json()["code"]) == (409, "room_in_use")
    r = await admin.delete(f"/api/v1/courses/{course['id']}")
    assert (r.status_code, r.json()["code"]) == (409, "course_in_use")
    spare = (await admin.post(R, json={"branch_id": dush, "name": "Spare", "capacity": 5})).json()
    assert (await admin.delete(f"{R}/{spare['id']}")).status_code == 204
    assert [x["name"] for x in (await admin.get(R, params={"branch_id": dush})).json()] == [
        "Lovelace"
    ]


def uuid_of(row: dict) -> uuid.UUID:  # type: ignore[name-defined]  # noqa: F821
    import uuid

    return uuid.UUID(row["id"])


async def test_cohort_code_schedule_and_defaults(admin: httpx.AsyncClient) -> None:
    course, room = await make_course(price=700), await make_room()
    first = await make_cohort(admin, course, room, weekdays=[1, 3])
    second = await make_cohort(admin, course, await make_room(name="B"), weekdays=[5, 7], weeks=2)
    assert first["code"].startswith("G-") and len(first["code"]) == 5
    assert int(second["code"][2:]) == int(first["code"][2:]) + 1
    assert first["price_month"] == "700.00"  # defaults to the course price
    assert first["fill"] == {"enrolled": 0, "capacity": 10}
    lessons = (await admin.get(f"{C}/{first['id']}/lessons")).json()
    assert len(lessons) == 9  # Mon+Wed over 4 weeks + the end day (Monday)
    assert {le["start"] for le in lessons} == {"10:00"} and {le["end"] for le in lessons} == {
        "11:30"
    }
    assert all(not le["cancelled"] for le in lessons)
    weekdays = {(next_monday() + timedelta(days=0)).isoweekday()}
    assert weekdays == {1}
    sat_sun = (await admin.get(f"{C}/{second['id']}/lessons")).json()
    assert len(sat_sun) == 4  # Fri+Sun in a 2-week window (Mon..Mon)
    # weekdays are normalised
    third = await make_cohort(admin, course, await make_room(name="C"), weekdays=[3, 1, 3])
    assert third["weekdays"] == [1, 3]
    bad = await admin.post(
        C, json=body(course, room, weekdays=[0, 8], branch_id=str(await branch_id("Душанбе")))
    )
    assert bad.status_code == 422
    bad = await admin.post(
        C, json={**body(course, room, branch_id=str(await branch_id("Душанбе"))), "weekdays": []}
    )
    assert bad.status_code == 422
    bad = await admin.post(
        C, json={**body(course, room, branch_id=str(await branch_id("Душанбе"))), "capacity": 101}
    )
    assert bad.status_code == 422
    bad = await admin.post(
        C,
        json={**body(course, room, branch_id=str(await branch_id("Душанбе"))), "price_month": "-5"},
    )
    assert bad.status_code == 422


async def test_update_regenerates_only_future_lessons(admin: httpx.AsyncClient) -> None:
    course, room = await make_course(), await make_room()
    t = today()
    start = t - timedelta(days=14)
    cohort = await make_cohort(
        admin, course, room, start=start, weeks=6, weekdays=[1, 2, 3, 4, 5, 6, 7]
    )
    cid = cohort["id"]
    before = (await admin.get(f"{C}/{cid}/lessons")).json()
    past = [le for le in before if le["date"] < t.isoformat()]
    future = [le for le in before if le["date"] > t.isoformat()]
    assert len(past) == 14 and future
    r = await admin.patch(
        f"{C}/{cid}", json={"start_time": "15:00", "end_time": "16:00", "weekdays": [1, 2]}
    )
    assert r.status_code == 200, r.text
    after = (await admin.get(f"{C}/{cid}/lessons")).json()
    # past lessons: same rows, same time
    assert [le["id"] for le in after if le["date"] < t.isoformat()] == [le["id"] for le in past]
    assert {le["start"] for le in after if le["date"] < t.isoformat()} == {"10:00"}
    # future lessons: rebuilt on Mon/Tue at 15:00
    new_future = [le for le in after if le["date"] > t.isoformat()]
    assert new_future and {le["start"] for le in new_future} == {"15:00"}
    assert all(
        __import__("datetime").date.fromisoformat(le["date"]).isoweekday() in (1, 2)
        for le in new_future
    )
    log = (await admin.get("/api/v1/audit", params={"action": "cohort.update"})).json()["items"][0]
    assert log["diff"]["future_lessons"][0] >= len(future)  # + a lesson later today


async def test_cohort_list_filters_and_search(admin: httpx.AsyncClient) -> None:
    course, other_course = await make_course("Python"), await make_course("Дизайн")
    instructor = await __import__("tests.conftest", fromlist=["make_user"]).make_user(
        "ins", "instructor", branch="Душанбе"
    )
    a = await make_cohort(admin, course, await make_room(name="A"), instructor_id=str(instructor))
    b = await make_cohort(admin, other_course, await make_room(name="B"))
    await sql("UPDATE cohort SET status = 'активный' WHERE id = :i", i=b["id"])

    async def codes(**params: str) -> list[str]:
        return [c["code"] for c in (await admin.get(C, params=params)).json()["items"]]

    assert set(await codes()) == {a["code"], b["code"]}
    assert await codes(status="активный") == [b["code"]]
    assert await codes(status="набор") == [a["code"]]
    assert await codes(q="дизайн") == [b["code"]]
    assert await codes(q=a["code"].lower()) == [a["code"]]
    assert await codes(q="user ins") == [a["code"]]
    assert await codes(q="%") == []  # wildcards are escaped
    assert await codes(branch_id=str(await branch_id("Истаравшан"))) == []
    page = (await admin.get(C, params={"page_size": "1"})).json()
    assert page["total"] == 2 and len(page["items"]) == 1


async def test_cancel_restore_delete_cohort(admin: httpx.AsyncClient) -> None:
    course, room = await make_course(), await make_room()
    cohort = await make_cohort(admin, course, room)
    cid = cohort["id"]
    assert (await admin.post(f"{C}/{cid}/restore")).json()["code"] == "cohort_not_cancelled"
    assert (await admin.post(f"{C}/{cid}/cancel")).json()["status"] == "отменён"
    assert (await sql("SELECT count(*) FROM lesson WHERE NOT cancelled"))[0][0] == 0
    # the room is free again
    other = await make_cohort(admin, course, room)
    assert (await admin.post(f"{C}/{cid}/restore")).json()["code"] == "room_busy"
    assert (await admin.delete(f"{C}/{other['id']}")).status_code == 204
    assert (await admin.post(f"{C}/{cid}/restore")).json()["status"] == "набор"
    student = await make_student()
    await admin.post(f"{C}/{cid}/enrollments", json={"student_id": str(student)})
    r = await admin.delete(f"{C}/{cid}")
    assert (r.status_code, r.json()["code"]) == (409, "cohort_in_use")


async def test_enrollment_flow_capacity_and_new_student(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    course, room = await make_course(), await make_room()
    cohort = await make_cohort(admin, course, room, capacity=2)
    cid = cohort["id"]
    r = await admin.post(
        f"{C}/{cid}/enrollments",
        json={
            "new_student": {
                "full_name": "  Новичок ",
                "phone": "+992 900 11 22 33",
                "gender": "female",
            }
        },
    )
    assert (
        r.status_code == 201
        and r.json()["student_name"] == "Новичок"
        and r.json()["status"] == "активный"
    )
    assert (await admin.post(f"{C}/{cid}/enrollments", json={})).status_code == 422
    assert (
        await admin.post(
            f"{C}/{cid}/enrollments",
            json={"student_id": str(await make_student()), "new_student": {"full_name": "x"}},
        )
    ).status_code == 422
    second = await admin.post(
        f"{C}/{cid}/enrollments", json={"student_id": str(await make_student("Второй"))}
    )
    assert second.status_code == 201
    full = await admin.post(
        f"{C}/{cid}/enrollments", json={"student_id": str(await make_student("Третий"))}
    )
    assert (full.status_code, full.json()["code"]) == (409, "cohort_full")
    # an expelled student frees a seat
    await admin.patch(f"/api/v1/enrollments/{second.json()['id']}", json={"status": "отчислен"})
    assert (await admin.get(f"{C}/{cid}")).json()["fill"] == {"enrolled": 1, "capacity": 2}
    assert (
        await admin.post(
            f"{C}/{cid}/enrollments", json={"student_id": str(await make_student("Третий"))}
        )
    ).status_code == 201
    # cannot shrink below the enrolled count
    assert (await admin.patch(f"{C}/{cid}", json={"capacity": 1})).json()["code"] == "cohort_full"
    assert (
        await admin.patch(
            f"/api/v1/enrollments/{second.json()['id']}", json={"status": "нет такого"}
        )
    ).status_code == 422
    assert (await admin.delete(f"/api/v1/enrollments/{second.json()['id']}")).status_code == 204
    # a manager without `students` change cannot create a student through enrollment
    mgr = await login_as(
        "only_cohorts", await make_role("Только потоки", {"cohorts": "change"}), branch="Душанбе"
    )
    r = await mgr.post(f"{C}/{cid}/enrollments", json={"new_student": {"full_name": "Тайный"}})
    assert (r.status_code, r.json()["code"]) == (403, "forbidden")
    assert (await sql("SELECT count(*) FROM student WHERE full_name = 'Тайный'"))[0][0] == 0


async def test_students_crud_search_history_and_phone(admin: httpx.AsyncClient) -> None:
    dush = str(await branch_id("Душанбе"))
    r = await admin.post(
        S,
        json={
            "full_name": "Рахимов Рахим",
            "phone": "+992 901 00 00 01",
            "gender": "male",
            "branch_id": dush,
        },
    )
    assert r.status_code == 201 and r.json()["status"] == "без зачисления"
    sid = r.json()["id"]
    await admin.post(
        S, json={"full_name": "Каримова Мадина", "phone": "+992 902 00 00 02", "branch_id": dush}
    )
    assert (
        await admin.post(S, json={"full_name": "x", "gender": "other", "branch_id": dush})
    ).status_code == 422
    assert (await admin.post(S, json={"full_name": "   ", "branch_id": dush})).status_code == 422

    def names(res: httpx.Response) -> list[str]:
        return [s["full_name"] for s in res.json()["items"]]

    assert names(await admin.get(S, params={"q": "рахим"})) == ["Рахимов Рахим"]
    assert names(await admin.get(S, params={"q": "902"})) == ["Каримова Мадина"]
    assert names(await admin.get(S, params={"q": "%"})) == []
    r = await admin.patch(f"{S}/{sid}", json={"phone": None, "full_name": "Рахимов Р."})
    assert r.json()["phone"] is None and r.json()["full_name"] == "Рахимов Р."

    course, room = await make_course(), await make_room()
    cohort = await make_cohort(admin, course, room)
    await admin.post(f"{C}/{cohort['id']}/enrollments", json={"student_id": sid})
    detail = (await admin.get(f"{S}/{sid}")).json()
    assert detail["status"] == "активный" and detail["enrollments_count"] == 1
    assert detail["enrollments"][0]["cohort_code"] == cohort["code"]
    assert detail["enrollments"][0]["course_name"] == "Python"
    r = await admin.delete(f"{S}/{sid}")
    assert (r.status_code, r.json()["code"]) == (409, "student_in_use")
    free = (await admin.get(S, params={"q": "Каримова"})).json()["items"][0]["id"]
    assert (await admin.delete(f"{S}/{free}")).status_code == 204
    assert (await admin.get(f"{S}/{free}")).status_code == 404


async def test_week_schedule_grid(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    course = await make_course()
    room, room_b = await make_room(name="A"), await make_room(name="B")
    monday = next_monday()
    cohort = await make_cohort(admin, course, room, weekdays=[1])
    await make_cohort(admin, course, room_b, weekdays=[2], start_time="12:00", end_time="13:00")
    r = await admin.get(f"{R}/schedule", params={"date_from": monday.isoformat()})
    grid = r.json()
    assert [x["name"] for x in grid["rooms"]] == ["A", "B"]
    assert grid["date_to"] == (monday + timedelta(days=6)).isoformat()
    assert {
        (le["date"], le["cohort_code"]) for le in grid["lessons"] if le["room_id"] == str(room)
    } == {(monday.isoformat(), cohort["code"])}
    assert len(grid["lessons"]) == 2
    # a cancelled lesson leaves the grid
    first = (await admin.get(f"{C}/{cohort['id']}/lessons")).json()[0]
    await admin.post(f"/api/v1/lessons/{first['id']}/cancel")
    grid = (await admin.get(f"{R}/schedule", params={"date_from": monday.isoformat()})).json()
    assert len(grid["lessons"]) == 1
    assert (
        await admin.get(
            f"{R}/schedule", params={"date_from": monday.isoformat(), "date_to": "2000-01-01"}
        )
    ).status_code == 422
    # branch-bound: only own rooms
    mgr = await login_as("m", await make_role("Ш", {"rooms": "view"}), branch="Истаравшан")
    grid = (await mgr.get(f"{R}/schedule", params={"date_from": monday.isoformat()})).json()
    assert grid["rooms"] == [] and grid["lessons"] == []


async def test_every_write_is_audited(admin: httpx.AsyncClient) -> None:
    dush = str(await branch_id("Душанбе"))
    room = (await admin.post(R, json={"branch_id": dush, "name": "R", "capacity": 5})).json()
    course = (
        await admin.post(
            "/api/v1/courses", json={"name": "C", "duration_months": 1, "format": "online"}
        )
    ).json()
    cohort = await make_cohort(admin, uuid_of(course), uuid_of(room))
    student = (await admin.post(S, json={"full_name": "S", "branch_id": dush})).json()
    enr = (
        await admin.post(f"{C}/{cohort['id']}/enrollments", json={"student_id": student["id"]})
    ).json()
    lesson = (
        await admin.post(
            f"{C}/{cohort['id']}/lessons",
            json={
                "date": (next_monday() + timedelta(days=1)).isoformat(),
                "start_time": "15:00",
                "end_time": "16:00",
            },
        )
    ).json()
    await admin.patch(
        f"/api/v1/lessons/{lesson['id']}", json={"start_time": "16:00", "end_time": "17:00"}
    )
    await admin.post(f"/api/v1/lessons/{lesson['id']}/cancel")
    await admin.patch(f"/api/v1/enrollments/{enr['id']}", json={"status": "выпускник"})
    await admin.patch(f"{C}/{cohort['id']}", json={"capacity": 12})
    await admin.post(f"{C}/{cohort['id']}/cancel")
    await admin.delete(f"/api/v1/enrollments/{enr['id']}")
    await admin.patch(f"{S}/{student['id']}", json={"full_name": "S2"})
    await admin.delete(f"{S}/{student['id']}")
    actions = {a for (a,) in await sql("SELECT action FROM audit_log")}
    assert {
        "room.create",
        "course.create",
        "cohort.create",
        "student.create",
        "enrollment.create",
        "lesson.create",
        "lesson.move",
        "lesson.cancel",
        "enrollment.update",
        "cohort.update",
        "cohort.cancel",
        "enrollment.delete",
        "student.update",
        "student.delete",
    } <= actions
    created = (await admin.get("/api/v1/audit", params={"action": "cohort.create"})).json()[
        "items"
    ][0]
    assert created["diff"]["code"][1] == cohort["code"]


async def test_metrics_agree_with_the_lists(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    """One fixture, every number from two sides: the summary vs the list endpoints."""
    course = await make_course()
    a = await make_cohort(admin, course, await make_room(name="A"), capacity=5)
    b = await make_cohort(admin, course, await make_room(name="B"), capacity=3)
    istar = await make_cohort(
        admin, course, await make_room("Истаравшан", "I"), branch="Истаравшан", capacity=4
    )
    await sql("UPDATE cohort SET status = 'активный' WHERE id = :i", i=a["id"])
    await sql("UPDATE cohort SET status = 'завершён' WHERE id = :i", i=b["id"])
    plan = {  # student -> [(cohort, status)]
        "Активный 1": [(a, "активный")],
        "Активный 2": [(a, "активный"), (b, "завершил")],
        "Выпускник": [(b, "выпускник")],
        "Выпускник и активный": [(b, "выпускник"), (a, "активный")],
        "Отчисленный": [(a, "отчислен")],
        "Только завершил": [(b, "завершил")],
        "Без потока": [],
    }
    for name, rows in plan.items():
        sid = await make_student(name)
        for cohort, status in rows:
            await sql(
                "INSERT INTO enrollment (cohort_id, student_id, status) VALUES (:c, :s, :t)",
                c=cohort["id"],
                s=sid,
                t=status,
            )
    other = await make_student("Из Истаравшана", branch="Истаравшан")
    await sql(
        "INSERT INTO enrollment (cohort_id, student_id) VALUES (:c, :s)", c=istar["id"], s=other
    )

    async def check(client: httpx.AsyncClient) -> dict:
        summary = (await client.get("/api/v1/metrics/education")).json()
        listed = (await client.get(S, params={"page_size": "100"})).json()
        assert summary["students"]["всего"] == listed["total"]
        for status in ("активный", "выпускник", "отчислен", "без зачисления"):
            by_list = (await client.get(S, params={"status": status})).json()
            assert summary["students"][status] == by_list["total"], status
            assert all(s["status"] == status for s in by_list["items"])
        assert (
            sum(
                summary["students"][s]
                for s in ("активный", "выпускник", "отчислен", "без зачисления")
            )
            == listed["total"]
        )
        cohorts = (await client.get(C, params={"page_size": "100"})).json()
        assert summary["cohorts"]["всего"] == cohorts["total"]
        for status in ("набор", "активный", "завершён", "отменён"):
            assert (
                summary["cohorts"][status]
                == (await client.get(C, params={"status": status})).json()["total"]
            )
        assert summary["active_cohorts"] == summary["cohorts"]["активный"]
        for item in cohorts["items"]:
            members = (await client.get(f"{C}/{item['id']}/enrollments")).json()
            assert item["fill"]["enrolled"] == len(
                [m for m in members if m["status"] != "отчислен"]
            )
            assert (await client.get(f"{C}/{item['id']}")).json()["fill"] == item["fill"]
        return summary  # type: ignore[no-any-return]

    everything = await check(admin)
    assert everything["students"]["всего"] == 8
    assert everything["students"]["активный"] == 4  # A1, A2, grad+active, Из Истаравшана
    assert everything["students"]["выпускник"] == 1
    assert everything["students"]["отчислен"] == 1
    assert everything["students"]["без зачисления"] == 2  # no enrollment, only «завершил»
    fills = {c["code"]: c["fill"] for c in (await admin.get(C)).json()["items"]}
    assert fills[a["code"]] == {
        "enrolled": 3,
        "capacity": 5,
    }  # A1, A2, grad+active (expelled excluded)
    assert fills[b["code"]] == {"enrolled": 4, "capacity": 3}

    mgr = await login_as(
        "m", await make_role("Ш", {"cohorts": "view", "students": "view"}), branch="Душанбе"
    )
    scoped = await check(mgr)
    assert scoped["students"]["всего"] == 7 and scoped["cohorts"]["всего"] == 2
