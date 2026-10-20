"""The one place that defines and computes the numbers (SPEC «Метрики»). Every endpoint that
returns a count, a fill or a student status gets it from here; lists filter with the same
expressions, so a list and a number can never disagree (#3, #22).

Definitions:
- enrolled (cohort fill) = enrollments not «отчислен»; fill = enrolled / capacity.
- student status (one per student, precedence): активный = has an active enrollment; else
  выпускник = has a graduate enrollment; else отчислен = has an expelled one; else
  «без зачисления» (no enrollment, or only «завершил»).
- active cohort = status «активный».
"""

import uuid
from typing import Any

from sqlalchemy import ColumnElement, case, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Cohort, Enrollment, Student

NO_ENROLLMENT = "без зачисления"
STUDENT_STATUSES = ("активный", "выпускник", "отчислен", NO_ENROLLMENT)
COHORT_STATUSES = ("набор", "активный", "завершён", "отменён")


def student_status_expr() -> ColumnElement[str]:
    """SQL expression of a student's status, usable in select, where and group by."""

    def has(status: str) -> ColumnElement[bool]:
        return exists().where(Enrollment.student_id == Student.id, Enrollment.status == status)

    return case(
        (has("активный"), "активный"),
        (has("выпускник"), "выпускник"),
        (has("отчислен"), "отчислен"),
        else_=NO_ENROLLMENT,
    )


async def student_statuses(db: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = await db.execute(select(Student.id, student_status_expr()).where(Student.id.in_(ids)))
    return {i: s for i, s in rows.all()}


async def cohort_enrolled(db: AsyncSession, cohort_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Enrolled count per cohort (cohorts without enrollments report 0)."""
    if not cohort_ids:
        return {}
    rows = await db.execute(
        select(Enrollment.cohort_id, func.count())
        .where(Enrollment.cohort_id.in_(cohort_ids), Enrollment.status != "отчислен")
        .group_by(Enrollment.cohort_id)
    )
    counts = {cid: n for cid, n in rows.all()}
    return {cid: counts.get(cid, 0) for cid in cohort_ids}


def fill_of(enrolled: int, capacity: int) -> dict[str, Any]:
    return {"enrolled": enrolled, "capacity": capacity}


async def cohort_fill(db: AsyncSession, cohorts: list[Cohort]) -> dict[uuid.UUID, dict[str, Any]]:
    enrolled = await cohort_enrolled(db, [c.id for c in cohorts])
    return {c.id: fill_of(enrolled[c.id], c.capacity) for c in cohorts}


async def student_counts(db: AsyncSession, where: list[ColumnElement[bool]]) -> dict[str, int]:
    """Students by status (all four keys always present) and the total."""
    status = student_status_expr().label("status")
    rows = await db.execute(
        select(status, func.count()).select_from(Student).where(*where).group_by(status)
    )
    counts = dict.fromkeys(STUDENT_STATUSES, 0)
    counts.update({s: n for s, n in rows.all()})
    counts["всего"] = sum(counts[s] for s in STUDENT_STATUSES)
    return counts


async def cohort_counts(db: AsyncSession, where: list[ColumnElement[bool]]) -> dict[str, int]:
    rows = await db.execute(
        select(Cohort.status, func.count()).where(*where).group_by(Cohort.status)
    )
    counts = dict.fromkeys(COHORT_STATUSES, 0)
    counts.update({s: n for s, n in rows.all()})
    counts["всего"] = sum(counts[s] for s in COHORT_STATUSES)
    return counts


async def education_summary(
    db: AsyncSession,
    cohort_where: list[ColumnElement[bool]],
    student_where: list[ColumnElement[bool]],
) -> dict[str, Any]:
    cohorts = await cohort_counts(db, cohort_where)
    return {
        "active_cohorts": cohorts["активный"],
        "cohorts": cohorts,
        "students": await student_counts(db, student_where),
    }


from app.metrics.attendance import (  # noqa: E402
    attendance_score,
    enrollment_attendance,
    enrollment_results,
    grade_total,
    has_marks,
    passed,
    today_lessons,
    unfilled_lessons,
)

__all__ = [
    "attendance_score",
    "cohort_counts",
    "cohort_enrolled",
    "cohort_fill",
    "education_summary",
    "enrollment_attendance",
    "enrollment_results",
    "fill_of",
    "grade_total",
    "has_marks",
    "passed",
    "student_counts",
    "student_statuses",
    "today_lessons",
    "unfilled_lessons",
]
