"""#24 as relaxed on 2026-11-13: an instructor adds new students to their own cohort and takes
back the ones they added. These lock down the edges: what a manager decided about the row stays,
the check-then-delete holds against writes in flight, and a write that loses the race to the
delete answers 404 instead of a 500."""

import asyncio
from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.cohorts.status import today
from app.core.db import sessionmaker
from tests.conftest import SignedIn, sql
from tests.edu import C
from tests.test_attendance import NEW, E, mark, past_cohort


async def _instructor_cohort(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> tuple[httpx.AsyncClient, dict[str, Any], list[str]]:
    ins = await login_as("ins", "instructor", branch="Душанбе")
    me = (await ins.get("/api/v1/auth/me")).json()["id"]
    cohort, lessons = await past_cohort(admin, name="A", instructor_id=me)
    return ins, cohort, lessons


async def _add(ins: httpx.AsyncClient, cohort: dict[str, Any]) -> dict[str, Any]:
    r = await ins.post(f"{C}/{cohort['id']}/enrollments", json=NEW)
    assert r.status_code == 201, r.text
    await sql(
        "UPDATE enrollment SET enrolled_at = :d WHERE id = :i",
        d=today() - timedelta(days=30),
        i=r.json()["id"],
    )
    return r.json()  # type: ignore[no-any-return]


async def _open_tx(stmt: str, **params: Any) -> AsyncSession:
    """Another user's write, begun and not committed yet (it holds its row locks)."""
    db = sessionmaker()
    await db.execute(text(stmt), params)
    return db


@pytest.mark.parametrize("status", ["выпускник", "завершил", "отчислен"])
async def test_bug_24_instructor_cannot_remove_a_row_a_manager_set_status_on(
    admin: httpx.AsyncClient, login_as: SignedIn, status: str
) -> None:
    """Statuses are the manager's (#24): a graduated, completed or expelled row is no longer
    the instructor's mistake to take back."""
    ins, cohort, _ = await _instructor_cohort(admin, login_as)
    added = await _add(ins, cohort)
    assert (await admin.patch(f"{E}/{added['id']}", json={"status": status})).status_code == 200
    listed = (await ins.get(f"{C}/{cohort['id']}/enrollments")).json()
    assert [(x["created_by_me"], x["deletable"]) for x in listed] == [(True, False)]
    r = await ins.delete(f"{E}/{added['id']}")
    assert (r.status_code, r.json()["code"]) == (409, "enrollment_has_records")
    assert await sql("SELECT status FROM enrollment WHERE id = :i", i=added["id"]) == [(status,)]


async def _graduate_with_job(admin: httpx.AsyncClient, added: dict[str, Any]) -> None:
    eid = added["id"]
    assert (await admin.patch(f"{E}/{eid}", json={"status": "выпускник"})).status_code == 200
    r = await admin.post(
        "/api/v1/employment",
        json={
            "student_id": added["student_id"],
            "enrollment_id": eid,
            "organization": "ООО Тест",
            "employed_at": str(today()),
        },
    )
    assert r.status_code == 201, r.text


async def test_bug_24_instructor_cannot_erase_a_graduate_with_certificate_and_job(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    ins, cohort, _ = await _instructor_cohort(admin, login_as)
    added = await _add(ins, cohort)
    eid = added["id"]
    await _graduate_with_job(admin, added)
    # issued by hand: the API would take a number from the sequence test_graduates counts on
    await sql(
        "UPDATE enrollment SET certificate_no = 'CERT-TEST', certificate_issued_at = now() "
        "WHERE id = :i",
        i=eid,
    )
    r = await ins.delete(f"{E}/{eid}")
    assert (r.status_code, r.json()["code"]) == (409, "enrollment_has_records")
    (row,) = await sql(
        "SELECT e.certificate_no IS NOT NULL, j.enrollment_id FROM enrollment e "
        "JOIN employment j ON j.student_id = e.student_id WHERE e.id = :i",
        i=eid,
    )
    assert row[0] is True and str(row[1]) == eid


async def test_bug_24_instructor_cannot_unlink_a_job_from_an_active_row(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    """A job recorded against the row keeps it even after a manager puts it back to active."""
    ins, cohort, _ = await _instructor_cohort(admin, login_as)
    added = await _add(ins, cohort)
    eid = added["id"]
    await _graduate_with_job(admin, added)
    assert (await admin.patch(f"{E}/{eid}", json={"status": "активный"})).status_code == 200
    listed = (await ins.get(f"{C}/{cohort['id']}/enrollments")).json()
    assert [x["deletable"] for x in listed] == [False]
    r = await ins.delete(f"{E}/{eid}")
    assert (r.status_code, r.json()["code"]) == (409, "enrollment_has_records")
    assert [str(e) for (e,) in await sql("SELECT enrollment_id FROM employment")] == [eid]


async def test_bug_24_instructor_delete_waits_for_a_payment_in_flight(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    """The check and the delete are one step: a payment being written meanwhile is seen."""
    ins, cohort, _ = await _instructor_cohort(admin, login_as)
    added = await _add(ins, cohort)
    other = await _open_tx(
        "INSERT INTO payment (enrollment_id, month_no, amount, method, paid_at, "
        "idempotency_key) VALUES (:e, 1, 100, 'alif', :d, gen_random_uuid())",
        e=added["id"],
        d=today(),
    )
    try:
        delete = asyncio.create_task(ins.delete(f"{E}/{added['id']}"))
        await asyncio.sleep(0.3)
        assert not delete.done()  # blocked on the payment's lock of the enrollment row
        await other.commit()
    finally:
        await other.close()
    r = await delete
    assert (r.status_code, r.json()["code"]) == (409, "enrollment_has_records")
    assert len(await sql("SELECT 1 FROM payment WHERE enrollment_id = :e", e=added["id"])) == 1


async def test_bug_24_instructor_delete_keeps_a_student_enrolled_meanwhile(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    ins, cohort, _ = await _instructor_cohort(admin, login_as)
    theirs, _ = await past_cohort(admin, name="B")
    added = await _add(ins, cohort)
    other = await _open_tx(
        "INSERT INTO enrollment (cohort_id, student_id) VALUES (:c, :s)",
        c=theirs["id"],
        s=added["student_id"],
    )
    try:
        delete = asyncio.create_task(ins.delete(f"{E}/{added['id']}"))
        await asyncio.sleep(0.3)
        assert not delete.done()  # blocked on the student row
        await other.commit()
    finally:
        await other.close()
    assert (await delete).status_code == 204
    assert len(await sql("SELECT 1 FROM student WHERE id = :i", i=added["student_id"])) == 1


async def test_mark_or_grade_of_an_enrollment_removed_meanwhile_is_404_not_500(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    """The mark passed its checks, then the row was removed before its insert: 404."""
    ins, cohort, lessons = await _instructor_cohort(admin, login_as)
    for write in ("mark", "grade"):
        added = await _add(ins, cohort)
        remover = await _open_tx("SELECT 1 FROM enrollment WHERE id = :i FOR UPDATE", i=added["id"])
        try:
            call = (
                mark(ins, lessons[0], added["id"])
                if write == "mark"
                else ins.patch(
                    f"{E}/{added['id']}/grade",
                    json={"homework": 5},
                    headers={"X-Record-Version": "1"},
                )
            )
            task = asyncio.create_task(call)
            await asyncio.sleep(0.3)
            await remover.execute(text("DELETE FROM enrollment WHERE id = :i"), {"i": added["id"]})
            await remover.commit()
        finally:
            await remover.close()
        r = await task
        assert (r.status_code, r.json()["code"]) == (404, "not_found"), (write, r.text)


async def test_bug_24_instructor_cannot_set_branch_or_author_of_a_new_student(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    ins, cohort, _ = await _instructor_cohort(admin, login_as)
    url = f"{C}/{cohort['id']}/enrollments"
    spoof = {"branch_id": cohort["branch_id"], "created_by": cohort["id"]}
    for key, value in spoof.items():
        for payload in (
            {"new_student": {**NEW["new_student"], key: value}},
            {**NEW, key: value},
        ):
            r = await ins.post(url, json=payload)
            assert (r.status_code, r.json()["code"]) == (422, "validation_failed")
    both = {**NEW, "student_id": cohort["id"]}
    assert (await ins.post(url, json=both)).status_code == 422
    assert (await sql("SELECT count(*) FROM student"))[0][0] == 0
