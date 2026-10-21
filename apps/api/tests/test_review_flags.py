"""Review flags set by the import, shown and cleared in the app; the old total of a graduate."""

import json
from pathlib import Path
from typing import Any

import httpx

from tests.conftest import sql
from tests.test_importer import FIXTURE, do_import, one


def snapshot() -> dict[str, Any]:
    return json.loads(Path(FIXTURE).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


async def flagged(table: str, column: str, value: str) -> tuple[bool, str | None]:
    join = (
        "student s" if table == "student" else "student s JOIN enrollment e ON e.student_id = s.id"
    )
    alias = "s" if table == "student" else "e"
    return await one(  # type: ignore[no-any-return]
        f"SELECT {alias}.needs_review, {alias}.review_reason FROM {join} WHERE {column} = :v",
        v=value,
    )


async def test_import_flags_students() -> None:
    await do_import(snapshot(), apply=True)
    ok, why = await flagged("student", "s.full_name", "Зарина Придуманная")
    assert ok and why == "нет телефона"
    ok, why = await flagged("student", "s.full_name", "Ali Fakerov")
    assert ok and "проверить слияние" in (why or "") and "нет телефона" in (why or "")
    ok, why = await flagged("student", "s.full_name", "Тест Студентов")
    assert ok and "общий телефон — проверить" in (why or "")
    ok, why = await flagged("student", "s.full_name", "Мура Выдуманная")
    assert (ok, why) == (False, None)


async def test_import_flags_enrollments_restored_and_of_odd_cohorts() -> None:
    await do_import(snapshot(), apply=True)
    rows = await sql(
        "SELECT s.full_name, c.legacy_ref, e.needs_review, e.review_reason FROM enrollment e "
        "JOIN student s ON s.id = e.student_id JOIN cohort c ON c.id = e.cohort_id"
    )
    by = {(r[0], r[1]): (r[2], r[3]) for r in rows}
    # P-006: enrollment made from the payment
    assert by[("Зарина Придуманная", "COHORTS:G-001")] == (True, "восстановлено из оплаты")
    # G-004 has no usable schedule; G-003 is fine
    assert by[("Фейк Эмодзи", "COHORTS:G-004")] == (True, "нет расписания")
    assert by[("Нора Вымышленная", "COHORTS:G-003")] == (False, None)


async def test_old_total_is_stored_only_when_it_has_no_breakdown() -> None:
    await do_import(snapshot(), apply=True)
    rows = await sql(
        "SELECT s.full_name, e.legacy_total FROM enrollment e JOIN student s ON s.id = e.student_id "
        "WHERE e.legacy_total IS NOT NULL"
    )
    names = {r[0]: r[1] for r in rows}
    assert str(names["Тест Студентов"]) == "85.0"
    assert "Мура Выдуманная" not in names  # score:20|20|60 has the breakdown


async def test_students_filter_and_clear_the_flag(admin: httpx.AsyncClient) -> None:
    await do_import(snapshot(), apply=True)
    r = await admin.get("/api/v1/students", params={"needs_review": "true", "page_size": 100})
    items = r.json()["items"]
    names = {i["full_name"] for i in items}
    assert "Зарина Придуманная" in names and "Мура Выдуманная" not in names
    assert all(i["needs_review"] and i["review_reason"] for i in items)
    none = await admin.get("/api/v1/students", params={"needs_review": "false", "page_size": 100})
    assert "Мура Выдуманная" in {i["full_name"] for i in none.json()["items"]}
    zarina = next(i for i in items if i["full_name"] == "Зарина Придуманная")
    # detail carries the flag and the enrollments' flags
    detail = (await admin.get(f"/api/v1/students/{zarina['id']}")).json()
    assert detail["needs_review"]
    assert any(e["review_reason"] == "восстановлено из оплаты" for e in detail["enrollments"])
    # clear: versioned and audited
    stale = await admin.patch(
        f"/api/v1/students/{zarina['id']}",
        json={"needs_review": False},
        headers={"If-Match": str(zarina["version"] + 5)},
    )
    assert stale.status_code == 409
    done = await admin.patch(f"/api/v1/students/{zarina['id']}", json={"needs_review": False})
    assert done.status_code == 200 and done.json()["needs_review"] is False
    assert done.json()["review_reason"] is None
    audit = await sql(
        "SELECT diff FROM audit_log WHERE action = 'student.update' AND entity_id = :i",
        i=str(zarina["id"]),
    )
    assert audit[0][0]["needs_review"] == [True, False]


async def test_cohort_students_tab_shows_and_clears_the_enrollment_flag(
    admin: httpx.AsyncClient,
) -> None:
    await do_import(snapshot(), apply=True)
    cohort = await one("SELECT id FROM cohort WHERE legacy_ref = 'COHORTS:G-001'")
    rows = (await admin.get(f"/api/v1/cohorts/{cohort}/enrollments")).json()
    zarina = next(r for r in rows if r["student_name"] == "Зарина Придуманная")
    assert zarina["needs_review"] and zarina["review_reason"] == "восстановлено из оплаты"
    r = await admin.patch(
        f"/api/v1/enrollments/{zarina['id']}/review", json={"needs_review": False}
    )
    assert r.status_code == 200 and r.json()["needs_review"] is False
    assert r.json()["review_reason"] is None
    entry = await sql(
        "SELECT diff FROM audit_log WHERE action = 'enrollment.update' AND entity_id = :i",
        i=str(zarina["id"]),
    )
    assert entry[0][0]["needs_review"] == [True, False]


async def test_graduates_show_the_old_total_until_real_grades_exist(
    admin: httpx.AsyncClient,
) -> None:
    await do_import(snapshot(), apply=True)
    r = await admin.get("/api/v1/graduates/students", params={"page_size": 100})
    items = {i["student_name"]: i for i in r.json()["items"]}
    old = items["Тест Студентов"]  # a graduate by the old total of 85, no breakdown
    assert old["score"] == 85 and old["score_legacy"] is True
    real = items["Мура Выдуманная"]  # homework 40 + final 40 + attendance
    assert real["score_legacy"] is False and real["score"] >= 80
    # once a grade is entered the computed total takes over
    await sql(
        "INSERT INTO grade (enrollment_id, homework, final) VALUES (:e, 10, 10)",
        e=old["enrollment_id"],
    )
    r = await admin.get("/api/v1/graduates/students", params={"page_size": 100})
    again = {i["student_name"]: i for i in r.json()["items"]}["Тест Студентов"]
    assert again["score_legacy"] is False and again["score"] < 85


async def test_reapply_counts_everything_as_already_there() -> None:
    await do_import(snapshot(), apply=True)
    again = await do_import(snapshot(), apply=True)
    assert sum(again.imported.values()) == 0
    assert again.existing["STUDENTS"] == 9 and again.existing["GRADES"] >= 1
