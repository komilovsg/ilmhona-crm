"""Stale cohorts: the nightly job closes an активный cohort with no attendance marks for
`stale_days` (boundaries, the manual finish logic reused), a finish frees the room (lessons ahead
without marks are cancelled, reopen restores them), the warning window and its list / dashboard /
cohort page agree with SQL, the setting is superadmin-only and audited."""

from datetime import date, timedelta
from typing import Any

import httpx

from app.cli import daily
from app.cohorts.status import today
from tests.conftest import SignedIn, make_role, sql
from tests.edu import C, body, make_cohort, make_course, make_room
from tests.money import enroll

SETTINGS = "/api/v1/academy-settings"
CARDS = "/api/v1/dashboard/cards"


async def stale_cohort(
    admin: httpx.AsyncClient,
    name: str,
    *,
    marked_ago: int | None = None,
    start_ago: int = 200,
    room: Any = None,
    students: tuple[str, ...] = ("Студент",),
) -> dict[str, Any]:
    """An активный cohort with a lesson every day, started `start_ago` days ago and running on
    for months. `marked_ago`: the day of its last marked lesson (None: nothing ever marked)."""
    cohort = await make_cohort(
        admin,
        await make_course(f"Курс {name}"),
        room or await make_room(name=f"R-{name}"),
        start=today() - timedelta(days=start_ago),
        weeks=60,
        weekdays=[1, 2, 3, 4, 5, 6, 7],
    )
    assert cohort["status"] == "активный"
    for student in students:
        enrollment = await enroll(admin, cohort, f"{name} {student}")
        if marked_ago is not None:
            await mark_on(cohort["id"], enrollment, today() - timedelta(days=marked_ago))
    return cohort


async def mark_on(cohort_id: str, enrollment: str, day: date) -> None:
    await sql(
        "INSERT INTO attendance (lesson_id, enrollment_id, present) "
        "SELECT id, :e, true FROM lesson WHERE cohort_id = :c AND lesson_date = :d",
        e=enrollment,
        c=cohort_id,
        d=day,
    )


async def status_of(cohort_id: str) -> str:
    return str((await sql("SELECT status FROM cohort WHERE id = :i", i=cohort_id))[0][0])


async def lessons_state(cohort_id: str) -> dict[str, tuple[int, int]]:
    """{'past'|'today'|'ahead': (live, cancelled)} lessons of a cohort."""
    rows = await sql(
        "SELECT CASE WHEN lesson_date < :t THEN 'past' WHEN lesson_date = :t THEN 'today' "
        "ELSE 'ahead' END, count(*) FILTER (WHERE NOT cancelled), count(*) FILTER (WHERE cancelled) "
        "FROM lesson WHERE cohort_id = :c GROUP BY 1",
        t=today(),
        c=cohort_id,
    )
    return {k: (int(a), int(b)) for k, a, b in rows}


async def reopen(c: httpx.AsyncClient, cohort_id: str) -> httpx.Response:
    version = (await c.get(f"{C}/{cohort_id}")).json()["version"]
    return await c.post(f"{C}/{cohort_id}/reopen", headers={"X-Record-Version": str(version)})


async def set_days(c: httpx.AsyncClient, days: int) -> httpx.Response:
    version = (await c.get(SETTINGS)).json()["version"]
    return await c.patch(
        SETTINGS, json={"stale_days": days}, headers={"X-Record-Version": str(version)}
    )


# ---- the nightly close ------------------------------------------------------------------


async def test_auto_close_boundaries_and_idempotent_job(admin: httpx.AsyncClient) -> None:
    n = 60
    last_59 = await stale_cohort(admin, "A", marked_ago=n - 1)
    last_60 = await stale_cohort(admin, "B", marked_ago=n)
    never_59 = await stale_cohort(admin, "C", start_ago=n - 1)
    never_60 = await stale_cohort(admin, "D", start_ago=n)
    recruiting = await make_cohort(
        admin,
        await make_course("Е"),
        await make_room(name="R-E"),
        start=today() + timedelta(days=9),
    )
    assert await daily() == 2
    assert [await status_of(c["id"]) for c in (last_59, last_60, never_59, never_60)] == [
        "активный",
        "завершён",
        "активный",
        "завершён",
    ]
    assert await status_of(recruiting["id"]) == "набор"
    assert await daily() == 0  # nothing left to close
    log = (await admin.get("/api/v1/audit", params={"action": "cohort.auto_close"})).json()
    assert log["total"] == 2
    texts = {i["text"] for i in log["items"]}
    assert any(
        f"поток {last_60['code']} закрыт автоматически: нет отметок 60 дней" in t for t in texts
    )
    assert all(t.startswith("Система: поток") for t in texts)


async def test_auto_close_uses_the_manual_finish_rules(admin: httpx.AsyncClient) -> None:
    cohort = await stale_cohort(admin, "F", marked_ago=70, students=("Первый", "Второй"))
    gone = await enroll(admin, cohort, "Отчисленный")
    await admin.patch(f"/api/v1/enrollments/{gone}", json={"status": "отчислен"})
    await daily()
    got = {
        e["student_name"]: e["status"]
        for e in (await admin.get(f"{C}/{cohort['id']}/enrollments")).json()
    }
    assert got == {"F Первый": "завершил", "F Второй": "завершил", "Отчисленный": "отчислен"}
    # the same restore as after a manual finish
    assert (await reopen(admin, cohort["id"])).status_code == 200
    got = {
        e["student_name"]: e["status"]
        for e in (await admin.get(f"{C}/{cohort['id']}/enrollments")).json()
    }
    assert set(got.values()) == {"активный", "отчислен"}


async def test_other_statuses_are_untouched(admin: httpx.AsyncClient) -> None:
    done = await stale_cohort(admin, "G", marked_ago=100)
    cancelled = await stale_cohort(admin, "H", marked_ago=100)
    await sql("UPDATE cohort SET status = 'завершён' WHERE id = :i", i=done["id"])
    await sql("UPDATE cohort SET status = 'отменён' WHERE id = :i", i=cancelled["id"])
    assert await daily() == 0
    assert [await status_of(c["id"]) for c in (done, cancelled)] == ["завершён", "отменён"]


async def test_setting_moves_the_boundary(admin: httpx.AsyncClient) -> None:
    cohort = await stale_cohort(admin, "I", marked_ago=70)
    assert (await set_days(admin, 90)).status_code == 200
    assert await daily() == 0
    assert (await set_days(admin, 70)).status_code == 200
    assert await daily() == 1
    assert await status_of(cohort["id"]) == "завершён"


# ---- lessons freed by a finish ----------------------------------------------------------


async def test_finish_cancels_only_future_unmarked_lessons(admin: httpx.AsyncClient) -> None:
    cohort = await stale_cohort(admin, "J", marked_ago=5)
    enrollment = (await sql("SELECT id FROM enrollment WHERE cohort_id = :c", c=cohort["id"]))[0][0]
    marked_ahead = today() + timedelta(days=5)
    await mark_on(cohort["id"], enrollment, marked_ahead)
    before = await lessons_state(cohort["id"])
    assert before["today"] == (1, 0) and before["past"][1] == 0
    pv = (await admin.get(f"{C}/{cohort['id']}/finish-preview")).json()
    assert pv["lessons_to_free"] == before["ahead"][0] - 1
    version = (await admin.get(f"{C}/{cohort['id']}")).json()["version"]
    r = await admin.post(
        f"{C}/{cohort['id']}/finish",
        json={"graduates": pv["graduates"], "completed": pv["completed"]},
        headers={"X-Record-Version": str(version)},
    )
    assert r.status_code == 200, r.text
    after = await lessons_state(cohort["id"])
    assert after["past"] == before["past"]  # held lessons stay
    assert after["today"] == (1, 0)  # the finish day itself stays
    assert after["ahead"] == (1, before["ahead"][0] - 1)  # only the marked one is left
    kept = await sql(
        "SELECT lesson_date FROM lesson WHERE cohort_id = :c AND NOT cancelled AND lesson_date > :t",
        c=cohort["id"],
        t=today(),
    )
    assert [r[0] for r in kept] == [marked_ahead]


async def test_finish_frees_the_room_and_reopen_restores_the_lessons(
    admin: httpx.AsyncClient,
) -> None:
    room = await make_room(name="Общая")
    cohort = await stale_cohort(admin, "K", marked_ago=61, room=room)
    other_course = await make_course("Другой")
    slot = today() + timedelta(days=10)

    async def book() -> httpx.Response:
        return await admin.post(
            C,
            json=body(
                other_course,
                room,
                start=slot,
                weeks=1,
                weekdays=[slot.isoweekday()],
                branch_id=cohort["branch_id"],
            ),
        )

    assert (await book()).json()["code"] == "room_busy"
    pv = (await admin.get(f"{C}/{cohort['id']}/finish-preview")).json()
    ahead = (await lessons_state(cohort["id"]))["ahead"][0]
    assert pv["lessons_to_free"] == ahead and ahead > 0
    version = (await admin.get(f"{C}/{cohort['id']}")).json()["version"]
    r = await admin.post(
        f"{C}/{cohort['id']}/finish",
        json={"graduates": pv["graduates"], "completed": pv["completed"]},
        headers={"X-Record-Version": str(version)},
    )
    assert r.status_code == 200, r.text
    assert (await lessons_state(cohort["id"]))["ahead"] == (0, ahead)
    log = (await admin.get("/api/v1/audit", params={"action": "cohort.finish"})).json()
    assert f"отменено уроков: {ahead}" in log["items"][0]["text"]
    # the slot is free for another cohort now
    booked = await book()
    assert booked.status_code == 201, booked.text
    assert (await admin.delete(f"{C}/{booked.json()['id']}")).status_code == 204
    # reopen: exactly the finish's lessons are back
    r = await reopen(admin, cohort["id"])
    assert (r.status_code, r.json()["lessons_busy"]) == (200, [])
    assert (await lessons_state(cohort["id"]))["ahead"] == (ahead, 0)
    assert (await sql("SELECT count(*) FROM lesson WHERE cancelled_by_finish"))[0][0] == 0


async def test_reopen_leaves_lessons_whose_slot_was_taken(admin: httpx.AsyncClient) -> None:
    room = await make_room(name="Занятая")
    cohort = await stale_cohort(admin, "L", marked_ago=61, room=room)
    manual = today() + timedelta(days=3)  # a lesson cancelled by hand stays cancelled
    await sql(
        "UPDATE lesson SET cancelled = true WHERE cohort_id = :c AND lesson_date = :d",
        c=cohort["id"],
        d=manual,
    )
    await daily()
    ahead = (await lessons_state(cohort["id"]))["ahead"]
    slot = today() + timedelta(days=10)
    taken = await admin.post(
        C,
        json=body(
            await make_course("Новый"),
            room,
            start=slot,
            weeks=1,
            weekdays=[slot.isoweekday()],
            branch_id=cohort["branch_id"],
        ),
    )
    assert taken.status_code == 201, taken.text
    r = await reopen(admin, cohort["id"])
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["status"] == "активный"
    taken_dates = sorted(
        r[0]
        for r in await sql(
            "SELECT lesson_date FROM lesson WHERE cohort_id = :c", c=taken.json()["id"]
        )
    )
    assert len(taken_dates) == 2
    assert [(b["date"], b["reason"]) for b in got["lessons_busy"]] == [
        (d.isoformat(), "аудитория занята") for d in taken_dates
    ]
    state = (await lessons_state(cohort["id"]))["ahead"]
    assert state == (ahead[1] - 1 - 2, 1 + 2)  # the manual one and the two busy ones stay
    assert (await sql("SELECT count(*) FROM lesson WHERE cancelled_by_finish"))[0][0] == 0
    log = (await admin.get("/api/v1/audit", params={"action": "cohort.reopen"})).json()
    assert "не возвращено (аудитория занята): 2" in log["items"][0]["text"]


# ---- the warning ------------------------------------------------------------------------


async def test_warning_list_filter_and_dashboard_match_sql(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    n, warn = 60, 15
    cohorts = {
        ago: await stale_cohort(admin, f"W{ago}", start_ago=ago)
        for ago in (n - warn - 1, n - warn, n - 1)
    }
    await stale_cohort(admin, "OK", marked_ago=3)
    expected = {
        str(i)
        for (i,) in await sql(
            "SELECT id FROM cohort WHERE status = 'активный' AND "
            "COALESCE((SELECT max(l.lesson_date) FROM lesson l JOIN attendance a "
            "ON a.lesson_id = l.id WHERE l.cohort_id = cohort.id), start_date) "
            "<= CAST(:t AS date) - CAST(:lo AS int) AND COALESCE((SELECT max(l.lesson_date) FROM lesson l JOIN attendance a "
            "ON a.lesson_id = l.id WHERE l.cohort_id = cohort.id), start_date) > CAST(:t AS date) - CAST(:hi AS int)",
            t=today(),
            lo=n - warn,
            hi=n,
        )
    }
    assert expected == {cohorts[n - warn]["id"], cohorts[n - 1]["id"]}
    listed = (await admin.get(C, params={"closing": "true"})).json()
    assert {i["id"] for i in listed["items"]} == expected and listed["total"] == 2
    # the cohort page and the list carry the same message data
    for ago in (n - warn, n - 1):
        c = (await admin.get(f"{C}/{cohorts[ago]['id']}")).json()
        assert c["stale"] == {
            "idle_days": ago,
            "closes_on": (today() + timedelta(days=n - ago)).isoformat(),
        }
    assert (await admin.get(f"{C}/{cohorts[n - warn - 1]['id']}")).json()["stale"] is None
    alerts = (await admin.get(f"{CARDS}/attention")).json()["items"]
    closing = next(a for a in alerts if a["key"] == "closing")
    assert "2 потока скоро закроются" in closing["title"]
    tiles = {t["key"]: t for t in (await admin.get(f"{CARDS}/queues")).json()["tiles"]}
    assert tiles["closing_cohorts"]["count"] == 2
    # a manager sees the tile too
    role = await make_role("Менеджер потоков", {"dashboard": "view", "cohorts": "view", "leads": "view"})
    mgr = await login_as("mia", role, branch="Душанбе")
    tiles = {t["key"]: t for t in (await mgr.get(f"{CARDS}/queues")).json()["tiles"]}
    assert tiles["closing_cohorts"]["count"] == 2


async def test_warning_is_absent_for_other_statuses(admin: httpx.AsyncClient) -> None:
    c = await stale_cohort(admin, "X", start_ago=50)
    await sql("UPDATE cohort SET status = 'завершён' WHERE id = :i", i=c["id"])
    assert (await admin.get(f"{C}/{c['id']}")).json()["stale"] is None
    assert (await admin.get(C, params={"closing": "true"})).json()["total"] == 0


# ---- the setting ------------------------------------------------------------------------


async def test_setting_is_superadmin_only_versioned_and_audited(
    admin: httpx.AsyncClient, login_as: SignedIn
) -> None:
    role = await make_role("Менеджер Т", {"cohorts": "change", "dashboard": "view"})
    mgr = await login_as("mia", role, branch="Душанбе")
    seen = (await mgr.get(SETTINGS)).json()
    assert (seen["stale_days"], seen["can_edit"]) == (60, False)
    r = await mgr.patch(SETTINGS, json={"stale_days": 90}, headers={"X-Record-Version": "1"})
    assert r.status_code == 403
    got = (await admin.get(SETTINGS)).json()
    assert (got["stale_days"], got["can_edit"], got["warn_days"]) == (60, True, 15)
    for bad in (19, 731, "x"):
        assert (await set_days(admin, bad)).status_code == 422  # type: ignore[arg-type]
    r = await admin.patch(SETTINGS, json={"stale_days": 90}, headers={"X-Record-Version": "99"})
    assert (r.status_code, r.json()["code"]) == (409, "stale_version")
    assert (await set_days(admin, 90)).json()["stale_days"] == 90
    log = (await admin.get("/api/v1/audit", params={"action": "academy_settings.update"})).json()
    assert log["total"] == 1
    assert (
        "изменены настройки академии: автозакрытие потоков без отметок, дней 60 → 90"
        in (log["items"][0]["text"])
    )
    # the same value again writes nothing
    await set_days(admin, 90)
    log = (await admin.get("/api/v1/audit", params={"action": "academy_settings.update"})).json()
    assert log["total"] == 1
