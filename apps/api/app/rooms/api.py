"""Rooms and courses (section `rooms`) and the week grid of lessons.

Reads: view on `rooms`, `cohorts` or `students` (the cohort form needs the lists). Writes:
`rooms` change. Rooms are branch-scoped (404 outside the branch); courses are global.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import diff_of, record
from app.auth.deps import Principal, require_csrf_header
from app.cohorts.status import TZ
from app.core.db import DB
from app.core.errors import NOT_FOUND, VALIDATION_FAILED, DomainError
from app.education.errors import COURSE_IN_USE, ROOM_IN_USE
from app.education.scope import AnyReader, branch_for_write, cohort_filters, writer
from app.models import AppUser, Branch, Cohort, Course, Lesson, Room

router = APIRouter(prefix="/api/v1", tags=["rooms"], dependencies=[Depends(require_csrf_header)])

Change = Annotated[Principal, writer("rooms")]
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


def room_out(r: Room, branch_name: str) -> dict[str, Any]:
    return {
        "id": r.id,
        "branch_id": r.branch_id,
        "branch_name": branch_name,
        "name": r.name,
        "capacity": r.capacity,
    }


def course_out(c: Course) -> dict[str, Any]:
    return {
        "id": c.id,
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


@router.get("/rooms")
async def list_rooms(
    p: AnyReader, db: DB, branch_id: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    where = []
    if p.branch_id is not None:
        where.append(Room.branch_id == p.branch_id)
    if branch_id:
        where.append(Room.branch_id == branch_id)
    rows = await db.execute(
        select(Room, Branch.name)
        .join(Branch, Branch.id == Room.branch_id)
        .where(*where)
        .order_by(Branch.name, Room.name)
    )
    return [room_out(r, b) for r, b in rows.all()]


@router.get("/rooms/schedule")
async def week_schedule(
    p: AnyReader,
    db: DB,
    date_from: date,
    date_to: date | None = None,
    branch_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Rooms and their live lessons for `date_from`..`date_to` (default: 7 days)."""
    end = date_to or date_from + timedelta(days=6)
    if end < date_from or (end - date_from).days > 62:
        raise DomainError(VALIDATION_FAILED)
    room_where = []
    if p.branch_id is not None:
        room_where.append(Room.branch_id == p.branch_id)
    if branch_id:
        room_where.append(Room.branch_id == branch_id)
    rooms = (
        await db.execute(
            select(Room, Branch.name)
            .join(Branch, Branch.id == Room.branch_id)
            .where(*room_where)
            .order_by(Branch.name, Room.name)
        )
    ).all()
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
            .order_by(Lesson.starts_at)
        )
    ).all()
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
async def update_room(room_id: uuid.UUID, body: RoomUpdate, p: Change, db: DB) -> dict[str, Any]:
    room, branch_name = await _room(db, p, room_id)
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
async def list_courses(_: AnyReader, db: DB) -> list[dict[str, Any]]:
    rows = await db.execute(select(Course).order_by(Course.name))
    return [course_out(c) for c in rows.scalars()]


def _course_snapshot(c: Course) -> dict[str, Any]:
    return {
        "name": c.name,
        "direction": c.direction,
        "default_price_month": str(c.default_price_month),
        "duration_months": c.duration_months,
        "format": c.format,
    }


@router.post("/courses", status_code=201)
async def create_course(body: CourseIn, p: Change, db: DB) -> dict[str, Any]:
    course = Course(**body.model_dump())
    db.add(course)
    await db.flush()
    await record(
        db, p.id, "course.create", "course", course.id, diff_of({}, _course_snapshot(course))
    )
    return course_out(course)


@router.put("/courses/{course_id}")
async def update_course(course_id: uuid.UUID, body: CourseIn, p: Change, db: DB) -> dict[str, Any]:
    course = (await db.execute(select(Course).where(Course.id == course_id))).scalar_one_or_none()
    if course is None:
        raise DomainError(NOT_FOUND)
    before = _course_snapshot(course)
    for field, value in body.model_dump().items():
        setattr(course, field, value)
    await db.flush()
    await record(
        db, p.id, "course.update", "course", course.id, diff_of(before, _course_snapshot(course))
    )
    return course_out(course)


@router.delete("/courses/{course_id}", status_code=204)
async def delete_course(course_id: uuid.UUID, p: Change, db: DB) -> None:
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
