"""Branches (read-only in stage 0): the list a signed-in user may pick from."""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.auth.deps import CurrentUser, require_csrf_header
from app.core.db import DB
from app.models import Branch

router = APIRouter(
    prefix="/api/v1/branches", tags=["branches"], dependencies=[Depends(require_csrf_header)]
)


@router.get("")
async def list_branches(p: CurrentUser, db: DB) -> list[dict[str, Any]]:
    query = select(Branch).order_by(Branch.name)
    if p.branch_id is not None:
        query = query.where(Branch.id == p.branch_id)
    return [{"id": b.id, "name": b.name} for b in (await db.execute(query)).scalars()]
