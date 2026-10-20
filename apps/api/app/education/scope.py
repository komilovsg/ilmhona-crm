"""Who sees which education rows, and who may write.

- Branch scope: a branch-bound user sees their branch only (404 for the rest).
- Role instructor: sees only cohorts where they are the instructor (others 404, also their
  lessons and enrollments) and can never write (#24), whatever the rights matrix says.
"""

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy import ColumnElement, exists, select

from app.auth.deps import CurrentUser, Principal
from app.core.errors import FORBIDDEN, NOT_FOUND, VALIDATION_FAILED, DomainError
from app.models import Cohort, Enrollment, Student
from app.permissions import allows
from app.users.errors import BRANCH_FORBIDDEN

INSTRUCTOR_CODE = "instructor"


def is_instructor(p: Principal) -> bool:
    return p.role.code == INSTRUCTOR_CODE


def require_any(*sections: str) -> object:
    """Read access to reference data (rooms, courses): view on any of `sections`."""

    async def dependency(p: CurrentUser) -> Principal:
        if not any(allows(p.level(s), "view") for s in sections):
            raise DomainError(FORBIDDEN, section=sections[0], level="view")
        return p

    return Depends(dependency)


def writer(section: str) -> object:
    """`change` on `section`, and not an instructor (#24)."""

    async def dependency(p: CurrentUser) -> Principal:
        if not allows(p.level(section), "change") or is_instructor(p):
            raise DomainError(FORBIDDEN, section=section, level="change")
        return p

    return Depends(dependency)


AnyReader = Annotated[Principal, require_any("rooms", "cohorts", "students")]


def cohort_filters(p: Principal) -> list[ColumnElement[bool]]:
    """Where-clauses that keep only the cohorts this user may see."""
    where: list[ColumnElement[bool]] = []
    if p.branch_id is not None:
        where.append(Cohort.branch_id == p.branch_id)
    if is_instructor(p):
        where.append(Cohort.instructor_id == p.id)
    return where


def student_filters(p: Principal) -> list[ColumnElement[bool]]:
    where: list[ColumnElement[bool]] = []
    if p.branch_id is not None:
        where.append(Student.branch_id == p.branch_id)
    if is_instructor(p):
        where.append(
            exists().where(
                Enrollment.student_id == Student.id,
                Enrollment.cohort_id.in_(select(Cohort.id).where(Cohort.instructor_id == p.id)),
            )
        )
    return where


def check_cohort_visible(p: Principal, cohort: Cohort) -> None:
    """404 for a cohort of another branch or (instructor) someone else's."""
    p.check_scope(cohort.branch_id)
    if is_instructor(p) and cohort.instructor_id != p.id:
        raise DomainError(NOT_FOUND)


def branch_for_write(p: Principal, branch_id: uuid.UUID | None) -> uuid.UUID:
    """The branch a new row goes to: a branch-bound user's own (another one is 403); an
    unbound user must name one."""
    if p.branch_id is not None:
        if branch_id not in (None, p.branch_id):
            raise DomainError(BRANCH_FORBIDDEN)
        return p.branch_id
    if branch_id is None:
        raise DomainError(VALIDATION_FAILED)
    return branch_id
