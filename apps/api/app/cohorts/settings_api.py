"""Academy settings: `stale_days`, the days without attendance marks after which a cohort is
flagged, and `stale_auto_close` (off by default): whether the nightly job then closes it.
Everybody signed in reads them; only the superadmin changes them, versioned and audited."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import record
from app.auth.deps import CurrentUser, Principal, require_csrf_header
from app.core import clock
from app.core.db import DB
from app.core.errors import FORBIDDEN, DomainError
from app.core.versioning import Version, check_version
from app.metrics.stale import WARN_DAYS
from app.models import AcademySettings, AppUser

router = APIRouter(
    prefix="/api/v1", tags=["academy-settings"], dependencies=[Depends(require_csrf_header)]
)


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stale_days: Annotated[int, Field(ge=20, le=730)] | None = None
    stale_auto_close: bool | None = None


async def _row(db: AsyncSession) -> AcademySettings:
    return (await db.execute(select(AcademySettings))).scalar_one()


async def _out(db: AsyncSession, p: Principal, row: AcademySettings) -> dict[str, Any]:
    by = (
        await db.execute(select(AppUser.full_name).where(AppUser.id == row.updated_by))
    ).scalar_one_or_none()
    return {
        "stale_days": row.stale_days,
        "stale_auto_close": row.stale_auto_close,
        "warn_days": WARN_DAYS,
        "can_edit": p.is_superadmin,
        "version": row.version,
        "updated_at": row.updated_at,
        "updated_by_name": by,
    }


@router.get("/academy-settings")
async def get_settings(p: CurrentUser, db: DB) -> dict[str, Any]:
    return await _out(db, p, await _row(db))


@router.patch("/academy-settings")
async def update_settings(
    body: SettingsIn, version: Version, p: CurrentUser, db: DB
) -> dict[str, Any]:
    if not p.is_superadmin:
        raise DomainError(FORBIDDEN, section="academy_settings", level="superadmin")
    row = await _row(db)
    changes = body.model_dump(exclude_none=True)
    await check_version(
        db, row, version, "academy_settings", lambda: _out(db, p, row), changes=changes
    )
    diff = {k: [getattr(row, k), v] for k, v in changes.items() if getattr(row, k) != v}
    if diff:
        for k, (_, v) in diff.items():
            setattr(row, k, v)
        row.updated_by, row.updated_at = p.id, clock.now()
        await db.flush()
        await record(
            db,
            p.id,
            "academy_settings.update",
            "academy_settings",
            str(row.id),
            diff,
            label="настройки академии",
        )
    return await _out(db, p, row)
