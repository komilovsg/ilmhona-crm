"""Attendance and grade numbers (SPEC «Посещаемость», «Оценки»): the one place that computes them.

- Held lesson (#12) = not cancelled and already started. Only held lessons count; a lesson that
  has not happened yet, or was cancelled, is neither a presence nor an absence.
- A student's lessons start at their enrollment: held lessons dated on or after the local date of
  `enrolled_at`. Attendance % = present / held. `unmarked` = held lessons without a mark, shown
  next to the percentage so «100 % of 1 marked lesson out of 13» can never pass as 100 % (#12).
- Attendance score (0-20) = round(20 × present / held). Total = attendance score + homework +
  final (an empty grade counts as 0). Total ≥ 70 graduates a student when the cohort closes.
- «Не заполнено» (#21) = held lessons of the last 30 days where some enrolled (not expelled)
  student has no mark.
"""

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import ColumnElement, Date, and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.models import Attendance, Cohort, Course, Enrollment, Grade, Lesson, Room

TZ_NAME = "Asia/Dushanbe"
ATTENDANCE_MAX = 20
GRADE_MAX = 40
PASS_TOTAL = 70
UNFILLED_DAYS = 30
EXPELLED = "отчислен"


def _now() -> datetime:
    return clock.now()


def attendance_score(present: int, held: int) -> int:
    """round(20 × present / held), halves up; no held lessons yet = 0."""
    if held <= 0:
        return 0
    return (2 * ATTENDANCE_MAX * present + held) // (2 * held)


def grade_total(att_score: int, homework: int | None, final: int | None) -> int:
    return att_score + (homework or 0) + (final or 0)


def passed(total: int) -> bool:
    return total >= PASS_TOTAL


def has_marks() -> ColumnElement[bool]:
    """The lesson has at least one mark: the schedule rebuild never deletes it."""
    return exists().where(Attendance.lesson_id == Lesson.id)


def held_lesson(now: datetime) -> ColumnElement[bool]:
    return and_(~Lesson.cancelled, Lesson.starts_at <= now)


def enrolled_by(lesson_date: Any = None) -> ColumnElement[bool]:
    """The enrollment existed on the lesson's date (compared as local calendar dates)."""
    return func.timezone(TZ_NAME, Enrollment.enrolled_at).cast(Date) <= (
        Lesson.lesson_date if lesson_date is None else lesson_date
    )


def stats_of(held: int, present: int, marked: int) -> dict[str, Any]:
    score = attendance_score(present, held)
    return {
        "held": held,
        "present": present,
        "absent": marked - present,
        "unmarked": held - marked,
        "percent": round(100 * present / held, 1) if held else None,
        "score": score,
    }


async def enrollment_attendance(
    db: AsyncSession,
    cohort_id: uuid.UUID | None,
    *,
    now: datetime | None = None,
    enrollment_ids: list[uuid.UUID] | None = None,
) -> dict[uuid.UUID, dict[str, Any]]:
    """Per enrollment of the cohort (or, with `cohort_id` None, of the given enrollments in any
    cohorts, in one query): held, present, absent, unmarked, percent, score."""
    now = now or _now()
    held = and_(Lesson.cohort_id == Enrollment.cohort_id, held_lesson(now), enrolled_by())
    query = (
        select(
            Enrollment.id,
            func.count(Lesson.id),
            func.count(Attendance.lesson_id),
            func.count(Attendance.lesson_id).filter(Attendance.present),
        )
        .select_from(Enrollment)
        .outerjoin(Lesson, held)
        .outerjoin(
            Attendance,
            and_(Attendance.lesson_id == Lesson.id, Attendance.enrollment_id == Enrollment.id),
        )
        .group_by(Enrollment.id)
    )
    if cohort_id is not None:
        query = query.where(Enrollment.cohort_id == cohort_id)
    if enrollment_ids is not None:
        query = query.where(Enrollment.id.in_(enrollment_ids))
    rows = await db.execute(query)
    return {i: stats_of(h, p, m) for i, h, m, p in rows.all()}


async def enrollment_results(
    db: AsyncSession,
    cohort_id: uuid.UUID | None,
    *,
    now: datetime | None = None,
    enrollment_ids: list[uuid.UUID] | None = None,
) -> dict[uuid.UUID, dict[str, Any]]:
    """Attendance stats plus homework, final, total, grade version (1 until a grade exists)."""
    stats = await enrollment_attendance(db, cohort_id, now=now, enrollment_ids=enrollment_ids)
    if not stats:
        return {}
    grades = {
        g.enrollment_id: g
        for g in (await db.execute(select(Grade).where(Grade.enrollment_id.in_(list(stats)))))
        .scalars()
        .all()
    }
    out: dict[uuid.UUID, dict[str, Any]] = {}
    for eid, s in stats.items():
        g = grades.get(eid)
        hw, fin = (g.homework, g.final) if g else (None, None)
        total = grade_total(s["score"], hw, fin)
        out[eid] = {
            **s,
            "homework": hw,
            "final": fin,
            "total": total,
            "passed": passed(total),
            "grade_version": g.version if g else 1,
        }
    return out


def lesson_marks_query(where: list[ColumnElement[bool]]) -> Any:
    """Lessons with how many of their students are marked (marked / total). A student counts for
    a lesson when enrolled (not expelled) by its date."""
    return (
        select(
            Lesson,
            Cohort,
            Course.name,
            Room.name,
            func.count(Enrollment.id).label("total"),
            func.count(Attendance.lesson_id).label("marked"),
        )
        .select_from(Lesson)
        .join(Cohort, Cohort.id == Lesson.cohort_id)
        .join(Course, Course.id == Cohort.course_id)
        .join(Room, Room.id == Lesson.room_id)
        .outerjoin(
            Enrollment,
            and_(
                Enrollment.cohort_id == Lesson.cohort_id,
                Enrollment.status != EXPELLED,
                enrolled_by(),
            ),
        )
        .outerjoin(
            Attendance,
            and_(Attendance.lesson_id == Lesson.id, Attendance.enrollment_id == Enrollment.id),
        )
        .where(*where)
        .group_by(Lesson.id, Cohort.id, Course.name, Room.name)
    )


async def today_lessons(
    db: AsyncSession, cohort_where: list[ColumnElement[bool]], day: date
) -> list[tuple[Lesson, Cohort, str, str, int, int]]:
    rows = await db.execute(
        lesson_marks_query([*cohort_where, Lesson.lesson_date == day, ~Lesson.cancelled])
        .where(Cohort.status != "отменён")
        .order_by(Lesson.starts_at, Cohort.code)
    )
    return [tuple(r) for r in rows.all()]


def _unfilled_query(cohort_where: list[ColumnElement[bool]], now: datetime) -> Any:
    return (
        lesson_marks_query(
            [
                *cohort_where,
                held_lesson(now),
                Lesson.starts_at >= now - timedelta(days=UNFILLED_DAYS),
                Cohort.status != "отменён",
            ]
        )
        .having(func.count(Enrollment.id) > func.count(Attendance.lesson_id))
        .order_by(Lesson.starts_at, Cohort.code)
    )


async def unfilled_lessons(
    db: AsyncSession, cohort_where: list[ColumnElement[bool]], *, now: datetime | None = None
) -> list[tuple[Lesson, Cohort, str, str, int, int]]:
    """#21: held lessons of the last 30 days where somebody is still unmarked, oldest first."""
    rows = await db.execute(_unfilled_query(cohort_where, now or _now()))
    return [tuple(r) for r in rows.all()]


async def unfilled_top(
    db: AsyncSession,
    cohort_where: list[ColumnElement[bool]],
    limit: int,
    *,
    now: datetime | None = None,
) -> tuple[int, list[tuple[Lesson, Cohort, str, str, int, int]]]:
    """How many unfilled lessons there are, and the first `limit` of them: one query that
    returns only those rows (the dashboard shows a count and five lines)."""
    rows = (
        await db.execute(
            _unfilled_query(cohort_where, now or _now())
            .add_columns(func.count().over().label("n"))
            .limit(limit)
        )
    ).all()
    if rows:
        return int(rows[0][-1]), [tuple(r[:-1]) for r in rows]
    return 0, []
