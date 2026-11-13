"""Private notes. Every query is filtered by the owner: a note of someone else (another
superadmin included) answers 404, exists nowhere in a list. For now only the superadmin has them.

The audit log never carries the text of a note, only that one was added, changed or deleted.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import record
from app.auth.deps import Principal, require_csrf_header
from app.core import clock
from app.core.db import DB
from app.core.errors import NOT_FOUND, VALIDATION_FAILED, DomainError, errors
from app.core.versioning import Version, check_version
from app.goals.api import Superadmin
from app.models import Cohort, Course, Goal, Note

errors.on_constraint("note_text_check", VALIDATION_FAILED)

router = APIRouter(
    prefix="/api/v1/notes", tags=["notes"], dependencies=[Depends(require_csrf_header)]
)

NoteText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
LIST_CAP = 200


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoteCreate(Strict):
    text: NoteText
    goal_id: uuid.UUID | None = None
    course_id: uuid.UUID | None = None
    cohort_id: uuid.UUID | None = None


class NoteUpdate(Strict):
    text: NoteText | None = None
    goal_id: uuid.UUID | None = None
    course_id: uuid.UUID | None = None
    cohort_id: uuid.UUID | None = None


def _select(p: Principal) -> Any:
    return (
        select(Note, Goal.title, Course.name, Cohort.code)
        .outerjoin(Goal, Goal.id == Note.goal_id)
        .outerjoin(Course, Course.id == Note.course_id)
        .outerjoin(Cohort, Cohort.id == Note.cohort_id)
        .where(Note.owner_id == p.id)
    )


def _out(row: Any) -> dict[str, Any]:
    n, goal_title, course_name, cohort_code = row
    return {
        "id": n.id,
        "text": n.text,
        "goal_id": n.goal_id,
        "goal_title": goal_title,
        "course_id": n.course_id,
        "course_name": course_name,
        "cohort_id": n.cohort_id,
        "cohort_code": cohort_code,
        "version": n.version,
        "created_at": n.created_at,
        "updated_at": n.updated_at,
    }


async def _detail(db: AsyncSession, p: Principal, note_id: uuid.UUID) -> dict[str, Any]:
    return _out((await db.execute(_select(p).where(Note.id == note_id))).one())


async def _load(db: AsyncSession, p: Principal, note_id: uuid.UUID) -> Note:
    note = (
        await db.execute(select(Note).where(Note.id == note_id, Note.owner_id == p.id))
    ).scalar_one_or_none()
    if note is None:
        raise DomainError(NOT_FOUND)
    return note


async def _check_links(
    db: AsyncSession,
    goal_id: uuid.UUID | None = None,
    course_id: uuid.UUID | None = None,
    cohort_id: uuid.UUID | None = None,
) -> None:
    for model, value in ((Goal, goal_id), (Course, course_id), (Cohort, cohort_id)):
        if (
            value is not None
            and not (await db.execute(select(model.id).where(model.id == value))).first()
        ):
            raise DomainError(NOT_FOUND)


@router.get("")
async def list_notes(
    p: Superadmin,
    db: DB,
    goal_id: uuid.UUID | None = None,
    course_id: uuid.UUID | None = None,
    cohort_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=LIST_CAP)] = 50,
) -> dict[str, Any]:
    stmt = _select(p)
    if goal_id:
        stmt = stmt.where(Note.goal_id == goal_id)
    if course_id:
        stmt = stmt.where(Note.course_id == course_id)
    if cohort_id:
        stmt = stmt.where(Note.cohort_id == cohort_id)
    if q and q.strip():
        like = f"%{q.strip().replace('\\', '\\\\').replace('%', r'\%').replace('_', r'\_')}%"
        stmt = stmt.where(Note.text.ilike(like))
    rows = (await db.execute(stmt.order_by(Note.created_at.desc(), Note.id).limit(limit))).all()
    return {"items": [_out(r) for r in rows]}


@router.post("", status_code=201)
async def create_note(body: NoteCreate, p: Superadmin, db: DB) -> dict[str, Any]:
    await _check_links(db, body.goal_id, body.course_id, body.cohort_id)
    note = Note(
        owner_id=p.id,
        text=body.text,
        goal_id=body.goal_id,
        course_id=body.course_id,
        cohort_id=body.cohort_id,
    )
    db.add(note)
    await db.flush()
    await record(db, p.id, "note.create", "note", note.id, {})
    return await _detail(db, p, note.id)


@router.patch("/{note_id}")
async def update_note(
    note_id: uuid.UUID, body: NoteUpdate, version: Version, p: Superadmin, db: DB
) -> dict[str, Any]:
    note = await _load(db, p, note_id)

    async def current() -> dict[str, Any]:
        return await _detail(db, p, note_id)

    await check_version(
        db, note, version, "note", current, changes=body.model_dump(exclude_unset=True)
    )
    sent = body.model_fields_set
    links = {f: getattr(body, f) for f in ("goal_id", "course_id", "cohort_id") if f in sent}
    await _check_links(db, **links)
    if "text" in sent and body.text:
        note.text = body.text
    for field, value in links.items():
        setattr(note, field, value)
    note.updated_at = clock.now()
    await db.flush()
    await record(db, p.id, "note.update", "note", note.id, {})
    return await _detail(db, p, note_id)


@router.delete("/{note_id}", status_code=204)
async def delete_note(note_id: uuid.UUID, p: Superadmin, db: DB) -> Response:
    note = await _load(db, p, note_id)
    await db.delete(note)
    await db.flush()
    await record(db, p.id, "note.delete", "note", note_id, {})
    return Response(status_code=204)
