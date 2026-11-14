"""Migration 0017 moves homework / final into per-category scores on the default academy
standard: every enrollment's total, every graduate and the report numbers stay exactly as they
were, on an imported-like fixture and on the demo seed, up / down / up."""

import asyncio
import uuid
from datetime import date, time, timedelta
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.cohorts.schedule import local_dt
from app.demo import seed_demo
from app.metrics import enrollment_attendance, enrollment_results
from app.metrics.reports import graduate_count, graduate_rows, master_rows, master_select
from app.models import Enrollment
from tests.conftest import SERVER_URL, TEST_DB


def old_total(present: int, held: int, homework: int | None, final: int | None) -> int:
    """The rule before 0017, written out: round(20 × present / held) + homework + final."""
    att = (2 * 20 * present + held) // (2 * held) if held else 0
    return att + (homework or 0) + (final or 0)


async def imported_like(db: AsyncSession) -> None:
    """At 0016: a finished imported cohort with every shape of grade the import makes."""
    ids = {k: uuid.uuid4() for k in ("co", "room", "cohort")}
    start = date.today() - timedelta(days=40)

    async def q(sql_text: str, **params: Any) -> Any:
        return await db.execute(text(sql_text), {**ids, **params})

    await q(
        "INSERT INTO room (id, branch_id, name, capacity) "
        "SELECT :room, id, 'Импорт', 10 FROM branch WHERE name = 'Душанбе'"
    )
    await q(
        "INSERT INTO course (id, name, default_price_month, duration_months, format) "
        "VALUES (:co, 'Импортный курс', 100, 1, 'offline')"
    )
    await q(
        "INSERT INTO cohort (id, course_id, branch_id, room_id, start_date, end_date, weekdays, "
        "start_time, end_time, capacity, price_month, status, legacy_ref) "
        "SELECT :cohort, :co, id, :room, :s, CAST(:s AS date) + 20, '{1,2,3,4,5,6,7}', "
        "'10:00', '11:00', 10, 100, 'завершён', 'COHORTS:old' FROM branch WHERE name = 'Душанбе'",
        s=start,
    )
    lessons = []
    for i in range(7):
        day = start + timedelta(days=i)
        row = await q(
            "INSERT INTO lesson (cohort_id, room_id, lesson_date, starts_at, ends_at) "
            "VALUES (:cohort, :room, :d, :a, :b) RETURNING id",
            d=day,
            a=local_dt(day, time(10)),
            b=local_dt(day, time(11)),
        )
        lessons.append(row.scalar_one())
    # (homework, final, legacy total, status, manual, present of 7)
    shapes = [
        (40, 40, None, "выпускник", False, 7),
        (30, None, None, "завершил", False, 3),
        (None, 25, None, "завершил", False, 0),
        (None, None, 85, "выпускник", True, 5),  # an old total only, the status fixed
        (None, None, None, "завершил", False, 2),
        (0, 0, None, "завершил", False, 7),
        (39, 31, None, "выпускник", False, 1),
    ]
    for n, (hw, fin, legacy, status, manual, present) in enumerate(shapes):
        sid = (
            await q(
                "INSERT INTO student (full_name, branch_id) SELECT :n, id FROM branch "
                "WHERE name = 'Душанбе' RETURNING id",
                n=f"Импортный {n}",
            )
        ).scalar_one()
        eid = (
            await q(
                "INSERT INTO enrollment (cohort_id, student_id, status, enrolled_at, "
                "legacy_total, status_manual) VALUES (:cohort, :sid, :st, :at, :lt, :m) "
                "RETURNING id",
                sid=sid,
                st=status,
                at=local_dt(start - timedelta(days=5), time(9)),
                lt=legacy,
                m=manual,
            )
        ).scalar_one()
        for i, lesson in enumerate(lessons):
            await q(
                "INSERT INTO attendance (lesson_id, enrollment_id, present) VALUES (:l, :e, :p)",
                l=lesson,
                e=eid,
                p=i < present,
            )
        if hw is not None or fin is not None:
            await q(
                "INSERT INTO grade (enrollment_id, homework, final) VALUES (:e, :h, :f)",
                e=eid,
                h=hw,
                f=fin,
            )


async def totals_at_0016(db: AsyncSession) -> dict[uuid.UUID, int]:
    ids = list((await db.execute(select(Enrollment.id))).scalars())
    stats = await enrollment_attendance(db, None, enrollment_ids=ids)
    grades = {
        e: (h, f)
        for e, h, f in (
            await db.execute(text("SELECT enrollment_id, homework, final FROM grade"))
        ).all()
    }
    return {
        i: old_total(s["present"], s["held"], *grades.get(i, (None, None)))
        for i, s in stats.items()
    }


async def numbers(db: AsyncSession) -> dict[str, Any]:
    ids = list((await db.execute(select(Enrollment.id))).scalars())
    results = await enrollment_results(db, None, enrollment_ids=ids)
    where = [Enrollment.status == "выпускник"]
    found = (await db.execute(master_select([]))).all()
    return {
        "totals": {i: r["total"] for i, r in results.items()},
        "passed": {i: r["passed"] for i, r in results.items()},
        "statuses": dict((await db.execute(select(Enrollment.id, Enrollment.status))).all()),
        "graduates": await graduate_count(db, where),
        "graduate_scores": {
            r["enrollment_id"]: (r["score"], r["score_legacy"])
            for r in await graduate_rows(db, where)
        },
        "master": [
            (r["cohort_id"], r["graduates"], r["employed"], r["enrolled"])
            for r in await master_rows(db, [tuple(x) for x in found])
        ],
    }


async def test_migration_0017_keeps_every_total_on_imported_data_and_the_demo_seed() -> None:
    name = f"{TEST_DB}_mig_gr"
    url = SERVER_URL.set(database=name)
    server = create_async_engine(SERVER_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")
    async with server.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url.render_as_string(hide_password=False))
    engine = create_async_engine(url)
    session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await asyncio.to_thread(command.upgrade, cfg, "0016")
        async with session() as db:
            await imported_like(db)
            await db.commit()
        async with session() as db:
            imported_before = await totals_at_0016(db)
        assert len(imported_before) == 7
        await asyncio.to_thread(command.upgrade, cfg, "head")
        async with session() as db:
            imported_after = await numbers(db)
        assert imported_after["totals"] == imported_before
        assert (await _scores(engine)) == 8  # 40/40, 30, 25, 0/0, 39/31: 2+1+1+2+2 rows
        # the demo seed on top, then down to 0016 (scores back into homework / final) and up
        async with session() as db:
            await seed_demo(db)
            await db.commit()
        async with session() as db:
            first = await numbers(db)
        await asyncio.to_thread(command.downgrade, cfg, "0016")
        async with session() as db:
            before = await totals_at_0016(db)
        await asyncio.to_thread(command.upgrade, cfg, "head")
        async with session() as db:
            after = await numbers(db)
        assert len(before) > 40  # the demo enrollments and the imported ones
        assert after["totals"] == before  # every enrollment, the old rule = the new one
        assert after == first  # totals, pass, statuses, graduates, scores, master list
        assert after["graduates"] > 0 and any(
            legacy for _, legacy in after["graduate_scores"].values()
        )
        # the downgrade path itself
        await asyncio.to_thread(command.downgrade, cfg, "0016")
    finally:
        await engine.dispose()
        async with server.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await server.dispose()


async def _scores(engine: Any) -> int:
    async with engine.connect() as conn:
        return int((await conn.execute(text("SELECT count(*) FROM grade_score"))).scalar_one())
