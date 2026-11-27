"""Room archive: the API (rights, 409 with lessons ahead, 422 on assign, lists and board) and
migration 0036 (two cohorts moved out of import placeholders, placeholders archived)."""

import asyncio
import uuid
from datetime import timedelta
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.audit.sentences import Entry, sentence
from app.cohorts.status import today
from tests.conftest import SERVER_URL, TEST_DB, SignedIn, branch_id, make_role, sql
from tests.edu import C, body, make_cohort, make_course, make_room, next_monday

R = "/api/v1/rooms"


async def _archive(c: httpx.AsyncClient, room: uuid.UUID, on: bool = True) -> httpx.Response:
    return await c.patch(f"{R}/{room}", json={"archived": on})


async def _last_sentence(action: str) -> str:
    row = (
        await sql(
            "SELECT a.action, a.entity, a.label, a.diff, u.full_name FROM audit_log a "
            "LEFT JOIN app_user u ON u.id = a.user_id WHERE a.action = :a ORDER BY a.id DESC",
            a=action,
        )
    )[0]
    return sentence(Entry(row[4], row[0], row[1], row[2], row[3]))


async def test_archive_refused_while_lessons_ahead(admin: httpx.AsyncClient) -> None:
    course, room = await make_course(), await make_room()
    cohort = await make_cohort(admin, course, room)
    r = await _archive(admin, room)
    assert (r.status_code, r.json()["code"]) == (409, "room_has_future_lessons")
    assert r.json()["params"]["count"] > 0
    assert r.json()["errors"] == [{"loc": ["body", "archived"], "code": "room_has_future_lessons"}]
    # cancelled lessons ahead do not hold the room
    await sql("UPDATE lesson SET cancelled = true WHERE cohort_id = :c", c=cohort["id"])
    r = await _archive(admin, room)
    assert r.status_code == 200 and r.json()["archived"] is True
    assert "перенесена в архив аудитория Lovelace" in await _last_sentence("room.archive")
    r = await _archive(admin, room, on=False)
    assert r.status_code == 200 and r.json()["archived"] is False
    assert "возвращена из архива аудитория Lovelace" in await _last_sentence("room.unarchive")


async def test_archived_room_hidden_and_not_assignable(admin: httpx.AsyncClient) -> None:
    course = await make_course()
    live, old = await make_room(name="Turing"), await make_room(name="Без аудитории (G-001)")
    assert (await _archive(admin, old)).status_code == 200
    names = [r["name"] for r in (await admin.get(R)).json()]
    assert names == ["Turing"]
    every = (await admin.get(R, params={"include_archived": "true"})).json()
    assert [(r["name"], r["archived"]) for r in every] == [
        ("Turing", False),
        ("Без аудитории (G-001)", True),
    ]
    # a new cohort cannot take it
    r = await admin.post(C, json=body(course, old, branch_id=str(await branch_id("Душанбе"))))
    assert (r.status_code, r.json()["code"]) == (422, "room_archived")
    assert r.json()["errors"][0]["loc"] == ["body", "room_id"]
    # nor an existing one
    cohort = await make_cohort(admin, course, live)
    r = await admin.patch(f"{C}/{cohort['id']}", json={"room_id": str(old)})
    assert (r.status_code, r.json()["code"]) == (422, "room_archived")
    # nor a lesson ahead
    day = (next_monday() + timedelta(days=1)).isoformat()
    r = await admin.post(
        f"{C}/{cohort['id']}/lessons",
        json={"date": day, "start_time": "15:00", "end_time": "16:00", "room_id": str(old)},
    )
    assert (r.status_code, r.json()["code"]) == (422, "room_archived")
    # the board leaves it out while it holds nothing that week
    week = (await admin.get(f"{R}/schedule", params={"date_from": today().isoformat()})).json()
    assert [r["name"] for r in week["rooms"]] == ["Turing"]


async def test_cohort_in_archived_room_keeps_it_and_board_shows_history(
    admin: httpx.AsyncClient,
) -> None:
    course = await make_course()
    room = await make_room(name="Без аудитории (G-019)")
    start = next_monday(today() - timedelta(days=60))
    cohort = await make_cohort(admin, course, room, start=start, weeks=2)
    await sql("DELETE FROM lesson WHERE cohort_id = :c AND starts_at > now()", c=cohort["id"])
    assert (await _archive(admin, room)).status_code == 200
    # the cohort still shows its room, and saving it unchanged is fine
    detail = (await admin.get(f"{C}/{cohort['id']}")).json()
    assert detail["room_name"] == "Без аудитории (G-019)"
    r = await admin.patch(f"{C}/{cohort['id']}", json={"room_id": str(room), "capacity": 12})
    assert r.status_code == 200, r.text
    # its past week still shows the archived room on the board
    week = (await admin.get(f"{R}/schedule", params={"date_from": start.isoformat()})).json()
    assert [r["name"] for r in week["rooms"]] == ["Без аудитории (G-019)"]
    assert len(week["lessons"]) == 2


async def test_archive_rights(admin: httpx.AsyncClient, login_as: SignedIn) -> None:
    room = await make_room()
    other = await make_room(branch="Истаравшан", name="Истаравшан-1")
    viewer = await login_as("rv", await make_role("Просмотр", {"rooms": "view"}))
    r = await _archive(viewer, room)
    assert r.status_code == 403
    local = await login_as(
        "rl", await make_role("Аудитории", {"rooms": "change"}), branch="Душанбе"
    )
    assert (await _archive(local, other)).status_code == 404
    assert (await _archive(local, room)).status_code == 200
    teacher = await login_as("ri", "instructor")
    assert (await _archive(teacher, room, on=False)).status_code == 403


# ---- migration 0036 ------------------------------------------------------------------------


async def _lesson(
    conn: AsyncConnection, cohort: Any, room: Any, days: int, start: str, end: str
) -> None:
    await conn.execute(
        text(
            "INSERT INTO lesson (cohort_id, room_id, lesson_date, starts_at, ends_at) VALUES "
            "(:h, :r, CURRENT_DATE + CAST(:d AS integer), "
            "((CURRENT_DATE + CAST(:d AS integer)) + CAST(CAST(:s AS text) AS time)) AT TIME ZONE 'Asia/Dushanbe', "
            "((CURRENT_DATE + CAST(:d AS integer)) + CAST(CAST(:e AS text) AS time)) AT TIME ZONE 'Asia/Dushanbe')"
        ),
        {"h": cohort, "r": room, "d": days, "s": start, "e": end},
    )


async def _seed(conn: AsyncConnection, *, clash: bool = False) -> dict[str, Any]:
    branch = (await conn.execute(text("SELECT id FROM branch WHERE name = 'Душанбе'"))).scalar_one()
    course = (
        await conn.execute(
            text(
                "INSERT INTO course (name, default_price_month, duration_months, format) "
                "VALUES ('Python', 100, 3, 'offline') RETURNING id"
            )
        )
    ).scalar_one()
    rooms = {}
    for name in (
        "Lovelace",
        "Turing",
        "Без аудитории (G-015)",
        "Без аудитории (G-001)",
        "Без аудитории (G-003)",
        "Без аудитории (G-099)",
    ):
        rooms[name] = (
            await conn.execute(
                text(
                    "INSERT INTO room (branch_id, name, capacity) VALUES (:b, :n, 30) RETURNING id"
                ),
                {"b": branch, "n": name},
            )
        ).scalar_one()
    cohorts = {}
    for code, room, start in (
        ("G-190", "Без аудитории (G-015)", "09:00"),
        ("G-270", "Без аудитории (G-001)", "18:30"),
        ("G-178", "Без аудитории (G-003)", "12:00"),
        ("G-999", "Без аудитории (G-099)", "14:00"),
        ("G-263", "Turing", "15:00"),
    ):
        cohorts[code] = (
            await conn.execute(
                text(
                    "INSERT INTO cohort (code, course_id, branch_id, room_id, start_date, end_date, "
                    "weekdays, start_time, end_time, capacity, price_month, status) VALUES "
                    "(:c, :k, :b, :r, CURRENT_DATE - 30, CURRENT_DATE + 60, '{1}', "
                    "CAST(CAST(:s AS text) AS time), CAST(CAST(:s AS text) AS time) + interval '90 minutes', 10, 100, "
                    "'активный') RETURNING id"
                ),
                {"c": code, "k": course, "b": branch, "r": rooms[room], "s": start},
            )
        ).scalar_one()
    # past lessons in their placeholders, lessons ahead for the live cohorts
    for code, room, start, end in (
        ("G-190", "Без аудитории (G-015)", "09:00", "10:30"),
        ("G-270", "Без аудитории (G-001)", "18:30", "20:00"),
        ("G-178", "Без аудитории (G-003)", "12:00", "13:30"),
    ):
        for days in (-14, -7):
            await _lesson(conn, cohorts[code], rooms[room], days, start, end)
    for days in (7, 14, 21):
        await _lesson(
            conn, cohorts["G-190"], rooms["Без аудитории (G-015)"], days, "09:00", "10:30"
        )
        await _lesson(
            conn, cohorts["G-270"], rooms["Без аудитории (G-001)"], days, "18:30", "20:00"
        )
    await _lesson(conn, cohorts["G-999"], rooms["Без аудитории (G-099)"], 7, "14:00", "15:30")
    # Turing is busy next to G-270 (no overlap) or, for the clash case, at the same time
    await _lesson(conn, cohorts["G-263"], rooms["Turing"], 14, *(
        ("18:00", "19:00") if clash else ("15:00", "16:30")
    ))  # fmt: skip
    return {"rooms": rooms, "cohorts": cohorts}


async def _fresh(name: str) -> tuple[Config, Any]:
    url = SERVER_URL.set(database=name)
    server = create_async_engine(SERVER_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")
    async with server.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    await server.dispose()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url.render_as_string(hide_password=False))
    await asyncio.to_thread(command.upgrade, cfg, "0035")
    return cfg, create_async_engine(url)


async def test_migration_0036_moves_live_cohorts_and_archives_placeholders() -> None:
    cfg, engine = await _fresh(f"{TEST_DB}_mig_ra")
    try:
        async with engine.begin() as conn:
            ids = await _seed(conn)
        rooms, cohorts = ids["rooms"], ids["cohorts"]
        q = "SELECT id, cohort_id, room_id, starts_at FROM lesson ORDER BY id"
        async with engine.connect() as conn:
            before = {r[0]: r for r in (await conn.execute(text(q))).all()}
        await asyncio.to_thread(command.upgrade, cfg, "0036")
        async with engine.connect() as conn:
            after = {r[0]: r for r in (await conn.execute(text(q))).all()}
            cohort_rooms = dict(
                (await conn.execute(text("SELECT code, room_id FROM cohort"))).all()
            )
            archived = {
                n
                for (n,) in await conn.execute(
                    text("SELECT name FROM room WHERE archived_at IS NOT NULL")
                )
            }
            audit = (
                await conn.execute(text("SELECT action, label, user_id FROM audit_log ORDER BY id"))
            ).all()
            now = (await conn.execute(text("SELECT now()"))).scalar_one()
        assert set(after) == set(before)  # no lesson added or removed
        assert cohort_rooms["G-190"] == rooms["Lovelace"]
        assert cohort_rooms["G-270"] == rooms["Turing"]
        target = {cohorts["G-190"]: rooms["Lovelace"], cohorts["G-270"]: rooms["Turing"]}
        for lid, (_, cohort, room, starts) in after.items():
            if cohort in target and starts > now:
                assert room == target[cohort]
            else:
                assert room == before[lid][2]  # past lessons and other cohorts keep their room
        assert archived == {
            "Без аудитории (G-015)",
            "Без аудитории (G-001)",
            "Без аудитории (G-003)",
        }  # G-099 still has a lesson ahead
        assert sorted((a, lab) for a, lab, _ in audit) == sorted(
            [
                ("cohort.update", "G-190"),
                ("cohort.update", "G-270"),
                ("room.archive", "Без аудитории (G-015)"),
                ("room.archive", "Без аудитории (G-001)"),
                ("room.archive", "Без аудитории (G-003)"),
            ]
        )
        assert all(user is None for *_, user in audit)  # «Система»
        # down drops the column only; up again finds nothing left to move
        await asyncio.to_thread(command.downgrade, cfg, "0035")
        await asyncio.to_thread(command.upgrade, cfg, "0036")
        async with engine.connect() as conn:
            again = (
                await conn.execute(text("SELECT count(*) FROM room WHERE archived_at IS NOT NULL"))
            ).scalar_one()
        assert again == 3
    finally:
        await engine.dispose()


async def test_migration_0036_fails_on_overlap() -> None:
    cfg, engine = await _fresh(f"{TEST_DB}_mig_rb")
    try:
        async with engine.begin() as conn:
            await _seed(conn, clash=True)
        with pytest.raises(Exception, match="lesson_room_no_overlap"):
            await asyncio.to_thread(command.upgrade, cfg, "0036")
        async with engine.connect() as conn:
            head = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()
        assert head == "0035"  # rolled back as a whole
    finally:
        await engine.dispose()
