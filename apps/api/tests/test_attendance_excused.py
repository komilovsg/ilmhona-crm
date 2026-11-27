"""«Уважительная»: an excused lesson leaves the held count (never an absence)."""

import httpx
import pytest
from sqlalchemy.exc import IntegrityError

from tests.conftest import SignedIn, sql
from tests.edu import C, make_student
from tests.test_attendance import L, enroll, mark, past_cohort, row_of


async def test_excused_is_left_out_of_the_denominator(admin: httpx.AsyncClient) -> None:
    cohort, lessons = await past_cohort(admin)
    e = await enroll(admin, cohort, "Алиев")
    for lesson in lessons[:4]:
        await mark(admin, lesson, e)
    assert (await mark(admin, lessons[4], e, present=False, excused=True)).status_code == 200
    row = await row_of(admin, cohort, e)
    assert (row["held"], row["present"], row["excused"], row["unmarked"]) == (8, 4, 1, 4)
    assert row["percent"] == 50.0  # 4 of 8, not 4 of 9
    grades = (await admin.get(f"{C}/{cohort['id']}/grades")).json()["rows"][0]
    assert (grades["held"], grades["percent"]) == (8, 50.0)


async def test_toggle_present_excused_absent(admin: httpx.AsyncClient) -> None:
    cohort, lessons = await past_cohort(admin)
    e = await enroll(admin, cohort, "Алиев")
    await mark(admin, lessons[0], e)
    await mark(admin, lessons[0], e, present=False, excused=True)
    row = await row_of(admin, cohort, e)
    assert (row["held"], row["present"], row["absent"]) == (8, 0, 0)
    assert row["marks"][lessons[0]]["excused"] is True
    await mark(admin, lessons[0], e, present=False)
    row = await row_of(admin, cohort, e)
    assert (row["held"], row["present"], row["absent"], row["excused"]) == (9, 0, 1, 0)
    log = (await admin.get("/api/v1/audit", params={"action": "attendance.mark"})).json()
    assert any("отметил уважительную причину" in i["text"] for i in log["items"])


async def test_excused_present_is_refused(admin: httpx.AsyncClient) -> None:
    cohort, lessons = await past_cohort(admin)
    e = await enroll(admin, cohort, "Алиев")
    r = await mark(admin, lessons[0], e, present=True, excused=True)
    assert r.status_code == 422
    with pytest.raises(IntegrityError):
        await sql(
            "INSERT INTO attendance (lesson_id, enrollment_id, present, excused) "
            "VALUES (:l, :e, true, true)",
            l=lessons[0],
            e=e,
        )


async def test_all_present_skips_excused(admin: httpx.AsyncClient) -> None:
    cohort, lessons = await past_cohort(admin)
    a = await enroll(admin, cohort, "Алиев")
    await enroll(admin, cohort, "Бобоев")
    await mark(admin, lessons[0], a, present=False, excused=True)
    page = (await admin.post(f"{L}/{lessons[0]}/attendance/all-present")).json()
    by = {s["student_name"]: s for s in page["students"]}
    assert (by["Алиев"]["present"], by["Алиев"]["excused"]) == (False, True)
    assert by["Бобоев"]["present"] is True


async def test_excused_in_analytics_is_not_an_absence(admin: httpx.AsyncClient) -> None:
    cohort, lessons = await past_cohort(admin)
    e = await enroll(admin, cohort, "Алиев")
    for lesson in lessons[:5]:
        await mark(admin, lesson, e, present=False, excused=True)
    row = await row_of(admin, cohort, e)
    assert (row["held"], row["percent"]) == (4, None if row["held"] == 0 else 0.0)
    an = await admin.get(f"{C}/{cohort['id']}/analytics")
    assert an.status_code == 200


async def test_instructor_scope_for_excused(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    ins = await login_as("ins", "instructor", branch="Душанбе")
    me = (await ins.get("/api/v1/auth/me")).json()["id"]
    mine, lessons = await past_cohort(admin, name="A", instructor_id=me)
    other, other_lessons = await past_cohort(admin, name="B")
    e, o = await enroll(admin, mine, "Свой"), await enroll(admin, other, "Чужой")
    assert (await mark(ins, lessons[0], e, present=False, excused=True)).status_code == 200
    assert (await mark(ins, other_lessons[0], o, present=False, excused=True)).status_code == 404


async def test_enrolling_past_20_works_and_all_students_listed(admin: httpx.AsyncClient) -> None:
    cohort, _ = await past_cohort(admin)
    await sql("UPDATE cohort SET capacity = 15")
    for i in range(23):
        sid = await make_student(f"Студент {i:02d}")
        r = await admin.post(f"{C}/{cohort['id']}/enrollments", json={"student_id": str(sid)})
        assert r.status_code == 201, (i, r.text)
        if i >= 15:
            assert r.json()["over_capacity"] == {"enrolled": i + 1, "capacity": 15}
    assert len((await admin.get(f"{C}/{cohort['id']}/enrollments")).json()) == 23
    assert len((await admin.get(f"{C}/{cohort['id']}/attendance")).json()["students"]) == 23
