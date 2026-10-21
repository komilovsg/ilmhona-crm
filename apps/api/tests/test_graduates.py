"""Stage 4: graduates, certificates, employment (#13), status re-evaluation, enrollment delete."""

import asyncio
from collections.abc import Callable
from datetime import datetime, time, timedelta
from io import BytesIO
from typing import Any

import httpx
import pytest
from openpyxl import load_workbook
from sqlalchemy.exc import IntegrityError

from app.cohorts.status import today
from tests.conftest import SignedIn, make_role, sql
from tests.money import enroll, pay, running_cohort
from tests.reports import EM, ML, E, G, employ, finished_cohort, grade, student_of, world


async def statuses() -> dict[str, str]:
    return {str(i): s for i, s in await sql("SELECT id, status FROM enrollment")}


async def test_seeded_manager_role_marks_attendance_by_default() -> None:
    rows = await sql(
        "SELECT level FROM role_permission WHERE section = 'attendance' "
        "AND role_id = (SELECT id FROM role WHERE code = 'manager')"
    )
    assert rows == [("change",)]


# ---- #13 ---------------------------------------------------------------------------------


async def test_bug_13_employment_lives_in_one_table(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    w = await world(admin, browser)
    one = w["done_ids"]["Выпускник Один"]
    cols = await sql(
        "SELECT table_name FROM information_schema.columns WHERE table_schema = 'public' "
        "AND column_name IN ('organization', 'employed_at')"
    )
    assert {t for (t,) in cols} == {"employment"}
    r = await employ(admin, await student_of(one), "ООО Рога", position="Разработчик")
    assert r.status_code == 201, r.text
    rows = (await admin.get(f"{G}/students")).json()["items"]
    mine = next(x for x in rows if x["enrollment_id"] == one)
    assert (mine["employed"], mine["organization"]) == (True, "ООО Рога")
    courses = (await admin.get(f"{G}/courses")).json()["items"]
    assert (courses[0]["employed"], courses[0]["employed_percent"]) == (1, 100.0)
    master = (await admin.get(ML)).json()["items"]
    assert next(m for m in master if m["cohort_id"] == w["done"]["id"])["employed"] == 1
    listed = (await admin.get(EM)).json()
    assert listed["total"] == 1 and listed["items"][0]["organization"] == "ООО Рога"
    # deleting the one record clears it everywhere
    assert (await admin.delete(f"{EM}/{listed['items'][0]['id']}")).status_code == 204
    rows = (await admin.get(f"{G}/students")).json()["items"]
    assert not any(x["employed"] for x in rows)
    master = (await admin.get(ML)).json()["items"]
    assert next(m for m in master if m["cohort_id"] == w["done"]["id"])["employed"] == 0
    assert (await admin.get(EM)).json()["total"] == 0


async def test_employment_rules_scope_and_versions(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient], login_as: SignedIn
) -> None:
    w = await world(admin, browser)
    grad = await student_of(w["done_ids"]["Выпускник Один"])
    plain = await student_of(w["done_ids"]["Выпускник Два"])  # завершил: not a graduate
    r = await employ(admin, plain)
    assert (r.status_code, r.json()["code"]) == (409, "not_graduate")
    live = await student_of((await sql("SELECT id FROM enrollment LIMIT 1"))[0][0])
    other_enrollment = str(
        (await sql("SELECT id FROM enrollment WHERE student_id != :s", s=grad))[0][0]
    )
    r = await employ(admin, grad, enrollment_id=other_enrollment)
    assert (r.status_code, r.json()["code"]) == (422, "employment_enrollment_mismatch")
    r = await employ(admin, grad, employed_at="1999-01-01")
    assert r.status_code == 422
    r = await employ(admin, grad, enrollment_id=w["done_ids"]["Выпускник Один"])
    assert r.status_code == 201
    job = r.json()
    assert job["course_name"] == "Курс F"
    r = await admin.patch(f"{EM}/{job['id']}", json={"organization": "Другая"})
    assert r.status_code == 200 and r.json()["organization"] == "Другая"
    stale = await admin.patch(
        f"{EM}/{job['id']}",
        json={"position": "X"},
        headers={"X-Record-Version": str(job["version"])},
    )
    assert (stale.status_code, stale.json()["code"]) == (409, "stale_version")
    # a viewer reads but cannot write; a Душанбе manager does not see Истаравшан students
    viewer = await login_as("viewer", await make_role("Вид", {"graduates": "view"}))
    assert (await viewer.get(EM)).json()["total"] == 1
    assert (
        await viewer.post(
            EM, json={"student_id": grad, "organization": "A", "employed_at": today().isoformat()}
        )
    ).status_code == 403
    assert (await viewer.delete(f"{EM}/{job['id']}")).status_code == 403
    ist = await login_as(
        "ist", await make_role("Ист", {"graduates": "change"}), branch="Истаравшан"
    )
    assert (await ist.get(EM)).json()["total"] == 0
    assert (await ist.patch(f"{EM}/{job['id']}", json={"organization": "Z"})).status_code == 404
    assert (await ist.get(f"{G}/students")).json()["total"] == 0
    _ = live
    log = (await admin.get("/api/v1/audit", params={"action": "employment.create"})).json()
    assert "трудоустройство студента" in log["items"][0]["text"]


# ---- certificates ------------------------------------------------------------------------


async def test_certificates_are_numbered_once_and_only_for_graduates(
    admin: httpx.AsyncClient,
) -> None:
    cohort, ids = await finished_cohort(
        admin, {"Первый": (40, 35), "Второй": (40, 40), "Третий": (10, 10)}
    )
    year = today().year
    r = await admin.post(f"{G}/{ids['Первый']}/certificate")
    assert r.status_code == 200 and r.json()["certificate_no"] == f"CERT-{year}-0001"
    a, b = await asyncio.gather(
        admin.post(f"{G}/{ids['Второй']}/certificate"),
        admin.post(f"{G}/{ids['Первый']}/certificate"),
    )
    assert (a.status_code, b.status_code) == (200, 409) and b.json()["code"] == "certificate_issued"
    assert a.json()["certificate_no"] == f"CERT-{year}-0002"
    r = await admin.post(f"{G}/{ids['Третий']}/certificate")
    assert (r.status_code, r.json()["code"]) == (409, "not_graduate")
    rows = (await admin.get(f"{G}/students", params={"certificate": "true"})).json()
    assert rows["total"] == 2
    # a certified graduate keeps the status; the database says so too
    r = await admin.patch(f"{E}/{ids['Первый']}", json={"status": "завершил"})
    assert (r.status_code, r.json()["code"]) == (409, "certificate_issued")
    with pytest.raises(IntegrityError):
        await sql("UPDATE enrollment SET status = 'завершил' WHERE id = :i", i=ids["Первый"])
    with pytest.raises(IntegrityError):
        await sql("UPDATE enrollment SET certificate_no = 'CERT-1' WHERE id = :i", i=ids["Третий"])
    log = (await admin.get("/api/v1/audit", params={"action": "enrollment.certificate"})).json()
    assert "выдан сертификат CERT-" in log["items"][0]["text"]
    _ = cohort


async def test_certificate_needs_the_graduates_change_right(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    _, ids = await finished_cohort(admin, {"Первый": (40, 35)})
    viewer = await login_as("viewer", await make_role("Вид", {"graduates": "view"}))
    assert (await viewer.post(f"{G}/{ids['Первый']}/certificate")).status_code == 403


# ---- status_manual and re-evaluation -----------------------------------------------------


async def test_grade_change_on_a_finished_cohort_re_evaluates_unless_manual(
    admin: httpx.AsyncClient,
) -> None:
    _, ids = await finished_cohort(admin, {"Вверх": (30, 30), "Вниз": (40, 35), "Ручной": (40, 35)})
    assert await statuses() == {
        ids["Вверх"]: "завершил", ids["Вниз"]: "выпускник", ids["Ручной"]: "выпускник",
    }  # fmt: skip
    await grade(admin, ids["Вверх"], 30, 40)  # 70
    await grade(admin, ids["Вниз"], 30, 30)  # 60
    st = await statuses()
    assert (st[ids["Вверх"]], st[ids["Вниз"]]) == ("выпускник", "завершил")
    log = (await admin.get("/api/v1/audit", params={"action": "enrollment.update"})).json()
    assert any("пересчёт по оценкам" in i["text"] for i in log["items"])
    # a manager's hand-set status is never overwritten
    r = await admin.patch(f"{E}/{ids['Ручной']}", json={"status": "выпускник"})
    assert r.status_code == 200
    assert (await sql("SELECT status_manual FROM enrollment WHERE id = :i", i=ids["Ручной"]))[0][0]
    await grade(admin, ids["Ручной"], 0, 0)
    assert (await statuses())[ids["Ручной"]] == "выпускник"
    # the re-evaluated one is not manual
    assert not (await sql("SELECT status_manual FROM enrollment WHERE id = :i", i=ids["Вверх"]))[0][
        0
    ]


async def test_grade_change_on_a_running_cohort_leaves_statuses(admin: httpx.AsyncClient) -> None:
    cohort = await running_cohort(admin)
    e = await enroll(admin, cohort, "Идёт")
    await grade(admin, e, 40, 40)
    assert (await statuses())[e] == "активный"


async def test_certificate_blocks_the_automatic_demotion(admin: httpx.AsyncClient) -> None:
    _, ids = await finished_cohort(admin, {"С сертификатом": (40, 35)})
    assert (await admin.post(f"{G}/{ids['С сертификатом']}/certificate")).status_code == 200
    await grade(admin, ids["С сертификатом"], 0, 0)
    assert (await statuses())[ids["С сертификатом"]] == "выпускник"


# ---- deleting an enrollment --------------------------------------------------------------


async def test_enrollment_with_payments_cannot_be_deleted(admin: httpx.AsyncClient) -> None:
    cohort = await running_cohort(admin)
    e = await enroll(admin, cohort, "Платил")
    await pay(admin, e)
    r = await admin.delete(f"{E}/{e}")
    assert (r.status_code, r.json()["code"]) == (409, "enrollment_has_payments")
    assert (await sql("SELECT count(*) FROM enrollment"))[0][0] == 1


async def test_deleting_an_enrollment_names_the_lost_marks_and_grade(
    admin: httpx.AsyncClient,
) -> None:
    cohort = await running_cohort(admin)
    e = await enroll(admin, cohort, "Без оплат")
    await grade(admin, e, 20, 20)
    lesson = (await sql("SELECT id FROM lesson WHERE cohort_id = :c LIMIT 1", c=cohort["id"]))[0][0]
    await sql(
        "INSERT INTO attendance (lesson_id, enrollment_id, present) VALUES (:l, :e, true)",
        l=lesson,
        e=e,
    )
    assert (await admin.delete(f"{E}/{e}")).status_code == 204
    log = (await admin.get("/api/v1/audit", params={"action": "enrollment.delete"})).json()
    text = log["items"][0]["text"]
    assert "убран из потока" in text and "отметок посещаемости: 1" in text and "оценки" in text


# ---- lists and Excel ---------------------------------------------------------------------


async def test_graduate_views_and_excel(
    admin: httpx.AsyncClient, browser: Callable[[], httpx.AsyncClient]
) -> None:
    w = await world(admin, browser)
    one = w["done_ids"]["Выпускник Один"]
    await employ(admin, await student_of(one), "ООО Рога")
    row = (await admin.get(f"{G}/students")).json()["items"][0]
    assert (row["student_name"], row["course_name"], row["score"], row["paid"]) == (
        "Выпускник Один", "Курс F", 75, "300.00",
    )  # fmt: skip
    assert row["instructor_name"] == "User ins1" and row["certificate_no"] is None
    assert (await admin.get(f"{G}/students", params={"employed": "false"})).json()["total"] == 0
    course = (await admin.get(f"{G}/courses")).json()["items"][0]
    assert (course["graduates"], course["avg_score"], course["employed_percent"]) == (
        1,
        75.0,
        100.0,
    )
    for url, rows in (
        (f"{G}/students/export", 1),
        (f"{G}/courses/export", 1),
        (f"{EM}/export", 1),
        (f"{ML}/export", 4),
        ("/api/v1/dashboard/by-month/export", 12),
    ):
        r = await admin.get(url)
        assert r.status_code == 200, url
        ws = load_workbook(BytesIO(r.content)).active
        assert ws is not None and ws.max_row == rows + 1, url
    log = (await admin.get("/api/v1/audit", params={"action": "export"})).json()
    assert log["total"] == 5


_ = (datetime, time, timedelta, Any)
