"""Manual cohort finish: no finish by date («Срок вышел»), preview == result, locks on the
counts, early finish, rights, reopen (exact restore, superadmin, no certificates), debt and
certificates unchanged, the list filter and the dashboard counter."""

from datetime import date, timedelta
from typing import Any

import httpx

from app.cli import daily
from app.cohorts.status import today
from tests.conftest import SignedIn, make_role, sql
from tests.edu import C, finish_overdue, make_cohort, make_course, make_room
from tests.money import enroll, running_cohort
from tests.reports import G, grade
from tests.test_attendance import E

Q = "/api/v1/dashboard/cards"
STUDENTS = {"Первый": (40, 35), "Второй": (10, 10), "Третий": (30, 40)}


async def overdue_cohort(
    admin: httpx.AsyncClient,
    students: dict[str, tuple[int, int]],
    *,
    name: str = "F",
    branch: str = "Душанбе",
    ended_days_ago: int = 1,
) -> tuple[dict[str, Any], dict[str, str]]:
    """An активный cohort whose end date passed, with graded students {name: (homework, final)}."""
    cohort = await make_cohort(
        admin,
        await make_course(f"Курс {name}"),
        await make_room(branch, f"R-{name}"),
        branch=branch,
        start=today() - timedelta(days=20),
        weeks=8,
    )
    ids = {}
    for student, (homework, final) in students.items():
        ids[student] = await enroll(admin, cohort, student, branch=branch)
        await grade(admin, ids[student], homework, final)
    await sql(
        "UPDATE cohort SET end_date = :e WHERE id = :i",
        e=today() - timedelta(days=ended_days_ago),
        i=cohort["id"],
    )
    return cohort, ids


async def finish(
    c: httpx.AsyncClient, cohort_id: str, graduates: int, completed: int
) -> httpx.Response:
    version = (await c.get(f"{C}/{cohort_id}")).json()["version"]
    return await c.post(
        f"{C}/{cohort_id}/finish",
        json={"graduates": graduates, "completed": completed},
        headers={"X-Record-Version": str(version)},
    )


async def reopen(c: httpx.AsyncClient, cohort_id: str) -> httpx.Response:
    version = (await c.get(f"{C}/{cohort_id}")).json()["version"]
    return await c.post(f"{C}/{cohort_id}/reopen", headers={"X-Record-Version": str(version)})


async def statuses() -> dict[str, str]:
    return {str(i): s for i, s in await sql("SELECT id, status FROM enrollment")}


async def test_nightly_job_leaves_an_overdue_cohort_active(admin: httpx.AsyncClient) -> None:
    cohort, _ = await overdue_cohort(admin, STUDENTS, ended_days_ago=8)
    assert await daily() == 0
    got = (await admin.get(f"{C}/{cohort['id']}")).json()
    assert (got["status"], got["overdue"]) == ("активный", True)
    assert set((await statuses()).values()) == {"активный"}
    # a cohort that ends today is not overdue yet
    today_cohort, _ = await overdue_cohort(admin, {"А": (1, 1)}, name="T", ended_days_ago=0)
    assert (await admin.get(f"{C}/{today_cohort['id']}")).json()["overdue"] is False


async def test_recruiting_to_active_by_start_date_stays_automatic(
    admin: httpx.AsyncClient,
) -> None:
    course, room = await make_course(), await make_room()
    started = await make_cohort(admin, course, room, start=today() + timedelta(days=3), weeks=4)
    assert started["status"] == "набор"
    await sql("UPDATE cohort SET start_date = :s", s=today() - timedelta(days=1))
    assert await daily() == 1
    assert (await admin.get(f"{C}/{started['id']}")).json()["status"] == "активный"


async def test_finish_preview_equals_the_result_and_is_audited(admin: httpx.AsyncClient) -> None:
    cohort, ids = await overdue_cohort(admin, STUDENTS)
    gone = await enroll(admin, cohort, "Отчисленный")
    await admin.patch(f"{E}/{gone}", json={"status": "отчислен"})
    r = await admin.get(f"{C}/{cohort['id']}/finish-preview")
    assert r.status_code == 200, r.text
    pv = r.json()
    counts = (pv["graduates"], pv["completed"], pv["excluded_count"], pv["overdue"])
    assert counts == (2, 1, 1, True)
    names = {k: [i["student_name"] for i in v] for k, v in pv["lists"].items()}
    assert names == {
        "graduates": ["Первый", "Третий"],
        "completed": ["Второй"],
        "excluded": ["Отчисленный"],
    }
    assert (await sql("SELECT status FROM cohort WHERE id = :i", i=cohort["id"]))[0][
        0
    ] == "активный"
    r = await finish(admin, cohort["id"], pv["graduates"], pv["completed"])
    assert (r.status_code, r.json()["status"]) == (200, "завершён"), r.text
    assert {
        e["student_name"]: e["status"]
        for e in (await admin.get(f"{C}/{cohort['id']}/enrollments")).json()
    } == {
        "Первый": "выпускник",
        "Второй": "завершил",
        "Третий": "выпускник",
        "Отчисленный": "отчислен",
    }
    assert {i["enrollment_id"] for i in pv["lists"]["graduates"]} == {ids["Первый"], ids["Третий"]}
    log = (await admin.get("/api/v1/audit", params={"action": "cohort.finish"})).json()
    assert log["total"] == 1
    assert f"завершил поток {cohort['code']}: выпускников 2, завершили 1" in log["items"][0]["text"]
    # a finished cohort no longer previews or finishes
    r = await admin.get(f"{C}/{cohort['id']}/finish-preview")
    assert (r.status_code, r.json()["code"]) == (409, "cohort_not_active")
    assert (await finish(admin, cohort["id"], 0, 0)).json()["code"] == "cohort_not_active"


async def test_finish_with_changed_counts_is_409_with_a_fresh_preview(
    admin: httpx.AsyncClient,
) -> None:
    cohort, ids = await overdue_cohort(admin, STUDENTS)
    # a grade changed after the preview was shown: Второй now passes
    await grade(admin, ids["Второй"], 40, 40)
    r = await finish(admin, cohort["id"], 2, 1)
    body = r.json()
    assert (r.status_code, body["code"]) == (409, "finish_changed"), r.text
    fresh = body["params"]["preview"]
    assert (fresh["graduates"], fresh["completed"]) == (3, 0)
    assert (await sql("SELECT status FROM cohort WHERE id = :i", i=cohort["id"]))[0][
        0
    ] == "активный"
    assert set((await statuses()).values()) == {"активный"}
    assert (await finish(admin, cohort["id"], 3, 0)).status_code == 200


async def test_stale_record_version_is_refused(admin: httpx.AsyncClient) -> None:
    cohort, _ = await overdue_cohort(admin, STUDENTS)
    r = await admin.post(
        f"{C}/{cohort['id']}/finish",
        json={"graduates": 2, "completed": 1},
        headers={"X-Record-Version": "0"},
    )
    assert (r.status_code, r.json()["code"]) == (409, "stale_version")


async def test_a_cohort_can_be_finished_before_its_end_date(admin: httpx.AsyncClient) -> None:
    cohort, _ = await overdue_cohort(admin, STUDENTS)
    await sql("UPDATE cohort SET end_date = :e", e=today() + timedelta(days=30))
    pv = (await admin.get(f"{C}/{cohort['id']}/finish-preview")).json()
    assert pv["overdue"] is False
    r = await finish(admin, cohort["id"], pv["graduates"], pv["completed"])
    assert (r.status_code, r.json()["status"], r.json()["overdue"]) == (200, "завершён", False)


async def test_finish_rights_and_scope(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    cohort, _ = await overdue_cohort(admin, STUDENTS)
    own = await login_as("own", "manager", branch="Душанбе")
    other = await login_as("other", "manager", branch="Истаравшан")
    ins = await login_as("ins", "instructor", branch="Душанбе")
    viewer = await login_as(
        "view", await make_role("Просмотр потоков", {"cohorts": "view"}), branch="Душанбе"
    )
    for c, code in ((ins, 403), (viewer, 403), (other, 404)):
        r = await c.get(f"{C}/{cohort['id']}/finish-preview")
        assert r.status_code == code, (code, r.text)
        r = await c.post(
            f"{C}/{cohort['id']}/finish",
            json={"graduates": 2, "completed": 1},
            headers={"X-Record-Version": "1"},
        )
        assert r.status_code == code, (code, r.text)
    assert (await sql("SELECT status FROM cohort"))[0][0] == "активный"
    assert (await own.get(f"{C}/{cohort['id']}/finish-preview")).status_code == 200
    assert (await finish(own, cohort["id"], 2, 1)).status_code == 200
    # the superadmin finishes any branch
    second, _ = await overdue_cohort(admin, {"Х": (40, 40)}, name="S", branch="Истаравшан")
    assert (await finish(admin, second["id"], 1, 0)).status_code == 200


async def test_reopen_restores_every_status_exactly(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    cohort, _ = await overdue_cohort(admin, STUDENTS)
    gone = await enroll(admin, cohort, "Отчисленный")
    await admin.patch(f"{E}/{gone}", json={"status": "отчислен"})
    before = await statuses()
    assert (await finish(admin, cohort["id"], 2, 1)).status_code == 200
    after = await statuses()
    assert after != before
    manager = await login_as("mgr", "manager", branch="Душанбе")
    r = await reopen(manager, cohort["id"])
    assert (r.status_code, r.json()["code"]) == (403, "forbidden")
    assert await statuses() == after
    r = await reopen(admin, cohort["id"])
    assert (r.status_code, r.json()["status"], r.json()["overdue"]) == (200, "активный", True)
    assert await statuses() == before
    assert not await sql("SELECT 1 FROM enrollment WHERE status_before_finish IS NOT NULL")
    log = (await admin.get("/api/v1/audit", params={"action": "cohort.reopen"})).json()
    text = log["items"][0]["text"]
    assert f"вернул поток {cohort['code']} в активные, статусов студентов восстановлено: 3" in text
    # not finished -> nothing to reopen; and it can be finished again
    r = await reopen(admin, cohort["id"])
    assert (r.status_code, r.json()["code"]) == (409, "cohort_not_done")
    assert (await finish(admin, cohort["id"], 2, 1)).status_code == 200


async def test_reopen_is_refused_after_a_certificate(admin: httpx.AsyncClient) -> None:
    cohort, ids = await overdue_cohort(admin, STUDENTS)
    assert (await finish(admin, cohort["id"], 2, 1)).status_code == 200
    assert (await admin.post(f"{G}/{ids['Первый']}/certificate")).status_code == 200
    r = await reopen(admin, cohort["id"])
    assert (r.status_code, r.json()["code"]) == (409, "certificate_issued")
    assert (await sql("SELECT status FROM cohort"))[0][0] == "завершён"
    assert (await statuses())[ids["Первый"]] == "выпускник"


async def test_certificates_only_after_the_finish(admin: httpx.AsyncClient) -> None:
    cohort, ids = await overdue_cohort(admin, STUDENTS)
    r = await admin.post(f"{G}/{ids['Первый']}/certificate")
    assert (r.status_code, r.json()["code"]) == (409, "not_graduate")  # still активный
    assert (await finish(admin, cohort["id"], 2, 1)).status_code == 200
    assert (await admin.post(f"{G}/{ids['Первый']}/certificate")).status_code == 200


async def test_already_finished_cohorts_are_untouched_by_the_job(admin: httpx.AsyncClient) -> None:
    cohort, _ = await overdue_cohort(admin, STUDENTS)
    assert await finish_overdue() == 1
    before = await statuses()
    assert await daily() == 0
    assert await daily(today() + timedelta(days=400)) == 0
    # moving the dates of a finished cohort does not reopen it either
    version = (await admin.get(f"{C}/{cohort['id']}")).json()["version"]
    r = await admin.patch(
        f"{C}/{cohort['id']}",
        json={"end_date": (today() + timedelta(days=90)).isoformat()},
        headers={"X-Record-Version": str(version)},
    )
    assert (r.status_code, r.json()["status"]) == (200, "завершён")
    assert await statuses() == before


async def test_an_overdue_cohort_adds_no_debt_beyond_its_months(admin: httpx.AsyncClient) -> None:
    cohort = await running_cohort(admin, back=4, weeks=5, price=500)
    await enroll(admin, cohort, "Должник")
    assert (await sql("SELECT status FROM cohort"))[0][0] == "активный"
    assert date.fromisoformat(cohort["end_date"]) < today()  # overdue, not finished
    assert await daily() == 0
    rows = (await admin.get("/api/v1/payments/debtors")).json()
    assert rows["total"] == 1
    # only the months up to the end date are owed, however long it stays unfinished
    assert rows["total_debt"] == f"{cohort['months'] * 500}.00"


async def test_overdue_filter_and_dashboard_counter_match_sql(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    a, _ = await overdue_cohort(admin, STUDENTS, name="A", ended_days_ago=3)
    b, _ = await overdue_cohort(admin, {"Б": (1, 1)}, name="B", branch="Истаравшан")
    await overdue_cohort(admin, {"В": (1, 1)}, name="C", ended_days_ago=0)  # ends today
    finished, _ = await overdue_cohort(admin, {"Г": (1, 1)}, name="D")
    assert (await finish(admin, finished["id"], 0, 1)).status_code == 200
    rows = await sql(
        "SELECT count(*) FROM cohort WHERE status = 'активный' AND end_date < :t", t=today()
    )
    n = rows[0][0]
    assert n == 2
    r = (await admin.get(C, params={"overdue": "true"})).json()
    assert r["total"] == n and {i["id"] for i in r["items"]} == {a["id"], b["id"]}
    assert all(i["overdue"] for i in r["items"])
    assert (await admin.get(C)).json()["total"] == 4
    # the filter keeps the branch scope; the export takes the same filter
    own = await login_as("own", "manager", branch="Душанбе")
    r = (await own.get(C, params={"overdue": "true"})).json()
    assert {i["id"] for i in r["items"]} == {a["id"]}
    assert (await admin.get(f"{C}/export", params={"overdue": "true"})).status_code == 200
    # counter: leadership alert and manager tile, with the filter link
    items = (await admin.get(f"{Q}/attention")).json()["items"]
    alert = next(i for i in items if i["key"] == "overdue")
    assert alert["title"].startswith(f"{n} потока") and alert["href"] == "/cohorts?overdue=1"
    tiles = {t["key"]: t for t in (await own.get(f"{Q}/queues")).json()["tiles"]}
    assert tiles["overdue_cohorts"]["count"] == 1
    tiles = {t["key"]: t for t in (await admin.get(f"{Q}/queues")).json()["tiles"]}
    assert tiles["overdue_cohorts"]["count"] == n
