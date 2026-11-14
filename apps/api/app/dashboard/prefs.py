"""`/api/v1/me/preferences/dashboard`: the signed-in user's own dashboard layout (which cards, in
which order). Own row only: the path names no user, so there is nobody else's row to reach.

No row yet = the role's default layout at version 0. The first save creates the row (it must say
version 0), later saves name the version they loaded (`X-Record-Version`, 409 `stale_version`).
Unknown ids, and cards the user may not have, are dropped on save and ignored on read.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.audit.log import record
from app.auth.deps import CurrentUser, Principal, require_csrf_header
from app.core import clock
from app.core.db import DB
from app.core.errors import FORBIDDEN, STALE_VERSION, DomainError
from app.core.versioning import Version, check_version
from app.dashboard.catalog import available, clean, resolve
from app.models import UserPref

router = APIRouter(
    prefix="/api/v1/me/preferences/dashboard",
    tags=["preferences"],
    dependencies=[Depends(require_csrf_header)],
)

CardId = Annotated[str, StringConstraints(max_length=40)]


class LayoutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: Annotated[list[CardId], Field(max_length=40)] = []
    hidden: Annotated[list[CardId], Field(max_length=40)] = []
    reset: bool = False


def _out(p: Principal, row: UserPref | None) -> dict[str, Any]:
    stored = row.dashboard if row else {}
    return {
        "cards": resolve(p, stored),
        "is_default": not stored,
        "version": row.version if row else 0,
    }


@router.get("")
async def get_layout(p: CurrentUser, db: DB) -> dict[str, Any]:
    return _out(p, await db.get(UserPref, p.id))


@router.put("")
async def put_layout(body: LayoutIn, version: Version, p: CurrentUser, db: DB) -> dict[str, Any]:
    if not available(p):  # an instructor (or a role with nothing to show) has no dashboard
        raise DomainError(FORBIDDEN, section="dashboard", level="view")
    new: dict[str, Any] = {} if body.reset else clean(p, body.order, body.hidden)
    action = "dashboard_pref.reset" if body.reset else "dashboard_pref.update"
    row = await db.get(UserPref, p.id)
    if row is None:
        if version != 0:
            raise DomainError(STALE_VERSION, version=0, current=_out(p, None))
        created = await db.execute(
            pg_insert(UserPref).values(user_id=p.id, dashboard=new).on_conflict_do_nothing()
        )
        if created.rowcount == 0:  # type: ignore[attr-defined]  # a parallel first save won
            row = await db.get(UserPref, p.id)
            raise DomainError(
                STALE_VERSION, version=row.version if row else 1, current=_out(p, row)
            )
        await record(db, p.id, action, "user_pref", p.id, {})
        return _out(p, await db.get(UserPref, p.id, populate_existing=True))

    async def current() -> dict[str, Any]:
        return _out(p, row)

    await check_version(db, row, version, "user_pref", current, changes={"dashboard": new})
    if row.dashboard != new:
        row.dashboard = new
        row.updated_at = clock.now()
        await db.flush()
        await record(db, p.id, action, "user_pref", p.id, {})
    return _out(p, row)
