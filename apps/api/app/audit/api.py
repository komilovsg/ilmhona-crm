"""The audit log, newest first. A branch-bound user sees their branch's entries only."""

import json
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select

from app.auth.deps import Principal, require, require_csrf_header
from app.core.db import DB
from app.export import MAX_ROWS, Col, xlsx_response
from app.models import AppUser, AuditLog, Branch, Role
from app.permissions import SECTIONS

REF_FIELDS = {"role_id", "branch_id", "user_id"}


def _uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def _refs(entity: str, entity_id: str | None, diff: dict[str, Any]) -> set[uuid.UUID]:
    """Ids a row mentions: its own target and the old/new values of reference fields."""
    found = {entity_id} if entity in ("app_user", "role") else set()
    for field in REF_FIELDS & diff.keys():
        change = diff[field]
        found.update(change if isinstance(change, list) else [change])
    return {u for u in map(_uuid, found) if u is not None}


async def _names(db: DB, ids: set[uuid.UUID]) -> dict[str, str]:
    """{id: display name} over users, roles and branches: three IN queries per page, no N+1."""
    if not ids:
        return {}
    names: dict[str, str] = {}
    for model, column in ((AppUser, AppUser.full_name), (Role, Role.name), (Branch, Branch.name)):
        result = await db.execute(select(model.id, column).where(model.id.in_(ids)))
        names.update({str(i): n for i, n in result.all()})
    return names


router = APIRouter(
    prefix="/api/v1/audit", tags=["audit"], dependencies=[Depends(require_csrf_header)]
)


def _audit_where(
    p: Principal,
    user_id: uuid.UUID | None,
    entity: str | None,
    entity_id: str | None,
    action: str | None,
    since: datetime | None,
    until: datetime | None,
) -> list[Any]:
    where: list[Any] = []
    if p.branch_id is not None:
        where.append(AuditLog.branch_id == p.branch_id)
    if user_id:
        where.append(AuditLog.user_id == user_id)
    if entity:
        where.append(AuditLog.entity == entity)
    if entity_id:
        where.append(AuditLog.entity_id == entity_id)
    if action:
        where.append(AuditLog.action == action)
    if since:
        where.append(AuditLog.at >= since)
    if until:
        where.append(AuditLog.at < until)
    return where


def _audit_select(where: list[Any]) -> Any:
    return (
        select(AuditLog, AppUser.full_name, AppUser.login)
        .outerjoin(AppUser, AppUser.id == AuditLog.user_id)
        .where(*where)
        .order_by(AuditLog.at.desc(), AuditLog.id.desc())
    )


AUDIT_COLUMNS: list[Col[Any]] = [
    Col("Время", lambda r: r[0].at, "datetime"),
    Col("Кто", lambda r: r[1] or "Система"),
    Col("Логин", lambda r: r[2]),
    Col("Действие", lambda r: r[0].action),
    Col("Объект", lambda r: r[0].entity),
    Col("ID объекта", lambda r: r[0].entity_id),
    Col("Данные", lambda r: json.dumps(r[0].diff, ensure_ascii=False) if r[0].diff else None),
]


@router.get("/export")
async def export_audit(
    p: Annotated[Principal, require("audit", "view")],
    db: DB,
    user_id: uuid.UUID | None = None,
    entity: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> Response:
    where = _audit_where(p, user_id, entity, entity_id, action, since, until)
    rows = (await db.execute(_audit_select(where).limit(MAX_ROWS + 1))).all()
    return await xlsx_response(
        db,
        p,
        entity="audit_log",
        slug="zhurnal",
        title="Журнал",
        columns=AUDIT_COLUMNS,
        rows=rows,
        filters={
            "user_id": user_id,
            "entity": entity,
            "entity_id": entity_id,
            "action": action,
            "since": since,
            "until": until,
        },
    )


@router.get("")
async def list_audit(
    p: Annotated[Principal, require("audit", "view")],
    db: DB,
    user_id: uuid.UUID | None = None,
    entity: str | None = None,
    entity_id: str | None = None,
    action: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> dict[str, Any]:
    where = _audit_where(p, user_id, entity, entity_id, action, since, until)
    total = (
        await db.execute(select(func.count()).select_from(AuditLog).where(*where))
    ).scalar_one()
    rows = (
        await db.execute(_audit_select(where).limit(page_size).offset((page - 1) * page_size))
    ).all()
    refs: set[uuid.UUID] = set()
    for a, _, _ in rows:
        refs |= _refs(a.entity, a.entity_id, a.diff)
    return {
        "names": await _names(db, refs),
        "sections": SECTIONS,
        "items": [
            {
                "id": a.id,
                "at": a.at,
                "user_id": a.user_id,
                "user_name": name,
                "user_login": login,
                "action": a.action,
                "entity": a.entity,
                "entity_id": a.entity_id,
                "diff": a.diff,
            }
            for a, name, login in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
