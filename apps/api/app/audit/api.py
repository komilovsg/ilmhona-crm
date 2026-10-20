"""The audit log, newest first. A branch-bound user sees their branch's entries only."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.auth.deps import Principal, require, require_csrf_header
from app.core.db import DB
from app.models import AppUser, AuditLog

router = APIRouter(
    prefix="/api/v1/audit", tags=["audit"], dependencies=[Depends(require_csrf_header)]
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
    where = []
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
    total = (
        await db.execute(select(func.count()).select_from(AuditLog).where(*where))
    ).scalar_one()
    rows = (
        await db.execute(
            select(AuditLog, AppUser.full_name, AppUser.login)
            .outerjoin(AppUser, AppUser.id == AuditLog.user_id)
            .where(*where)
            .order_by(AuditLog.at.desc(), AuditLog.id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).all()
    return {
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
