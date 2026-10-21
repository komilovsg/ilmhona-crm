"""Rooms and courses (section `rooms`) and the week grid of lessons.

Reads: view on `rooms`, `cohorts` or `students` (the cohort form needs the lists). Writes:
`rooms` change. Rooms are branch-scoped (404 outside the branch); courses are global.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import diff_of, record
from app.auth.deps import Principal, require, require_csrf_header
from app.cohorts.status import TZ
from app.core.db import DB
from app.core.errors import NOT_FOUND, VALIDATION_FAILED, DomainError
from app.core.versioning import Version, check_version
from app.education.errors import COURSE_GLOBAL_ONLY, COURSE_IN_USE, ROOM_IN_USE
from app.education.scope import RoomReader, branch_for_write, cohort_filters, writer
from app.export import MAX_ROWS, Col, xlsx_response
from app.models import AppUser, Branch, Cohort, Course, Lesson, Room

router = APIRouter(prefix="/api/v1", tags=["rooms"], dependencies=[Depends(require_csrf_header)])

Change = Annotated[Principal, writer("rooms")]


async def _course_writer(p: Change) -> Principal:
    """Courses are shared by both branches: only users without a branch write them."""
    if p.branch_id is not None:
        raise DomainError(COURSE_GLOBAL_ONLY)
    return p


CourseChange = Annotated[Principal, Depends(_course_writer)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Direction = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoomCreate(Strict):
    branch_id: uuid.UUID | None = None
    name: Name
    capacity: Annotated[int, Field(ge=1, le=100)]


class RoomUpdate(Strict):
    name: Name | None = None
    capacity: Annotated[int, Field(ge=1, le=100)] | None = None


class CourseIn(Strict):
    name: Name
    direction: Direction | None = None
    default_price_month: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)] = Decimal(
        0
    )
    duration_months: Annotated[int, Field(ge=1, le=36)]
    format: Literal["offline", "online"]


class CourseUpdate(Strict):
    """Only the fields present change (`direction: null` clears it)."""

    name: Name | None = None
    direction: Direction | None = None
    default_price_month: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)] | None = (
        None
    )
    duration_months: Annotated[int, Field(ge=1, le=36)] | None = None
    format: Literal["offline", "online"] | None = None


def room_out(r: Room, branch_name: str) -> dict[str, Any]:
    return {
        "id": r.id,
        "version": r.version,
        "branch_id": r.branch_id,
        "branch_name": branch_name,
        "name": r.name,
        "capacity": r.capacity,
    }


def course_out(c: Course) -> dict[str, Any]:
    return {
        "id": c.id,
        "version": c.version,
        "name": c.name,
        "direction": c.direction,
        "default_price_month": c.default_price_month,
        "duration_months": c.duration_months,
        "format": c.format,
    }


async def _room(db: AsyncSession, p: Principal, room_id: uuid.UUID) -> tuple[Room, str]:
    row = (
        await db.execute(
            select(Room, Branch.name)
            .join(Branch, Branch.id == Room.branch_id)
            .where(Room.id == room_id)
        )
    ).first()
    if row is None:
        raise DomainError(NOT_FOUND)
    p.check_scope(row[0].branch_id)
    return row[0], row[1]


# ---- rooms -------------------------------------------------------------------------------


def _room_where(p: Principal, branch_id: uuid.UUID | None) -> list[Any]:
    where: list[Any] = []
    if p.branch_id is not None:
        where.append(Room.branch_id == p.branch_id)
    if branch_id:
        where.append(Room.branch_id == branch_id)
    return where


def _room_select(where: list[Any]) -> Any:
    return (
        select(Room, Branch.name)
        .join(Branch, Branch.id == Room.branch_id)
        .where(*where)
        .order_by(Branch.name, Room.name)
    )


@router.get("/rooms")
async def list_rooms(
    p: RoomReader, db: DB, branch_id: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    rows = await db.execute(_room_select(_room_where(p, branch_id)))
    return [room_out(r, b) for r, b in rows.all()]


ROOM_COLUMNS: list[Col[Any]] = [
    Col("Филиал", lambda r: r[1]),
    Col("Аудитория", lambda r: r[0].name),
    Col("Вместимость", lambda r: r[0].capacity, "int"),
]


@router.get("/rooms/export")
async def export_rooms(
    p: Annotated[Principal, require("rooms", "view")], db: DB, branch_id: uuid.UUID | None = None
) -> Response:
    rows = (await db.execute(_room_select(_room_where(p, branch_id)).limit(MAX_ROWS + 1))).all()
    return await xlsx_response(
        db,
        p,
        entity="room",
        slug="auditorii",
        title="Аудитории",
        columns=ROOM_COLUMNS,
        rows=rows,
        filters={"branch_id": branch_id},
    )


async def _week(
    p: Principal,
    db: AsyncSession,
    date_from: date,
    date_to: date | None,
    branch_id: uuid.UUID | None,
) -> tuple[date, list[Any], list[Any]]:
    """(end date, rooms, lessons) of the week grid: the one query behind the grid and its export."""
    end = date_to or date_from + timedelta(days=6)
    if end < date_from or (end - date_from).days > 62:
        raise DomainError(VALIDATION_FAILED)
    rooms = (await db.execute(_room_select(_room_where(p, branch_id)))).all()
    lessons = (
        await db.execute(
            select(Lesson, Cohort, Course.name, AppUser.full_name)
            .join(Cohort, Cohort.id == Lesson.cohort_id)
            .join(Course, Course.id == Cohort.course_id)
            .outerjoin(AppUser, AppUser.id == Cohort.instructor_id)
            .where(
                Lesson.room_id.in_([r.id for r, _ in rooms]),
                ~Lesson.cancelled,
                Lesson.lesson_date >= date_from,
                Lesson.lesson_date <= end,
                *cohort_filters(p),
            )
            .order_by(Lesson.starts_at, Lesson.id)
        )
    ).all()
    return end, list(rooms), list(lessons)


@router.get("/rooms/schedule")
async def week_schedule(
    p: RoomReader,
    db: DB,
    date_from: date,
    date_to: date | None = None,
    branch_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Rooms and their live lessons for `date_from`..`date_to` (default: 7 days)."""
    end, rooms, lessons = await _week(p, db, date_from, date_to, branch_id)
    return {
        "date_from": date_from,
        "date_to": end,
        "rooms": [room_out(r, b) for r, b in rooms],
        "lessons": [
            {
                "id": le.id,
                "room_id": le.room_id,
                "cohort_id": c.id,
                "cohort_code": c.code,
                "course_name": course,
                "instructor_name": instructor,
                "date": le.lesson_date,
                "start": le.starts_at.astimezone(TZ).strftime("%H:%M"),
                "end": le.ends_at.astimezone(TZ).strftime("%H:%M"),
            }
            for le, c, course, instructor in lessons
        ],
    }


LESSON_COLUMNS: list[Col[Any]] = [
    Col("Дата", lambda r: r[0].lesson_date, "date"),
    Col("Начало", lambda r: r[0].starts_at.astimezone(TZ).strftime("%H:%M")),
    Col("Конец", lambda r: r[0].ends_at.astimezone(TZ).strftime("%H:%M")),
    Col("Филиал", lambda r: r[4]),
    Col("Аудитория", lambda r: r[5]),
    Col("Поток", lambda r: r[1].code),
    Col("Курс", lambda r: r[2]),
    Col("Инструктор", lambda r: r[3]),
]


@router.get("/rooms/schedule/export")
async def export_schedule(
    p: Annotated[Principal, require("rooms", "view")],
    db: DB,
    date_from: date,
    date_to: date | None = None,
    branch_id: uuid.UUID | None = None,
) -> Response:
    """The lesson schedule of the week grid, one row per lesson."""
    end, rooms, lessons = await _week(p, db, date_from, date_to, branch_id)
    where_room = {r.id: (b, r.name) for r, b in rooms}
    rows = [(*row, *where_room[row[0].room_id]) for row in lessons]
    return await xlsx_response(
        db,
        p,
        entity="lesson",
        slug="raspisanie",
        title="Расписание",
        columns=LESSON_COLUMNS,
        rows=rows,
        filters={"date_from": date_from, "date_to": end, "branch_id": branch_id},
    )


@router.post("/rooms", status_code=201)
async def create_room(body: RoomCreate, p: Change, db: DB) -> dict[str, Any]:
    room = Room(
        branch_id=branch_for_write(p, body.branch_id), name=body.name, capacity=body.capacity
    )
    db.add(room)
    await db.flush()
    await record(
        db,
        p.id,
        "room.create",
        "room",
        room.id,
        diff_of({}, {"name": room.name, "capacity": room.capacity}),
        branch_id=room.branch_id,
    )
    return room_out(room, (await _room(db, p, room.id))[1])


@router.patch("/rooms/{room_id}")
async def update_room(
    room_id: uuid.UUID, body: RoomUpdate, version: Version, p: Change, db: DB
) -> dict[str, Any]:
    room, branch_name = await _room(db, p, room_id)

    async def current() -> dict[str, Any]:
        return room_out(room, branch_name)

    await check_version(
        db, room, version, "room", current, changes=body.model_dump(exclude_unset=True)
    )
    before = {"name": room.name, "capacity": room.capacity}
    if body.name is not None:
        room.name = body.name
    if body.capacity is not None:
        room.capacity = body.capacity
    await db.flush()
    await record(
        db,
        p.id,
        "room.update",
        "room",
        room.id,
        diff_of(before, {"name": room.name, "capacity": room.capacity}),
        branch_id=room.branch_id,
    )
    return room_out(room, branch_name)


@router.delete("/rooms/{room_id}", status_code=204)
async def delete_room(room_id: uuid.UUID, p: Change, db: DB) -> None:
    room, _ = await _room(db, p, room_id)
    snapshot = {"name": room.name, "capacity": room.capacity}
    try:
        async with db.begin_nested():
            await db.delete(room)
            await db.flush()
    except IntegrityError as exc:
        raise DomainError(ROOM_IN_USE) from exc
    await record(
        db, p.id, "room.delete", "room", room_id, diff_of(snapshot, {}), branch_id=room.branch_id
    )


# ---- courses -----------------------------------------------------------------------------


@router.get("/courses")
async def list_courses(_: RoomReader, db: DB) -> list[dict[str, Any]]:
    rows = await db.execute(select(Course).order_by(Course.name))
    return [course_out(c) for c in rows.scalars()]


COURSE_COLUMNS: list[Col[Course]] = [
    Col("Курс", lambda c: c.name),
    Col("Направление", lambda c: c.direction),
    Col("Цена за месяц", lambda c: c.default_price_month, "money"),
    Col("Длительность, мес.", lambda c: c.duration_months, "int"),
    Col("Формат", lambda c: "Онлайн" if c.format == "online" else "Офлайн"),
]


@router.get("/courses/export")
async def export_courses(p: Annotated[Principal, require("rooms", "view")], db: DB) -> Response:
    rows = (await db.execute(select(Course).order_by(Course.name).limit(MAX_ROWS + 1))).scalars()
    return await xlsx_response(
        db,
        p,
        entity="course",
        slug="kursy",
        title="Курсы",
        columns=COURSE_COLUMNS,
        rows=list(rows),
        filters={},
    )


async def _async(value: dict[str, Any]) -> dict[str, Any]:
    return value


def _course_snapshot(c: Course) -> dict[str, Any]:
    return {
        "name": c.name,
        "direction": c.direction,
        "default_price_month": str(c.default_price_month),
        "duration_months": c.duration_months,
        "format": c.format,
    }


@router.post("/courses", status_code=201)
async def create_course(body: CourseIn, p: CourseChange, db: DB) -> dict[str, Any]:
    course = Course(**body.model_dump())
    db.add(course)
    await db.flush()
    await record(
        db, p.id, "course.create", "course", course.id, diff_of({}, _course_snapshot(course))
    )
    return course_out(course)


@router.patch("/courses/{course_id}")
async def update_course(
    course_id: uuid.UUID, body: CourseUpdate, version: Version, p: CourseChange, db: DB
) -> dict[str, Any]:
    course = (await db.execute(select(Course).where(Course.id == course_id))).scalar_one_or_none()
    if course is None:
        raise DomainError(NOT_FOUND)
    await check_version(
        db,
        course,
        version,
        "course",
        lambda: _async(course_out(course)),
        changes=body.model_dump(exclude_unset=True),
    )
    before = _course_snapshot(course)
    for field in body.model_fields_set:
        value = getattr(body, field)
        if value is not None or field == "direction":  # NOT NULL columns ignore an explicit null
            setattr(course, field, value)
    await db.flush()
    await record(
        db, p.id, "course.update", "course", course.id, diff_of(before, _course_snapshot(course))
    )
    return course_out(course)


@router.delete("/courses/{course_id}", status_code=204)
async def delete_course(course_id: uuid.UUID, p: CourseChange, db: DB) -> None:
    course = (await db.execute(select(Course).where(Course.id == course_id))).scalar_one_or_none()
    if course is None:
        raise DomainError(NOT_FOUND)
    snapshot = _course_snapshot(course)
    try:
        async with db.begin_nested():
            await db.delete(course)
            await db.flush()
    except IntegrityError as exc:
        raise DomainError(COURSE_IN_USE) from exc
    await record(db, p.id, "course.delete", "course", course_id, diff_of(snapshot, {}))
