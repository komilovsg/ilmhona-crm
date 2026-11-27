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
        # the shapes the old system left in production
        ("AI в дизайне (Aug", "AI в дизайне"),
        ("Frontend с ИИ (Sep 26) (Sep", "Frontend с ИИ"),
        ("Python - базовый уровень остатки (Jul", "Python - базовый уровень остатки"),
        ("Маркетинг Pro (August 2025)", "Маркетинг Pro"),
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
        "Курс (Mayor)",
        "Python (базовый",
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
    # case-only twins: the oldest is small-lettered, so the capitalised one with most cohorts
    # names the course («SQL» and «Sql» both have 2: the older «SQL» wins)
    ("sql", "sql", "2025-01-01", None, 100),
    ("sql_up", "SQL", "2025-02-01", None, 100),
    ("sql_cap", "Sql", "2025-03-01", None, 100),
    # one course runs three times on Monday and once every day, plus its dated twin
    # the free survivor takes the paid twins' price: 800 and 500 tie on cohorts, 800 wins
    ("robo", "Робототехника (5 фев)", "2025-01-01", None, 0),
    ("robo2", "Робототехника", "2025-02-01", None, 800),
    ("robo3", "Робототехника (Mar", "2025-03-01", None, 500),
    # the owner's one-off merge into the base Python course
    ("pyb1", "Python - базовый уровень 1 группа (Jul", "2025-01-15", None, 0),
    ("pyb", "Python - базовый уровень", "2025-02-01", None, 300),
    ("pyb_rest", "Python - базовый уровень остатки", "2025-03-01", None, 0),
]
# (course key, weekdays, start, end); each cohort gets its own room
SCHEDULES = [
    ("robo", "{1}", "09:00", "10:30"),
    ("robo", "{1}", "12:00", "13:30"),
    ("robo", "{1}", "15:00", "16:30"),
    ("robo", "{1,2,3,4,5,6,7}", "18:00", "19:00"),
    ("robo2", "{2,4}", "10:00", "11:00"),
    ("robo3", "{6}", "11:00", "12:00"),
    ("pyb1", "{1}", "10:00", "11:00"),
    ("pyb", "{2}", "10:00", "11:00"),
    ("pyb_rest", "{3}", "10:00", "11:00"),
    ("sql", "{1}", "10:00", "11:00"),
    ("sql_up", "{2}", "10:00", "11:00"),
    ("sql_up", "{3}", "10:00", "11:00"),
    ("sql_cap", "{4}", "10:00", "11:00"),
    ("sql_cap", "{5}", "10:00", "11:00"),
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
    rooms = [
        (
            await conn.execute(
                text(
                    "INSERT INTO room (branch_id, name, capacity) VALUES (:b, :n, 10) RETURNING id"
                ),
                {"b": branch, "n": f"R{n}"},
            )
        ).scalar_one()
        for n in range(len(SCHEDULES))
    ]
    room = rooms[0]
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
    for n, (key, days, start, end) in enumerate(SCHEDULES):
        cohort = (
            await conn.execute(
                text(
                    "INSERT INTO cohort (course_id, branch_id, room_id, instructor_id, start_date, "
                    "end_date, weekdays, start_time, end_time, capacity, price_month, funding, status) "
                    "VALUES (:c, :b, :r, :u, DATE '2026-02-02', DATE '2026-04-30', "
                    "CAST(CAST(:d AS text) AS integer[]), CAST(CAST(:s AS text) AS time), CAST(CAST(:e AS text) AS time), 10, :pm, :f, 'активный') "
                    "RETURNING id"
                ),
                {
                    "c": ids[key],
                    "b": branch,
                    "r": rooms[n],
                    "u": user if key == "robo" else None,
                    # free robotics cohorts stay free after the course price becomes 800
                    "pm": 0 if key.startswith("robo") else 100,
                    "f": "бесплатный" if key.startswith("robo") else "платный",
                    "d": days,
                    "s": start,
                    "e": end,
                },
            )
        ).scalar_one()
        for day in range(2):  # two lessons each, on the first Monday / Tuesday
            await conn.execute(
                text(
                    "INSERT INTO lesson (cohort_id, room_id, lesson_date, starts_at, ends_at) "
                    "VALUES (:h, :r, DATE '2026-02-02' + CAST(:d AS integer), "
                    "((DATE '2026-02-02' + CAST(:d AS integer)) + CAST(CAST(:s AS text) AS time)) AT TIME ZONE 'Asia/Dushanbe', "
                    "((DATE '2026-02-02' + CAST(:d AS integer)) + CAST(CAST(:e AS text) AS time)) AT TIME ZONE 'Asia/Dushanbe')"
                ),
                {"h": cohort, "r": rooms[n], "d": day, "s": start, "e": end},
            )
        student = (
            await conn.execute(
                text("INSERT INTO student (full_name, branch_id) VALUES (:n, :b) RETURNING id"),
                {"n": f"Студент {n}", "b": branch},
            )
        ).scalar_one()
        await conn.execute(
            text("INSERT INTO enrollment (student_id, cohort_id) VALUES (:s, :h)"),
            {"s": student, "h": cohort},
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
        # every cohort row except its course: id, code, schedule, room, dates, instructor
        "cohort_rows": await rows(
            "SELECT id, code, branch_id, room_id, instructor_id, start_date, end_date, weekdays, "
            "start_time, end_time, capacity, price_month, funding, status FROM cohort ORDER BY id"
        ),
        "lessons": await rows(
            "SELECT id, cohort_id, room_id, lesson_date, starts_at, ends_at FROM lesson ORDER BY id"
        ),
        "enrollments": await rows("SELECT id, student_id, cohort_id FROM enrollment ORDER BY id"),
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
        await asyncio.to_thread(command.upgrade, cfg, "0032")
        async with engine.begin() as conn:
            ids = await _seed(conn)
        async with engine.connect() as conn:
            before = await _state(conn)
        await asyncio.to_thread(command.upgrade, cfg, "0033")
        async with engine.connect() as conn:
            after = await _state(conn)
        # merging only moves cohort.course_id: no cohort, lesson or enrollment changes or goes
        for key in ("cohort_rows", "lessons", "enrollments"):
            assert after[key] == before[key], key
        assert len(after["cohort_rows"]) == 8 + len(SCHEDULES)
        async with engine.connect() as conn:
            robo = (
                await conn.execute(
                    text(
                        "SELECT h.weekdays, h.start_time::text FROM cohort h JOIN course c "
                        "ON c.id = h.course_id WHERE c.name = 'Робототехника' ORDER BY 2"
                    )
                )
            ).all()
            survivor = (
                await conn.execute(
                    text(
                        "SELECT id, default_price_month FROM course WHERE name = 'Программирование'"
                    )
                )
            ).one()
        assert [(list(d), t) for d, t in robo] == [
            ([1], "09:00:00"),
            ([2, 4], "10:00:00"),
            ([6], "11:00:00"),
            ([1], "12:00:00"),
            ([1], "15:00:00"),
            ([1, 2, 3, 4, 5, 6, 7], "18:00:00"),
        ]
        async with engine.connect() as conn:
            prices = dict(
                (await conn.execute(text("SELECT name, default_price_month FROM course"))).all()
            )
        assert prices["Робототехника"] == 800  # the free survivor took the paid twin's price
        assert prices["Python - базовый уровень"] == 300
        assert prices["Программирование"] == 100  # a paid survivor keeps its own
        assert set(after["courses"]) == {
            ("Python", None),  # «python» merged into the older «Python»
            ("Python (базовый)", None),
            ("Python - базовый уровень", None),
            ("SQL", None),
            ("Дизайн", None),
            ("Программирование", "COURSES:5"),
            ("Робототехника", None),
        }
        # the oldest («23 янв») survives with its own price, under the undated name
        assert survivor == (ids["jan"], 100)
        assert after["cohorts"] == [
            ("Python (базовый)", 1),
            ("Python - базовый уровень", 3),
            ("SQL", 5),
            ("Дизайн", 1),
            ("Программирование", 6),
            ("Робототехника", 6),
        ]
        assert after["leads"] == [("Python (базовый)", 1), ("Программирование", 2)]
        assert after["campaigns"] == [("Программирование",)]
        assert after["notes"] == [("Программирование",)]
        assert after["rules"] == [("Программирование", False), ("Программирование", True)]
        merges = [(a, lab, d) for a, lab, d in after["audit"] if a == "course.merge"]
        renames = [(lab, d["name"]) for a, lab, d in after["audit"] if a == "course.update"]
        robo_change = next(
            d for a, lab, d in after["audit"] if a == "course.update" and lab == "Робототехника"
        )
        assert robo_change["default_price_month"] == ["0.00", "800.00"]
        assert sorted((lab, d["cohorts"][1]) for _, lab, d in merges) == sorted(
            [
                ("Программирование", 1),
                ("программирование  (10.03)", 3),
                ("python", 0),
                ("SQL", 2),
                ("Sql", 2),
                ("Робототехника", 1),
                ("Робототехника (Mar", 1),
                ("Python - базовый уровень", 1),
                ("Python - базовый уровень остатки", 1),
            ]
        )
        plain = next(d for _, lab, d in merges if lab == "Программирование")
        assert plain["differs"] == {"default_price_month": ["200.00", "100.00"]}
        assert sorted(renames) == sorted(
            [
                ("Дизайн", ["Дизайн (5 мая 2025)", "Дизайн"]),
                ("Программирование", ["Программирование (23 янв)", "Программирование"]),
                ("Робототехника", ["Робототехника (5 фев)", "Робототехника"]),
                ("SQL", ["sql", "SQL"]),
                (
                    "Python - базовый уровень",
                    ["Python - базовый уровень 1 группа (Jul", "Python - базовый уровень"],
                ),
            ]
        )
        # down is a no-op, up again changes nothing
        await asyncio.to_thread(command.downgrade, cfg, "0032")
        await asyncio.to_thread(command.upgrade, cfg, "head")
        async with engine.connect() as conn:
            assert await _state(conn) == after
    finally:
        await engine.dispose()
        async with server.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await server.dispose()
