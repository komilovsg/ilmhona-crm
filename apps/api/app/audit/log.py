"""The audit log writer. Every write endpoint calls `record` in the same transaction as the
change, so both commit or fail together. No secrets (hashes, passwords) in a diff."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


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
) -> None:
    db.add(
        AuditLog(
            user_id=actor_id,
            action=action,
            entity=entity,
            entity_id=str(entity_id) if entity_id is not None else None,
            branch_id=branch_id,
            diff=_plain(diff or {}),
        )
    )
    await db.flush()
