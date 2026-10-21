"""Attendance, grades and the «Сегодня» screen of the instructor (stage 1b).

Rights: section `attendance` (view to read, change to write) covers attendance and grades. The
instructor role writes here for its own cohorts only (404 for the rest) and nowhere else (#24).
Branch scope for everybody else. Every number comes from `app.metrics`.

Attendance is written cell by cell (lesson × enrollment), so two people marking one lesson never
overwrite each other's other cells; the same cell is last write wins and the audit sentence names
the previous value. «Все присутствуют» fills only the cells nobody has marked yet.
"""

import uuid
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import record
from app.auth.deps import Principal, require, require_csrf_header
from app.cohorts import status as st
from app.core import clock
from app.core.db import DB
from app.core.errors import NOT_FOUND, DomainError
from app.core.versioning import Version, check_version
from app.education.errors import (
    COHORT_CLOSED,
    ENROLLED_AFTER_LESSON,
    LESSON_CANCELLED,
    LESSON_NOT_HELD,
)
from app.education.scope import check_cohort_visible, cohort_filters
from app.export import Col, check_cap, xlsx_response
from app.metrics import (
    enrollment_attendance,
    enrollment_results,
    today_lessons,
    unfilled_lessons,
)
from app.metrics.attendance import EXPELLED, enrolled_by
from app.models import (
    AppUser,
    Attendance,
    Cohort,
    Course,
    Enrollment,
    Grade,
    Lesson,
    Room,
    Student,
)

router = APIRouter(
    prefix="/api/v1", tags=["attendance"], dependencies=[Depends(require_csrf_header)]
)

View = Annotated[Principal, require("attendance", "view")]
Change = Annotated[Principal, require("attendance", "change")]

Reason = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Mark(Strict):
    present: bool
    reason: Reason | None = None  # only an absence has one


class GradeIn(Strict):
    """Only the fields sent change (`null` clears one)."""

    homework: Annotated[int, Field(ge=0, le=40)] | None = None
    final: Annotated[int, Field(ge=0, le=40)] | None = None


def _hm(dt: datetime) -> str:
    return dt.astimezone(st.TZ).strftime("%H:%M")


def _now() -> datetime:
    return clock.now()


async def _cohort(db: AsyncSession, p: Principal, cohort_id: uuid.UUID) -> Cohort:
    cohort = (await db.execute(select(Cohort).where(Cohort.id == cohort_id))).scalar_one_or_none()
    if cohort is None:
        raise DomainError(NOT_FOUND)
    check_cohort_visible(p, cohort)
    return cohort


async def _lesson(
    db: AsyncSession, p: Principal, lesson_id: uuid.UUID
) -> tuple[Lesson, Cohort, str]:
    row = (
        await db.execute(
            select(Lesson, Cohort, Room.name)
            .join(Cohort, Cohort.id == Lesson.cohort_id)
            .join(Room, Room.id == Lesson.room_id)
            .where(Lesson.id == lesson_id)
        )
    ).first()
    if row is None:
        raise DomainError(NOT_FOUND)
    check_cohort_visible(p, row[1])
    return row[0], row[1], row[2]


def _writable(lesson: Lesson, cohort: Cohort) -> None:
    if lesson.cancelled:
        raise DomainError(LESSON_CANCELLED)
    if cohort.status == st.CANCELLED:
        raise DomainError(COHORT_CLOSED)
    # today's lesson takes marks from the morning on, a later one none: a mark pins a lesson
    # through every schedule rebuild
    if lesson.lesson_date > st.today():
        raise DomainError(LESSON_NOT_HELD)


async def _eligible(db: AsyncSession, lesson: Lesson) -> list[tuple[Enrollment, Student]]:
    """The students of a lesson: enrolled (not expelled) by its date."""
    rows = await db.execute(
        select(Enrollment, Student)
        .join(Student, Student.id == Enrollment.student_id)
        .where(
            Enrollment.cohort_id == lesson.cohort_id,
            Enrollment.status != EXPELLED,
            enrolled_by(lesson.lesson_date),
        )
        .order_by(Student.full_name, Enrollment.id)
    )
    return [(e, s) for e, s in rows.all()]


async def _lesson_payload(
    db: AsyncSession, lesson: Lesson, cohort: Cohort, room: str
) -> dict[str, Any]:
    course = (
        await db.execute(select(Course.name).where(Course.id == cohort.course_id))
    ).scalar_one()
    marks = {
        a.enrollment_id: (a, name)
        for a, name in (
            await db.execute(
                select(Attendance, AppUser.full_name)
                .outerjoin(AppUser, AppUser.id == Attendance.marked_by)
                .where(Attendance.lesson_id == lesson.id)
            )
        ).all()
    }
    students = []
    for enrollment, student in await _eligible(db, lesson):
        mark = marks.get(enrollment.id)
        students.append(
            {
                "enrollment_id": enrollment.id,
                "student_id": student.id,
                "student_name": student.full_name,
                "status": enrollment.status,
                "present": mark[0].present if mark else None,
                "reason": mark[0].reason if mark else None,
                "marked_at": mark[0].marked_at if mark else None,
                "marked_by": mark[1] if mark else None,
            }
        )
    ordered = (
        (
            await db.execute(
                select(Lesson.id)
                .where(Lesson.cohort_id == cohort.id, ~Lesson.cancelled)
                .order_by(Lesson.starts_at)
            )
        )
        .scalars()
        .all()
    )
    at = ordered.index(lesson.id) if lesson.id in ordered else None
    return {
        "lesson": {
            "id": lesson.id,
            "cohort_id": cohort.id,
            "cohort_code": cohort.code,
            "course_name": course,
            "room_name": room,
            "date": lesson.lesson_date,
            "start": _hm(lesson.starts_at),
            "end": _hm(lesson.ends_at),
            "cancelled": lesson.cancelled,
            "held": not lesson.cancelled and lesson.starts_at <= _now(),
            "number": at + 1 if at is not None else None,
            "of": len(ordered),
        },
        "prev_id": ordered[at - 1] if at else None,
        "next_id": ordered[at + 1] if at is not None and at + 1 < len(ordered) else None,
        "students": students,
        "marked": sum(1 for s in students if s["present"] is not None),
        "total": len(students),
    }


# ---- one lesson --------------------------------------------------------------------------


@router.get("/lessons/{lesson_id}/attendance")
async def lesson_attendance(lesson_id: uuid.UUID, p: View, db: DB) -> dict[str, Any]:
    lesson, cohort, room = await _lesson(db, p, lesson_id)
    return await _lesson_payload(db, lesson, cohort, room)


@router.put("/lessons/{lesson_id}/attendance/{enrollment_id}")
async def mark_cell(
    lesson_id: uuid.UUID, enrollment_id: uuid.UUID, body: Mark, p: Change, db: DB
) -> dict[str, Any]:
    """One cell. Never reads or writes another cell of the lesson."""
    lesson, cohort, _ = await _lesson(db, p, lesson_id)
    _writable(lesson, cohort)
    row = (
        await db.execute(
            select(Enrollment, Student.full_name, enrolled_by(lesson.lesson_date))
            .join(Student, Student.id == Enrollment.student_id)
            .where(
                Enrollment.id == enrollment_id,
                Enrollment.cohort_id == lesson.cohort_id,
                Enrollment.status != EXPELLED,  # not on the lesson screen: not markable either
            )
        )
    ).first()
    if row is None:
        raise DomainError(NOT_FOUND)
    if not row[2]:
        raise DomainError(ENROLLED_AFTER_LESSON)
    reason = None if body.present else (body.reason or None)
    values = {
        "lesson_id": lesson.id,
        "enrollment_id": enrollment_id,
        "present": body.present,
        "reason": reason,
        "marked_by": p.id,
    }
    inserted = (
        await db.execute(
            pg_insert(Attendance)
            .values(**values)
            .on_conflict_do_nothing()
            .returning(Attendance.lesson_id)
        )
    ).first()
    before: tuple[bool | None, str | None] = (None, None)
    if inserted is None:
        # the cell exists: lock it, so the audit entry names the value it really replaced
        old = (
            await db.execute(
                select(Attendance)
                .where(Attendance.lesson_id == lesson.id, Attendance.enrollment_id == enrollment_id)
                .with_for_update()
            )
        ).scalar_one()
        before = (old.present, old.reason)
        old.present, old.reason, old.marked_by = body.present, reason, p.id
        old.marked_at = _now()
        await db.flush()
    if before != (body.present, reason):
        await record(
            db,
            p.id,
            "attendance.mark",
            "lesson",
            lesson.id,
            {
                "student": [None, row[1]],
                "present": [before[0], body.present],
                "reason": [before[1], reason],
            },
            branch_id=cohort.branch_id,
        )
    return {
        "lesson_id": lesson.id,
        "enrollment_id": enrollment_id,
        "present": body.present,
        "reason": reason,
    }


@router.post("/lessons/{lesson_id}/attendance/all-present")
async def mark_all_present(lesson_id: uuid.UUID, p: Change, db: DB) -> dict[str, Any]:
    """«Все присутствуют»: marks present everyone nobody has marked yet (marks already made,
    absences included, stay as they are)."""
    lesson, cohort, room = await _lesson(db, p, lesson_id)
    _writable(lesson, cohort)
    filled = 0
    for enrollment, _ in await _eligible(db, lesson):
        done = (
            await db.execute(
                pg_insert(Attendance)
                .values(
                    lesson_id=lesson.id,
                    enrollment_id=enrollment.id,
                    present=True,
                    marked_by=p.id,
                )
                .on_conflict_do_nothing()
                .returning(Attendance.lesson_id)
            )
        ).first()
        filled += done is not None
    if filled:
        await record(
            db,
            p.id,
            "attendance.mark_all",
            "lesson",
            lesson.id,
            {"marked": [0, filled]},
            branch_id=cohort.branch_id,
        )
    return await _lesson_payload(db, lesson, cohort, room)


# ---- one cohort: grid and grades ---------------------------------------------------------


@router.get("/cohorts/{cohort_id}/attendance")
async def cohort_grid(cohort_id: uuid.UUID, p: View, db: DB) -> dict[str, Any]:
    """Students × lessons, with each student's held / present / unmarked / percent."""
    cohort = await _cohort(db, p, cohort_id)
    return await grid_of(db, cohort)


async def grid_of(db: AsyncSession, cohort: Cohort) -> dict[str, Any]:
    now = _now()
    lessons = (
        (
            await db.execute(
                select(Lesson).where(Lesson.cohort_id == cohort.id).order_by(Lesson.starts_at)
            )
        )
        .scalars()
        .all()
    )
    rows = (
        await db.execute(
            select(Enrollment, Student)
            .join(Student, Student.id == Enrollment.student_id)
            .where(Enrollment.cohort_id == cohort.id, Enrollment.status != EXPELLED)
            .order_by(Student.full_name, Enrollment.id)
        )
    ).all()
    cells: dict[uuid.UUID, dict[str, dict[str, Any]]] = defaultdict(dict)
    for a in (
        await db.execute(
            select(Attendance).where(Attendance.lesson_id.in_([le.id for le in lessons]))
        )
    ).scalars():
        cells[a.enrollment_id][str(a.lesson_id)] = {"present": a.present, "reason": a.reason}
    stats = await enrollment_attendance(db, cohort.id, now=now)
    return {
        "cohort_id": cohort.id,
        "cohort_code": cohort.code,
        "lessons": [
            {
                "id": le.id,
                "date": le.lesson_date,
                "start": _hm(le.starts_at),
                "end": _hm(le.ends_at),
                "cancelled": le.cancelled,
                "held": not le.cancelled and le.starts_at <= now,
            }
            for le in lessons
        ],
        "students": [
            {
                "enrollment_id": e.id,
                "student_id": s.id,
                "student_name": s.full_name,
                "status": e.status,
                "enrolled_at": e.enrolled_at,
                "marks": cells.get(e.id, {}),
                **stats[e.id],
            }
            for e, s in rows
        ],
    }


@router.get("/cohorts/{cohort_id}/attendance/export")
async def export_grid(cohort_id: uuid.UUID, p: View, db: DB) -> Response:
    """The табель: one row per student, one column per lesson («П» present, «Н» absent with the
    reason, empty = not marked), then the same held / present / unmarked / percent as the screen."""
    cohort = await _cohort(db, p, cohort_id)
    grid = await grid_of(db, cohort)
    check_cap(grid["students"])

    def cell(lesson_id: uuid.UUID) -> Callable[[dict[str, Any]], str]:
        def value(s: dict[str, Any]) -> str:
            mark = s["marks"].get(str(lesson_id))
            if mark is None:
                return ""
            if mark["present"]:
                return "П"
            return f"Н ({mark['reason']})" if mark["reason"] else "Н"

        return value

    columns: list[Col[dict[str, Any]]] = [
        Col("Студент", lambda s: s["student_name"]),
        Col("Статус", lambda s: s["status"]),
        Col("Проведено уроков", lambda s: s["held"], "int"),
        Col("Присутствовал", lambda s: s["present"], "int"),
        Col("Не отмечено", lambda s: s["unmarked"], "int"),
        Col("Посещаемость", lambda s: s["percent"], "percent"),
    ]
    columns += [
        Col(
            f"{le['date']:%d.%m}{' (отм.)' if le['cancelled'] else ''}",
            cell(le["id"]),
        )
        for le in grid["lessons"]
    ]
    return await xlsx_response(
        db,
        p,
        entity="lesson",
        slug=f"tabel_{cohort.code}",
        title="Табель",
        columns=columns,
        rows=grid["students"],
        filters={"cohort": cohort.code},
    )


def _grade_out(enrollment_id: uuid.UUID, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "enrollment_id": enrollment_id,
        "version": result["grade_version"],
        "homework": result["homework"],
        "final": result["final"],
        "attendance_score": result["score"],
        "total": result["total"],
        "passed": result["passed"],
    }


@router.get("/cohorts/{cohort_id}/grades")
async def cohort_grades(cohort_id: uuid.UUID, p: View, db: DB) -> list[dict[str, Any]]:
    cohort = await _cohort(db, p, cohort_id)
    rows = (
        await db.execute(
            select(Enrollment, Student.full_name)
            .join(Student, Student.id == Enrollment.student_id)
            .where(Enrollment.cohort_id == cohort.id, Enrollment.status != EXPELLED)
            .order_by(Student.full_name, Enrollment.id)
        )
    ).all()
    results = await enrollment_results(db, cohort.id)
    return [
        {
            **_grade_out(e.id, results[e.id]),
            "student_id": e.student_id,
            "student_name": name,
            "status": e.status,
            "held": results[e.id]["held"],
            "present": results[e.id]["present"],
            "unmarked": results[e.id]["unmarked"],
            "percent": results[e.id]["percent"],
        }
        for e, name in rows
    ]


@router.patch("/enrollments/{enrollment_id}/grade")
async def set_grade(
    enrollment_id: uuid.UUID, body: GradeIn, version: Version, p: Change, db: DB
) -> dict[str, Any]:
    row = (
        await db.execute(
            select(Enrollment, Cohort)
            .join(Cohort, Cohort.id == Enrollment.cohort_id)
            .where(Enrollment.id == enrollment_id)
        )
    ).first()
    if row is None:
        raise DomainError(NOT_FOUND)
    enrollment, cohort = row
    check_cohort_visible(p, cohort)
    if cohort.status == st.CANCELLED:
        raise DomainError(COHORT_CLOSED)
    # a student has a grade row from the first save on; until then it reads as version 1
    await db.execute(pg_insert(Grade).values(enrollment_id=enrollment.id).on_conflict_do_nothing())
    grade = (
        await db.execute(select(Grade).where(Grade.enrollment_id == enrollment.id))
    ).scalar_one()

    async def current() -> dict[str, Any]:
        result = (await enrollment_results(db, cohort.id, enrollment_ids=[enrollment.id]))[
            enrollment.id
        ]
        return _grade_out(enrollment.id, result)

    await check_version(
        db, grade, version, "grade", current, changes=body.model_dump(exclude_unset=True)
    )
    before = {"homework": grade.homework, "final": grade.final}
    for field in body.model_fields_set:
        setattr(grade, field, getattr(body, field))
    after = {"homework": grade.homework, "final": grade.final}
    diff = {k: [before[k], after[k]] for k in after if before[k] != after[k]}
    if diff:  # nothing changed: no new version, so nobody else's save goes stale for nothing
        grade.updated_at = _now()
        await db.flush()
        await record(
            db, p.id, "grade.update", "enrollment", enrollment.id, diff, branch_id=cohort.branch_id
        )
        await st.reevaluate(db, enrollment, cohort, p.id)
    return await current()


# ---- «Сегодня» and «Не заполнено» --------------------------------------------------------


def _lesson_item(
    row: tuple[Lesson, Cohort, str, str, int, int], names: dict[Any, str]
) -> dict[str, Any]:
    lesson, cohort, course, room, total, marked = row
    return {
        "lesson_id": lesson.id,
        "cohort_id": cohort.id,
        "cohort_code": cohort.code,
        "course_name": course,
        "room_name": room,
        "date": lesson.lesson_date,
        "start": _hm(lesson.starts_at),
        "end": _hm(lesson.ends_at),
        "marked": marked,
        "total": total,
        "instructor_id": cohort.instructor_id,
        "instructor_name": names.get(cohort.instructor_id),
    }


@router.get("/me/today")
async def my_today(p: View, db: DB) -> dict[str, Any]:
    """The lessons of today in the user's scope (an instructor: their own cohorts) with
    marked / total, and the «не заполнено» list (#21): held lessons of the last 30 days with
    somebody still unmarked, also grouped by instructor for the manager."""
    where = cohort_filters(p)
    today = await today_lessons(db, where, st.today())
    unfilled = await unfilled_lessons(db, where)
    ids = {r[1].instructor_id for r in [*today, *unfilled] if r[1].instructor_id}
    names = (
        {
            i: n
            for i, n in (
                await db.execute(select(AppUser.id, AppUser.full_name).where(AppUser.id.in_(ids)))
            ).all()
        }
        if ids
        else {}
    )
    items = [_lesson_item(r, names) for r in unfilled]
    groups: dict[Any, dict[str, Any]] = {}
    for item in items:
        g = groups.setdefault(
            item["instructor_id"],
            {
                "instructor_id": item["instructor_id"],
                "instructor_name": item["instructor_name"],
                "lessons": [],
            },
        )
        g["lessons"].append(item)
    return {
        "date": st.today(),
        "today": [_lesson_item(r, names) for r in today],
        "unfilled": items,
        "unfilled_by_instructor": list(groups.values()),
    }
