"""The audit log, newest first, each entry as a Russian sentence (`sentences.py`).

A branch-bound user sees their branch's entries only. Filters: period, section, branch, user,
action, text. Each entry carries a `link` (entity type + id) when the entity still exists and
the reader may open it.

Money is shown only with the section that shows it elsewhere: payments and payouts are not
listed at all, rates and budgets are cut out of the diffs (and the text search) without
`instructors` / `marketing` view.
"""

import json
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import ColumnElement, Text, cast, func, or_, select
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.sentences import (
    ACTIONS,
    AUTH_LABEL,
    REFS,
    SECTION_ENTITIES,
    TABLES,
    TZ,
    Entry,
    section_of,
    sentence,
)
from app.auth.deps import Principal, require, require_csrf_header
from app.core.db import DB
from app.core.paging import Page, PageSize
from app.education.scope import cohort_filters, student_filters
from app.export import MAX_ROWS, Col, xlsx_response
from app.models import (
    AppUser,
    AuditLog,
    Branch,
    Campaign,
    Cohort,
    Course,
    Enrollment,
    Lesson,
    Role,
    Room,
    Student,
)
from app.permissions import SECTIONS, allows

# the section whose view right opens the page of an entity
LINK_SECTION = {
    "student": "students",
    "cohort": "cohorts",
    "lesson": "cohorts",
    "enrollment": "cohorts",
    "room": "rooms",
    "course": "rooms",
    "app_user": "users",
    "role": "users",
}


# money in the log: whole entities and single diff fields, each behind its section's view
MONEY_ENTITIES = {"payment": "payments", "instructor_payout": "instructors"}
MONEY_FIELDS = {
    "instructor_rate": "instructors",
    "default_rate": "instructors",
    "budget": "marketing",
}


def _hidden_fields(p: Principal) -> list[str]:
    return [f for f, s in MONEY_FIELDS.items() if not allows(p.level(s), "view")]


def _visible(diff: dict[str, Any], hidden: list[str]) -> dict[str, Any]:
    return {k: v for k, v in diff.items() if k not in hidden} if hidden else diff


# lessons and enrollments have no page of their own: they open their cohort
PAGE_ENTITY = {"lesson": "cohort", "enrollment": "cohort"}


def _uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def _refs(entity: str, entity_id: str | None, diff: dict[str, Any]) -> set[uuid.UUID]:
    """Ids a row mentions: the old/new values of its reference fields."""
    found: set[Any] = set()
    for field in REFS & diff.keys():
        change = diff[field]
        found.update(change if isinstance(change, list) else [change])
    filters = diff.get("filters")  # an Excel export: the ids its filters name
    if isinstance(filters, dict):
        found.update(v for k, v in filters.items() if k in REFS)
    return {u for u in map(_uuid, found) if u is not None}


async def _names(db: AsyncSession, ids: set[uuid.UUID]) -> dict[str, str]:
    """{id: display name} over users, roles, branches, rooms and courses: one IN query each
    per page, no N+1."""
    if not ids:
        return {}
    names: dict[str, str] = {}
    for model, column in (
        (AppUser, AppUser.full_name),
        (Role, Role.name),
        (Branch, Branch.name),
        (Room, Room.name),
        (Course, Course.name),
        (Campaign, Campaign.name),
    ):
        result = await db.execute(select(model.id, column).where(model.id.in_(ids)))
        names.update({str(i): n for i, n in result.all()})
    return names


async def _links(
    db: AsyncSession, p: Principal, rows: list[AuditLog]
) -> dict[int, dict[str, str] | None]:
    """audit id -> {entity, id} of the page to open, or None: the entity is gone, outside the
    reader's branch or cohorts, or the reader may not view that section."""
    wanted: dict[str, set[uuid.UUID]] = {}
    for a in rows:
        eid = _uuid(a.entity_id)
        if a.entity in LINK_SECTION and eid and allows(p.level(LINK_SECTION[a.entity]), "view"):
            wanted.setdefault(a.entity, set()).add(eid)
    # (entity, id) -> id of the page it opens (a lesson or enrollment opens its cohort)
    alive: dict[tuple[str, uuid.UUID], uuid.UUID] = {}

    async def fetch(entity: str, query: Any) -> None:
        for row_id, page_id in (await db.execute(query)).all():
            alive[(entity, row_id)] = page_id

    def own_branch(column: Any) -> list[ColumnElement[bool]]:
        return [column == p.branch_id] if p.branch_id is not None else []

    if ids := wanted.get("student"):
        stmt = select(Student.id, Student.id).where(Student.id.in_(ids), *student_filters(p))
        await fetch("student", stmt)
    if ids := wanted.get("cohort"):
        stmt = select(Cohort.id, Cohort.id).where(Cohort.id.in_(ids), *cohort_filters(p))
        await fetch("cohort", stmt)
    if ids := wanted.get("lesson"):
        stmt = (
            select(Lesson.id, Lesson.cohort_id)
            .join(Cohort, Cohort.id == Lesson.cohort_id)
            .where(Lesson.id.in_(ids), *cohort_filters(p))
        )
        await fetch("lesson", stmt)
    if ids := wanted.get("enrollment"):
        stmt = (
            select(Enrollment.id, Enrollment.cohort_id)
            .join(Cohort, Cohort.id == Enrollment.cohort_id)
            .where(Enrollment.id.in_(ids), *cohort_filters(p))
        )
        await fetch("enrollment", stmt)
    if ids := wanted.get("room"):
        await fetch(
            "room", select(Room.id, Room.id).where(Room.id.in_(ids), *own_branch(Room.branch_id))
        )
    if ids := wanted.get("course"):
        await fetch("course", select(Course.id, Course.id).where(Course.id.in_(ids)))
    if ids := wanted.get("app_user"):
        stmt = select(AppUser.id, AppUser.id).where(
            AppUser.id.in_(ids), *own_branch(AppUser.branch_id)
        )
        await fetch("app_user", stmt)
    if ids := wanted.get("role"):
        await fetch("role", select(Role.id, Role.id).where(Role.id.in_(ids)))
    out: dict[int, dict[str, str] | None] = {}
    for a in rows:
        eid = _uuid(a.entity_id)
        page_id = alive.get((a.entity, eid)) if eid else None
        out[a.id] = (
            {"entity": PAGE_ENTITY.get(a.entity, a.entity), "id": str(page_id)} if page_id else None
        )
    return out


def _day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=TZ).astimezone(UTC)


def _section_filter(section: str) -> ColumnElement[bool] | None:
    if section == "auth":
        return AuditLog.action.like("auth.%")
    if section in SECTION_ENTITIES:
        return AuditLog.entity.in_(SECTION_ENTITIES[section]) & AuditLog.action.not_like("auth.%")
    return None


def _like(text_: str) -> str:
    return f"%{text_.strip().replace('\\', '\\\\').replace('%', r'\%').replace('_', r'\_')}%"


router = APIRouter(
    prefix="/api/v1/audit", tags=["audit"], dependencies=[Depends(require_csrf_header)]
)


def _audit_where(
    p: Principal,
    user_id: uuid.UUID | None,
    section: str | None,
    branch_id: uuid.UUID | None,
    entity: str | None,
    entity_id: str | None,
    action: str | None,
    q: str | None,
    date_from: date | None,
    date_to: date | None,
) -> list[ColumnElement[bool]]:
    where: list[ColumnElement[bool]] = []
    if p.branch_id is not None:
        where.append(AuditLog.branch_id == p.branch_id)
    for money_entity, money_section in MONEY_ENTITIES.items():
        if not allows(p.level(money_section), "view"):
            where.append(AuditLog.entity != money_entity)
    hidden = _hidden_fields(p)
    if branch_id:
        where.append(AuditLog.branch_id == branch_id)
    if user_id:
        where.append(AuditLog.user_id == user_id)
    if section and (clause := _section_filter(section)) is not None:
        where.append(clause)
    if entity:
        where.append(AuditLog.entity == entity)
    if entity_id:
        where.append(AuditLog.entity_id == entity_id)
    if action:
        where.append(AuditLog.action == action)
    if date_from:
        where.append(AuditLog.at >= _day_start(date_from))
    if date_to:
        where.append(AuditLog.at < _day_start(date_to + timedelta(days=1)))
    if q and q.strip():
        like = _like(q)
        where.append(
            or_(
                AuditLog.label.ilike(like),
                AuditLog.entity_id.ilike(like),
                AppUser.full_name.ilike(like),
                AppUser.login.ilike(like),
                cast(
                    AuditLog.diff.op("-")(array(hidden, type_=Text)) if hidden else AuditLog.diff,
                    Text,
                ).ilike(like),
            )
        )
    return where


def _audit_select(where: list[ColumnElement[bool]]) -> Any:
    return (
        select(AuditLog, AppUser.full_name, AppUser.login, Branch.name)
        .outerjoin(AppUser, AppUser.id == AuditLog.user_id)
        .outerjoin(Branch, Branch.id == AuditLog.branch_id)
        .where(*where)
        .order_by(AuditLog.at.desc(), AuditLog.id.desc())
    )


def _audit_columns(hidden: list[str]) -> list[Col[Any]]:
    def data(r: Any) -> str | None:
        diff = _visible(r[0].diff, hidden)
        return json.dumps(diff, ensure_ascii=False) if diff else None

    return [
        Col("Время", lambda r: r[0].at, "datetime"),
        Col("Кто", lambda r: r[1] or "Система"),
        Col("Логин", lambda r: r[2]),
        Col("Филиал", lambda r: r[3]),
        Col("Действие", lambda r: " ".join(ACTIONS.get(r[0].action, (r[0].action,)))),
        Col("Событие", lambda r: r[0].label),
        Col("Объект", lambda r: TABLES.get(r[0].entity, r[0].entity)),
        Col("ID объекта", lambda r: r[0].entity_id),
        Col("Данные", data),
    ]


@router.get("/export")
async def export_audit(
    p: Annotated[Principal, require("audit", "view")],
    db: DB,
    user_id: uuid.UUID | None = None,
    section: str | None = None,
    branch_id: uuid.UUID | None = None,
    entity: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Response:
    where = _audit_where(
        p, user_id, section, branch_id, entity, entity_id, action, q, date_from, date_to
    )
    rows = (await db.execute(_audit_select(where).limit(MAX_ROWS + 1))).all()
    return await xlsx_response(
        db,
        p,
        entity="audit_log",
        slug="zhurnal",
        title="Журнал",
        columns=_audit_columns(_hidden_fields(p)),
        rows=rows,
        filters={
            "user_id": user_id,
            "section": section,
            "branch_id": branch_id,
            "entity": entity,
            "entity_id": entity_id,
            "action": action,
            "q": q,
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@router.get("")
async def list_audit(
    p: Annotated[Principal, require("audit", "view")],
    db: DB,
    user_id: uuid.UUID | None = None,
    section: str | None = None,
    branch_id: uuid.UUID | None = None,
    entity: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: Page = 1,
    page_size: PageSize = 25,
) -> dict[str, Any]:
    where = _audit_where(
        p, user_id, section, branch_id, entity, entity_id, action, q, date_from, date_to
    )
    base = select(AuditLog).outerjoin(AppUser, AppUser.id == AuditLog.user_id).where(*where)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        await db.execute(_audit_select(where).limit(page_size).offset((page - 1) * page_size))
    ).all()
    hidden = _hidden_fields(p)
    diffs = {a.id: _visible(a.diff, hidden) for a, *_ in rows}
    refs: set[uuid.UUID] = set()
    for a, *_ in rows:
        refs |= _refs(a.entity, a.entity_id, diffs[a.id])
    names = await _names(db, refs)
    sections = {**SECTIONS, "auth": AUTH_LABEL}
    links = await _links(db, p, [a for a, *_ in rows])
    return {
        "names": names,
        "sections": sections,
        "items": [
            {
                "id": a.id,
                "at": a.at,
                "user_id": a.user_id,
                "user_name": name,
                "user_login": login,
                "branch_name": branch,
                "action": a.action,
                "section": section_of(a.entity, a.action),
                "entity": a.entity,
                "entity_id": a.entity_id,
                "text": sentence(
                    Entry(name, a.action, a.entity, a.label, diffs[a.id]), names, sections
                ),
                "link": links[a.id],
                "diff": diffs[a.id],
            }
            for a, name, login, branch in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
