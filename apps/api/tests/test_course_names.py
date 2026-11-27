"""A course name holds no intake date (the cohort title shows it): the pattern, the 422 on create
and edit, and migration 0033 that cleans the names and merges the dated duplicates."""

import asyncio
import uuid
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.audit.sentences import Entry, sentence
from app.education.course_names import has_date, without_date
from tests.conftest import SERVER_URL, TEST_DB


@pytest.mark.parametrize(
    ("name", "clean"),
    [
        ("Программирование (23 янв)", "Программирование"),
        ("Программирование (23 янв.)", "Программирование"),
        ("Программирование  (1 января 2026)", "Программирование"),
        ("Дизайн (5 мая)", "Дизайн"),
        ("Дизайн (5 май 2025 г.)", "Дизайн"),
        ("Английский (12 Сент)", "Английский"),
        ("Английский (12 сентября)", "Английский"),
        ("SMM (3 дек 25)", "SMM"),
        ("SMM (03.12)", "SMM"),
        ("SMM (03.12.25)", "SMM"),
        ("SMM (03.12.2025) ", "SMM"),
        ("Python (базовый) (10 мар)", "Python (базовый)"),
        ("  Веб   дизайн (10мар)", "Веб дизайн"),
    ],
)
def test_trailing_date_is_cut(name: str, clean: str) -> None:
    assert has_date(name)
    assert without_date(name) == clean


@pytest.mark.parametrize(
    "name",
    [
        "Python (базовый)",
        "Python (3.11)",
        "Python (3.10)",
        "Excel (2 уровень)",
        "Программирование (23 янв) продвинутый",
        "Курс 23 янв",
        "Март (весна)",
        "SMM (32.01)",
        "SMM (12.13)",
        "Робототехника (дети 7-10)",
    ],
)
def test_other_brackets_stay(name: str) -> None:
    assert not has_date(name)


async def test_course_name_with_a_date_is_rejected(admin: httpx.AsyncClient) -> None:
    body = {"name": "Программирование (23 янв)", "duration_months": 3, "format": "offline"}
    r = await admin.post("/api/v1/courses", json=body)
    assert (r.status_code, r.json()["code"]) == (422, "course_name_has_date")
    assert r.json()["errors"] == [{"loc": ["body", "name"], "code": "course_name_has_date"}]
    r = await admin.post("/api/v1/courses", json={**body, "name": "Python (базовый)"})
    assert r.status_code == 201
    course = r.json()
    r = await admin.patch(
        f"/api/v1/courses/{course['id']}",
        json={"name": "Python (01.02)"},
        headers={"X-Record-Version": str(course["version"])},
    )
    assert (r.status_code, r.json()["code"]) == (422, "course_name_has_date")


def test_merge_sentence() -> None:
    e = Entry(
        actor=None,
        action="course.merge",
        entity="course",
        label="Программирование (23 янв)",
        diff={"into": [None, "Программирование"], "cohorts": [None, 2], "leads": [None, 1]},
    )
    assert sentence(e) == (
        "Система: курс Программирование (23 янв) объединён с курсом Программирование — "
        "перенесено: 2 потока, 1 лид"
    )


SEED = [
    # (key, name, created_at, legacy_ref, price)
    ("jan", "Программирование (23 янв)", "2025-01-01", None, 100),
    ("plain", "Программирование", "2025-02-01", "COURSES:5", 200),
    ("mar", "программирование  (10.03)", "2025-03-01", None, 100),
    ("basic", "Python (базовый)", "2025-01-01", None, 100),
    ("solo", "Дизайн (5 мая 2025)", "2025-01-01", None, 100),
    ("pair", "Python", "2025-01-01", None, 100),
    ("pair2", "python", "2025-02-01", None, 100),
]


async def _seed(conn: Any) -> dict[str, uuid.UUID]:
    ids = {k: uuid.uuid4() for k, *_ in SEED}
    for key, name, created, legacy, price in SEED:
        await conn.execute(
            text(
                "INSERT INTO course (id, name, created_at, legacy_ref, default_price_month, "
                "duration_months, format) VALUES (:id, :n, CAST(CAST(:c AS text) AS timestamptz), :l, :p, 3, "
                "'offline')"
            ),
            {"id": ids[key], "n": name, "c": created, "l": legacy, "p": price},
        )
    branch = (await conn.execute(text("SELECT id FROM branch LIMIT 1"))).scalar_one()
    room = (
        await conn.execute(
            text("INSERT INTO room (branch_id, name, capacity) VALUES (:b, 'R', 10) RETURNING id"),
            {"b": branch},
        )
    ).scalar_one()
    user = (
        await conn.execute(
            text(
                "INSERT INTO app_user (login, full_name, role_id, password_hash) "
                "SELECT 'mig', 'Миграция', id, 'x' FROM role LIMIT 1 RETURNING id"
            )
        )
    ).scalar_one()
    template = (
        await conn.execute(
            text(
                "INSERT INTO cert_template (name, key, draft) VALUES ('T', 'mig', '{}') "
                "RETURNING id"
            )
        )
    ).scalar_one()
    for key, n in (("jan", 2), ("plain", 1), ("mar", 3), ("basic", 1), ("solo", 1)):
        for i in range(n):
            await conn.execute(
                text(
                    "INSERT INTO cohort (course_id, branch_id, room_id, start_date, end_date, "
                    "weekdays, start_time, end_time, capacity, price_month, status) VALUES "
                    "(:c, :b, :r, DATE '2026-01-05' + CAST(:i AS integer), DATE '2026-03-05', '{1}', '10:00', "
                    "'11:00', 10, 100, 'набор')"
                ),
                {"c": ids[key], "b": branch, "r": room, "i": i},
            )
    for key in ("mar", "mar", "basic"):
        await conn.execute(
            text("INSERT INTO lead (full_name, branch_id, course_id) VALUES ('Л', :b, :c)"),
            {"b": branch, "c": ids[key]},
        )
    await conn.execute(
        text(
            "INSERT INTO campaign (name, platform, branch_id, start_date, course_id) "
            "VALUES ('К', 'Instagram', :b, DATE '2026-01-01', :c)"
        ),
        {"b": branch, "c": ids["plain"]},
    )
    await conn.execute(
        text("INSERT INTO note (owner_id, text, course_id) VALUES (:u, 'n', :c)"),
        {"u": user, "c": ids["mar"]},
    )
    # the survivor's rule wins, the merged duplicate rule goes, an instructor's rule moves
    for key, instructor in (("jan", None), ("mar", None), ("plain", user)):
        await conn.execute(
            text(
                "INSERT INTO cert_template_rule (course_id, instructor_id, template_id) "
                "VALUES (:c, :i, :t)"
            ),
            {"c": ids[key], "i": instructor, "t": template},
        )
    return ids


async def _state(conn: Any) -> dict[str, Any]:
    async def rows(q: str) -> list[Any]:
        return [tuple(r) for r in (await conn.execute(text(q))).all()]

    return {
        "courses": await rows("SELECT name, legacy_ref FROM course ORDER BY name"),
        "cohorts": await rows(
            "SELECT c.name, count(*) FROM cohort h JOIN course c ON c.id = h.course_id "
            "GROUP BY 1 ORDER BY 1"
        ),
        "leads": await rows(
            "SELECT c.name, count(*) FROM lead l JOIN course c ON c.id = l.course_id "
            "GROUP BY 1 ORDER BY 1"
        ),
        "campaigns": await rows(
            "SELECT c.name FROM campaign m JOIN course c ON c.id = m.course_id"
        ),
        "notes": await rows("SELECT c.name FROM note n JOIN course c ON c.id = n.course_id"),
        "rules": await rows(
            "SELECT c.name, r.instructor_id IS NULL FROM cert_template_rule r "
            "JOIN course c ON c.id = r.course_id ORDER BY 2"
        ),
        "audit": await rows(
            "SELECT action, label, diff FROM audit_log WHERE entity = 'course' ORDER BY id"
        ),
    }


async def test_migration_0033_merges_dated_duplicates_and_keeps_other_brackets() -> None:
    name = f"{TEST_DB}_mig_cn"
    url = SERVER_URL.set(database=name)
    server = create_async_engine(SERVER_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")
    async with server.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url.render_as_string(hide_password=False))
    engine = create_async_engine(url)
    try:
        await asyncio.to_thread(command.upgrade, cfg, "0030")
        async with engine.begin() as conn:
            ids = await _seed(conn)
        await asyncio.to_thread(command.upgrade, cfg, "0033")
        async with engine.connect() as conn:
            after = await _state(conn)
            survivor = (
                await conn.execute(
                    text(
                        "SELECT id, default_price_month FROM course WHERE name = 'Программирование'"
                    )
                )
            ).one()
        assert set(after["courses"]) == {
            ("Python", None),
            ("Python (базовый)", None),
            ("python", None),  # an old case-only twin without a date is left alone
            ("Дизайн", None),
            ("Программирование", "COURSES:5"),
        }
        # the oldest («23 янв») survives with its own price, under the undated name
        assert survivor == (ids["jan"], 100)
        assert after["cohorts"] == [
            ("Python (базовый)", 1),
            ("Дизайн", 1),
            ("Программирование", 6),
        ]
        assert after["leads"] == [("Python (базовый)", 1), ("Программирование", 2)]
        assert after["campaigns"] == [("Программирование",)]
        assert after["notes"] == [("Программирование",)]
        assert after["rules"] == [("Программирование", False), ("Программирование", True)]
        merges = [(a, lab, d) for a, lab, d in after["audit"] if a == "course.merge"]
        renames = [(lab, d["name"]) for a, lab, d in after["audit"] if a == "course.update"]
        assert [(lab, d["cohorts"][1]) for _, lab, d in merges] == [
            ("Программирование", 1),
            ("программирование  (10.03)", 3),
        ]
        assert merges[0][2]["differs"] == {"default_price_month": ["200.00", "100.00"]}
        assert sorted(renames) == [
            ("Дизайн", ["Дизайн (5 мая 2025)", "Дизайн"]),
            ("Программирование", ["Программирование (23 янв)", "Программирование"]),
        ]
        # down is a no-op, up again changes nothing
        await asyncio.to_thread(command.downgrade, cfg, "0030")
        await asyncio.to_thread(command.upgrade, cfg, "head")
        async with engine.connect() as conn:
            assert await _state(conn) == after
    finally:
        await engine.dispose()
        async with server.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await server.dispose()
