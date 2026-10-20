"""The audit log writer. Every write endpoint calls `record` in the same transaction as the
change, so both commit or fail together. No secrets (hashes, passwords) in a diff."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppUser, AuditLog, Cohort, Course, Enrollment, Lesson, Role, Room, Student

# diff field that holds the name of a row, per entity: the fallback when the row is gone (delete)
_NAME_FIELD = {
    "student": "full_name",
    "cohort": "code",
    "room": "name",
    "course": "name",
    "app_user": "full_name",
    "role": "name",
}
# entity -> (id column, name column)
_NAME_COLUMN = {
    "student": (Student.id, Student.full_name),
    "cohort": (Cohort.id, Cohort.code),
    "room": (Room.id, Room.name),
    "course": (Course.id, Course.name),
    "app_user": (AppUser.id, AppUser.full_name),
    "role": (Role.id, Role.name),
}


def _old(value: Any) -> Any:
    """Before-value of a `[old, new]` diff entry; a delete has the name in `old`."""
    return value[0] if isinstance(value, list) and value else value


async def _label(
    db: AsyncSession, entity: str, entity_id: UUID | str | None, diff: dict[str, Any]
) -> str | None:
    """The display name of the changed row (student name, cohort code, ...): stored with the entry
    because the row may be deleted or renamed by the time somebody reads the log."""
    try:
        row_id = UUID(str(entity_id))
    except ValueError:
        return str(entity_id) if entity_id else None
    if entity in _NAME_COLUMN:
        id_col, name_col = _NAME_COLUMN[entity]
        found = (await db.execute(select(name_col).where(id_col == row_id))).scalar_one_or_none()
        if found is not None:
            return str(found)
        old = _old(diff.get(_NAME_FIELD[entity]))
        return str(old) if old else None
    if entity == "lesson":
        lesson = (
            await db.execute(
                select(Cohort.code, Lesson.lesson_date)
                .join(Cohort, Cohort.id == Lesson.cohort_id)
                .where(Lesson.id == row_id)
            )
        ).first()
        return f"{lesson[0]}, {lesson[1]:%d.%m.%Y}" if lesson else None
    if entity == "enrollment":
        row = (
            await db.execute(
                select(Student.full_name, Cohort.code)
                .join(Enrollment, Enrollment.student_id == Student.id)
                .join(Cohort, Cohort.id == Enrollment.cohort_id)
                .where(Enrollment.id == row_id)
            )
        ).first()
        if row:
            return f"{row[0]} ({row[1]})"
        student, cohort = _old(diff.get("student")), _old(diff.get("cohort"))
        return f"{student} ({cohort})" if student and cohort else None
    return None


def _plain(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [_plain(v) for v in value]
    return value


def diff_of(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """{field: [old, new]} for the fields that changed (a creation is `before={}`)."""
    return {
        k: [_plain(before.get(k)), _plain(after.get(k))]
        for k in before.keys() | after.keys()
        if before.get(k) != after.get(k)
    }


async def record(
    db: AsyncSession,
    actor_id: UUID | None,
    action: str,
    entity: str,
    entity_id: UUID | str | None,
    diff: dict[str, Any] | None = None,
    *,
    branch_id: UUID | None = None,
    label: str | None = None,
) -> None:
    diff = _plain(diff or {})
    db.add(
        AuditLog(
            user_id=actor_id,
            action=action,
            entity=entity,
            entity_id=str(entity_id) if entity_id is not None else None,
            branch_id=branch_id,
            label=label or await _label(db, entity, entity_id, diff),
            diff=diff,
        )
    )
    await db.flush()
