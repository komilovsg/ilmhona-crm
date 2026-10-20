"""Fixtures for the education tests: fake rooms, courses, cohorts, students."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Any

import httpx

from app.cohorts.status import today
from tests.conftest import branch_id, sql

C = "/api/v1/cohorts"


async def make_room(
    branch: str = "Душанбе", name: str = "Lovelace", capacity: int = 20
) -> uuid.UUID:
    rows = await sql(
        "INSERT INTO room (branch_id, name, capacity) VALUES (:b, :n, :c) RETURNING id",
        b=await branch_id(branch),
        n=name,
        c=capacity,
    )
    return rows[0][0]  # type: ignore[no-any-return]


async def make_course(name: str = "Python", price: int = 500) -> uuid.UUID:
    rows = await sql(
        "INSERT INTO course (name, direction, default_price_month, duration_months, format) "
        "VALUES (:n, 'IT', :p, 3, 'offline') RETURNING id",
        n=name,
        p=price,
    )
    return rows[0][0]  # type: ignore[no-any-return]


async def make_student(
    name: str = "Student", branch: str = "Душанбе", phone: str | None = None
) -> uuid.UUID:
    rows = await sql(
        "INSERT INTO student (full_name, branch_id, phone) VALUES (:n, :b, :p) RETURNING id",
        n=name,
        b=await branch_id(branch),
        p=phone,
    )
    return rows[0][0]  # type: ignore[no-any-return]


def next_monday(after: date | None = None) -> date:
    d = (after or today()) + timedelta(days=7)
    return d - timedelta(days=d.weekday())


def body(
    course: uuid.UUID,
    room: uuid.UUID,
    *,
    start: date | None = None,
    weeks: int = 4,
    weekdays: list[int] | None = None,
    start_time: str = "10:00",
    end_time: str = "11:30",
    **extra: Any,
) -> dict[str, Any]:
    start = start or next_monday()
    return {
        "course_id": str(course),
        "room_id": str(room),
        "start_date": start.isoformat(),
        "end_date": (start + timedelta(weeks=weeks)).isoformat(),
        "weekdays": weekdays or [1, 3],
        "start_time": start_time,
        "end_time": end_time,
        "capacity": 10,
        **extra,
    }


async def make_cohort(
    c: httpx.AsyncClient,
    course: uuid.UUID,
    room: uuid.UUID,
    *,
    branch: str = "Душанбе",
    **kw: Any,
) -> dict[str, Any]:
    r = await c.post(C, json=body(course, room, branch_id=str(await branch_id(branch)), **kw))
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


@asynccontextmanager
async def instructor_rights(**sections: str) -> AsyncIterator[None]:
    """Give the seeded instructor role extra rights for one test, then put the matrix back."""
    saved = await sql(
        "SELECT section, level FROM role_permission "
        "WHERE role_id = (SELECT id FROM role WHERE code = 'instructor')"
    )
    try:
        for section, level in sections.items():
            await sql(
                "INSERT INTO role_permission (role_id, section, level) "
                "SELECT id, :s, :l FROM role WHERE code = 'instructor' "
                "ON CONFLICT (role_id, section) DO UPDATE SET level = :l",
                s=section,
                l=level,
            )
        yield
    finally:
        await sql(
            "DELETE FROM role_permission "
            "WHERE role_id = (SELECT id FROM role WHERE code = 'instructor')"
        )
        for section, level in saved:
            await sql(
                "INSERT INTO role_permission (role_id, section, level) "
                "SELECT id, :s, :l FROM role WHERE code = 'instructor'",
                s=section,
                l=level,
            )
