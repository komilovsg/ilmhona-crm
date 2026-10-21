"""Edit conflicts (#25): every update names the version of the row it loaded.

The client sends it in `If-Match` (the `version` of the record it got). `check_version` locks
the row, compares, and on a mismatch answers 409 `stale_version` with the last change from the
audit log and the current record, so the screen can show both and re-apply the user's edit.
The version itself is bumped by a database trigger on any real change of the row.
"""

import inspect
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    BAD_REQUEST,
    NOT_FOUND,
    STALE_VERSION,
    VERSION_REQUIRED,
    DomainError,
)
from app.models import AppUser, AuditLog, Versioned


def _if_match(if_match: Annotated[str | None, Header()] = None) -> int:
    if if_match is None:
        raise DomainError(VERSION_REQUIRED)
    try:
        return int(if_match.strip().removeprefix("W/").strip('"'))
    except ValueError:
        raise DomainError(BAD_REQUEST) from None


Version = Annotated[int, Depends(_if_match)]


async def _last_change(db: AsyncSession, entity: str, entity_id: object) -> dict[str, Any]:
    row = (
        await db.execute(
            select(AuditLog.at, AppUser.full_name)
            .outerjoin(AppUser, AppUser.id == AuditLog.user_id)
            .where(AuditLog.entity == entity, AuditLog.entity_id == str(entity_id))
            .order_by(AuditLog.at.desc(), AuditLog.id.desc())
            .limit(1)
        )
    ).first()
    return {"changed_by": row[1], "changed_at": row[0]} if row else {}


async def lock(db: AsyncSession, row: Versioned) -> None:
    """Re-read `row` under a row lock; a row a parallel request deleted meanwhile is a 404."""
    try:
        await db.refresh(row, with_for_update=True)
    except InvalidRequestError:
        raise DomainError(NOT_FOUND) from None


async def check_version[T: Versioned](
    db: AsyncSession,
    row: T,
    expected: int,
    entity: str,
    current: Callable[[], Awaitable[dict[str, Any]] | dict[str, Any]],
) -> T:
    """Lock `row` (a concurrent edit waits here, then sees the new version) and compare. Call it
    right after loading, before changing anything: it re-reads the row."""
    await lock(db, row)
    if row.version != expected:
        record = current()
        if inspect.isawaitable(record):
            record = await record
        raise DomainError(
            STALE_VERSION,
            version=row.version,
            current=record,
            **await _last_change(db, entity, getattr(row, "id", None)),
        )
    return row


def touch(row: Versioned) -> None:
    """Bump a row whose change lives elsewhere (role permissions): the trigger sees a changed
    row and moves the version on."""
    row.version = row.version + 1
