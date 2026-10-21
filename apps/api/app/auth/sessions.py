"""Sessions = refresh-token families. «Мои устройства и сессии» on /profile and, for a
superadmin, the same list in a user's card. Ending a session revokes its family, and the access
token's `sid` stops working at once (deps._principal checks the family on every request).
Another user's session id answers 404."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import record
from app.auth.api import clear_cookies
from app.auth.deps import CurrentUser, Principal, require, require_csrf_header
from app.auth.devices import device_name
from app.core.db import DB
from app.core.errors import FORBIDDEN, NOT_FOUND, DomainError
from app.models import AppUser, RefreshToken

router = APIRouter(prefix="/api/v1", tags=["sessions"], dependencies=[Depends(require_csrf_header)])

_LIST = """
    SELECT family_id, min(created_at) AS created_at, max(last_used_at) AS last_used_at,
           (array_agg(user_agent ORDER BY created_at))[1] AS user_agent,
           bool_or(remember) AS remember
    FROM refresh_token
    WHERE user_id = :u
    GROUP BY family_id
    HAVING bool_and(revoked_at IS NULL) AND max(expires_at) > now()
    ORDER BY max(last_used_at) DESC
"""


async def list_sessions(
    db: AsyncSession, user_id: uuid.UUID, current: uuid.UUID | None
) -> list[dict[str, Any]]:
    rows = (await db.execute(text(_LIST), {"u": user_id})).mappings().all()
    return [
        {
            "id": r["family_id"],
            "device": device_name(r["user_agent"]),
            "created_at": r["created_at"],
            "last_used_at": r["last_used_at"],
            "remember": r["remember"],
            "current": r["family_id"] == current,
        }
        for r in rows
    ]


async def _end(db: AsyncSession, user_id: uuid.UUID, family_ids: list[uuid.UUID]) -> int:
    """Revoke those of the user's live families that are listed; returns how many were live."""
    live = {s["id"] for s in await list_sessions(db, user_id, None)}
    targets = [f for f in family_ids if f in live]
    if targets:
        await db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.family_id.in_(targets),
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
    return len(targets)


@router.get("/auth/sessions")
async def my_sessions(p: CurrentUser, db: DB) -> list[dict[str, Any]]:
    return await list_sessions(db, p.id, p.session_id)


@router.delete("/auth/sessions/{session_id}", status_code=204)
async def end_my_session(session_id: uuid.UUID, p: CurrentUser, response: Response, db: DB) -> None:
    if not await _end(db, p.id, [session_id]):
        raise DomainError(NOT_FOUND)
    await record(db, p.id, "auth.session_end", "app_user", p.id, branch_id=p.branch_id)
    if session_id == p.session_id:
        clear_cookies(response)


@router.post("/auth/sessions/end-others")
async def end_other_sessions(p: CurrentUser, db: DB) -> dict[str, int]:
    others = [s["id"] for s in await list_sessions(db, p.id, p.session_id) if not s["current"]]
    n = await _end(db, p.id, others)
    if n:
        await record(
            db,
            p.id,
            "auth.session_end_others",
            "app_user",
            p.id,
            {"count": [None, n]},
            branch_id=p.branch_id,
        )
    return {"ended": n}


# --- superadmin: any user's sessions, from the user card ---------------------------------

Change = Annotated[Principal, require("users", "change")]


async def _target(db: AsyncSession, p: Principal, user_id: uuid.UUID) -> AppUser:
    if not p.is_superadmin:
        raise DomainError(FORBIDDEN, section="users", level="superadmin")
    u = await db.get(AppUser, user_id)
    if u is None:
        raise DomainError(NOT_FOUND)
    return u


@router.get("/users/{user_id}/sessions")
async def user_sessions(user_id: uuid.UUID, p: Change, db: DB) -> list[dict[str, Any]]:
    u = await _target(db, p, user_id)
    return await list_sessions(db, u.id, None)


@router.delete("/users/{user_id}/sessions/{session_id}", status_code=204)
async def end_user_session(user_id: uuid.UUID, session_id: uuid.UUID, p: Change, db: DB) -> None:
    u = await _target(db, p, user_id)
    if not await _end(db, u.id, [session_id]):
        raise DomainError(NOT_FOUND)
    await record(db, p.id, "user.session_end", "app_user", u.id, branch_id=u.branch_id)
