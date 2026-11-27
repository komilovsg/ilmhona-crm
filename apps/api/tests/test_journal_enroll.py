"""Journal import: names that are not in the group get written into it (through the cohort page's
enrollment), then their marks import too."""

from typing import Any

import httpx

from tests.conftest import SignedIn, sql
from tests.edu import C, make_student
from tests.journal_fixture import journal_xlsx
from tests.test_attendance import enroll, past_cohort
from tests.test_journal_import import days, send, short

NAMES = [f"Студентов{chr(1040 + i)} Имя{chr(1040 + i)}" for i in range(24)]


def file_of(ds: list[Any], names: list[str]) -> bytes:
    return journal_xlsx(short(ds[:3]), [(n, ["б", "н", "у"], False) for n in names])


async def test_24_names_into_a_20_student_cohort_all_end_up_in_the_group(
    admin: httpx.AsyncClient,
) -> None:
    cohort, _ = await past_cohort(admin)
    await sql("UPDATE cohort SET capacity = 20")
    for n in NAMES[:20]:
        await enroll(admin, cohort, n)
    # one of the missing four exists as a student already (same spelling), three are new
    known = await make_student(NAMES[20])
    ds = await days(admin, cohort)
    data = file_of(ds, NAMES)
    body = (await send(admin, cohort, "preview", data)).json()
    assert body["can_enroll"] is True
    assert [u["name"] for u in body["unmatched"]] == NAMES[20:]
    first = body["unmatched"][0]
    assert first["options"][0]["student_id"] == str(known)
    assert first["options"][0]["tier"] == "exact"
    assert all(u["options"] == [] for u in body["unmatched"][1:])
    assert first["first_date"] == ds[0].isoformat()

    url = f"{C}/{cohort['id']}/attendance/import/enroll"
    r = await admin.post(url, json={"student_id": str(known), "first_date": first["first_date"]})
    assert r.status_code == 201, r.text
    assert r.json()["over_capacity"] == {"enrolled": 21, "capacity": 20}
    for i, u in enumerate(body["unmatched"][1:], start=22):
        r = await admin.post(
            url,
            json={"new_student": {"full_name": u["name"]}, "first_date": u["first_date"]},
        )
        assert r.status_code == 201, r.text
        assert r.json()["over_capacity"] == {"enrolled": i, "capacity": 20}

    again = (await send(admin, cohort, "preview", data)).json()
    assert again["unmatched"] == []
    assert again["counts"]["unmatched"] == 0
    applied = await send(admin, cohort, "apply", data)
    assert applied.status_code == 200, applied.text
    grid = (await admin.get(f"{C}/{cohort['id']}/attendance")).json()
    assert len(grid["students"]) == 24
    # every one of the 24 got the three marks from the file, the new four from their first day
    assert all(len(s["marks"]) == 3 for s in grid["students"])
    log = (await admin.get("/api/v1/audit", params={"action": "enrollment.create"})).json()
    assert log["total"] >= 24


async def test_an_instructor_cannot_enroll_and_sees_no_options(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    ins = await login_as("ins", "instructor", branch="Душанбе")
    me = (await ins.get("/api/v1/auth/me")).json()["id"]
    cohort, _ = await past_cohort(admin, instructor_id=me)
    await enroll(admin, cohort, NAMES[0])
    known = await make_student(NAMES[1])
    data = file_of(await days(admin, cohort), NAMES[:2])
    body = (await send(ins, cohort, "preview", data)).json()
    assert body["can_enroll"] is False
    assert [u["name"] for u in body["unmatched"]] == [NAMES[1]]
    assert body["unmatched"][0]["options"] == []
    url = f"{C}/{cohort['id']}/attendance/import/enroll"
    for payload in ({"student_id": str(known)}, {"new_student": {"full_name": "Новый Нур"}}):
        r = await ins.post(url, json=payload)
        assert (r.status_code, r.json()["code"]) == (403, "forbidden")
    assert (await sql("SELECT count(*) FROM enrollment"))[0][0] == 1


async def test_a_student_of_another_branch_is_not_offered_nor_enrolled(
    admin: httpx.AsyncClient,
) -> None:
    cohort, _ = await past_cohort(admin)
    await enroll(admin, cohort, NAMES[0])
    foreign = await make_student(NAMES[1], branch="Истаравшан")
    data = file_of(await days(admin, cohort), NAMES[:2])
    body = (await send(admin, cohort, "preview", data)).json()
    assert body["unmatched"][0]["options"] == []
    r = await admin.post(
        f"{C}/{cohort['id']}/attendance/import/enroll", json={"student_id": str(foreign)}
    )
    assert (r.status_code, r.json()["code"]) == (422, "student_branch_mismatch")
