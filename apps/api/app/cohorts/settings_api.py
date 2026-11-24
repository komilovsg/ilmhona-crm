"""Academy settings: `stale_days`, the days without attendance marks after which the nightly job
closes an активный cohort. Everybody signed in reads it (the warning on a cohort names the
closing date); only the superadmin changes it, versioned and audited."""

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
    stale_days: Annotated[int, Field(ge=20, le=730)]


async def _row(db: AsyncSession) -> AcademySettings:
    return (await db.execute(select(AcademySettings))).scalar_one()


async def _out(db: AsyncSession, p: Principal, row: AcademySettings) -> dict[str, Any]:
    by = (
        await db.execute(select(AppUser.full_name).where(AppUser.id == row.updated_by))
    ).scalar_one_or_none()
    return {
        "stale_days": row.stale_days,
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
    await check_version(
        db,
        row,
        version,
        "academy_settings",
        lambda: _out(db, p, row),
        changes={"stale_days": body.stale_days},
    )
    before = row.stale_days
    if before != body.stale_days:
        row.stale_days = body.stale_days
        row.updated_by, row.updated_at = p.id, clock.now()
        await db.flush()
        await record(
            db,
            p.id,
            "academy_settings.update",
            "academy_settings",
            str(row.id),
            {"stale_days": [before, body.stale_days]},
            label="настройки академии",
        )
    return await _out(db, p, row)
