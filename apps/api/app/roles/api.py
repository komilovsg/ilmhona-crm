"""Roles with a permission matrix (section -> view | change; no entry = no access).

`change` covers delete. The superadmin role is locked (no edit, no delete); seeded system roles
cannot be deleted. Roles are global, so a branch-bound user cannot write them, and nobody
grants rights they do not hold themselves.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import diff_of, record
from app.auth.deps import Principal, permissions_of, require, require_csrf_header
from app.core.db import DB
from app.core.errors import FORBIDDEN, NOT_FOUND, DomainError, errors
from app.models import AppUser, Role, RolePermission
from app.permissions import LEVELS, SECTIONS, SUPERADMIN_CODE
from app.users.errors import BRANCH_FORBIDDEN, ROLE_NOT_ASSIGNABLE

NAME_TAKEN = errors.define("name_taken", 409, "Name already used")
ROLE_IN_USE = errors.define("role_in_use", 409, "Role is assigned to users")
ROLE_LOCKED = errors.define("role_locked", 403, "The superadmin role cannot be changed")
ROLE_SYSTEM = errors.define("role_system", 403, "A system role cannot be deleted")
errors.on_constraint("role_name_key", NAME_TAKEN)

router = APIRouter(
    prefix="/api/v1/roles", tags=["roles"], dependencies=[Depends(require_csrf_header)]
)

View = Annotated[Principal, require("users", "view")]
Change = Annotated[Principal, require("users", "change")]

RoleName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class RoleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: RoleName
    permissions: dict[str, str] = {}

    @field_validator("permissions")
    @classmethod
    def _known(cls, value: dict[str, str]) -> dict[str, str]:
        for section, level in value.items():
            if section not in SECTIONS:
                raise ValueError(f"unknown section {section}")
            if level not in LEVELS:
                raise ValueError(f"unknown level {level}")
        return value


async def _out(db: AsyncSession, role: Role) -> dict[str, Any]:
    users = (
        await db.execute(
            select(func.count()).select_from(AppUser).where(AppUser.role_id == role.id)
        )
    ).scalar_one()
    return {
        "id": role.id,
        "name": role.name,
        "code": role.code,
        "is_system": role.is_system,
        "locked": role.code == SUPERADMIN_CODE,
        "permissions": await permissions_of(db, role),
        "users_count": users,
    }


async def _get(db: AsyncSession, role_id: uuid.UUID) -> Role:
    role = (await db.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()
    if role is None:
        raise DomainError(NOT_FOUND)
    return role


def _writer(p: Principal, permissions: dict[str, str]) -> None:
    if p.branch_id is not None:
        raise DomainError(BRANCH_FORBIDDEN)
    if not p.covers(permissions):
        raise DomainError(ROLE_NOT_ASSIGNABLE)


@router.get("/sections")
async def sections(_: View) -> list[dict[str, str]]:
    return [{"key": k, "label": v} for k, v in SECTIONS.items()]


@router.get("")
async def list_roles(p: View, db: DB) -> list[dict[str, Any]]:
    roles = (await db.execute(select(Role).order_by(Role.created_at, Role.name))).scalars().all()
    out = [await _out(db, r) for r in roles]
    for row in out:
        row["assignable"] = p.can_assign(row["code"], row["permissions"])
    return out


@router.get("/{role_id}")
async def get_role(role_id: uuid.UUID, _: View, db: DB) -> dict[str, Any]:
    return await _out(db, await _get(db, role_id))


@router.post("", status_code=201)
async def create_role(body: RoleIn, p: Change, db: DB) -> dict[str, Any]:
    _writer(p, body.permissions)
    role = Role(name=body.name)
    db.add(role)
    await db.flush()
    db.add_all(
        RolePermission(role_id=role.id, section=s, level=lvl) for s, lvl in body.permissions.items()
    )
    await db.flush()
    await record(
        db,
        p.id,
        "role.create",
        "role",
        role.id,
        {"name": [None, role.name], "permissions": diff_of({}, body.permissions)},
    )
    return await _out(db, role)


@router.put("/{role_id}")
async def update_role(role_id: uuid.UUID, body: RoleIn, p: Change, db: DB) -> dict[str, Any]:
    role = await _get(db, role_id)
    if role.code == SUPERADMIN_CODE:
        raise DomainError(ROLE_LOCKED)
    # Rights the role already has must be covered too, or a user could strip a role above them.
    _writer(p, {**await permissions_of(db, role), **body.permissions})
    before = await permissions_of(db, role)
    old_name = role.name
    role.name = body.name
    rows = (
        (await db.execute(select(RolePermission).where(RolePermission.role_id == role.id)))
        .scalars()
        .all()
    )
    for row in rows:
        if row.section not in body.permissions:
            await db.delete(row)
        else:
            row.level = body.permissions[row.section]
    have = {r.section for r in rows}
    db.add_all(
        RolePermission(role_id=role.id, section=s, level=lvl)
        for s, lvl in body.permissions.items()
        if s not in have
    )
    await db.flush()
    diff: dict[str, Any] = {}
    if old_name != role.name:
        diff["name"] = [old_name, role.name]
    perm_diff = diff_of(before, body.permissions)
    if perm_diff:
        diff["permissions"] = perm_diff
    await record(db, p.id, "role.update", "role", role.id, diff)
    return await _out(db, role)


@router.delete("/{role_id}", status_code=204)
async def delete_role(role_id: uuid.UUID, p: Change, db: DB) -> None:
    role = await _get(db, role_id)
    if role.code == SUPERADMIN_CODE:
        raise DomainError(ROLE_LOCKED)
    if role.is_system:
        raise DomainError(ROLE_SYSTEM)
    if p.branch_id is not None:
        raise DomainError(FORBIDDEN)
    _writer(p, await permissions_of(db, role))  # nobody removes a role above their own rights
    users = (
        await db.execute(
            select(func.count()).select_from(AppUser).where(AppUser.role_id == role.id)
        )
    ).scalar_one()
    if users:
        raise DomainError(ROLE_IN_USE, users_count=users)
    before = await permissions_of(db, role)
    await db.delete(role)
    await db.flush()
    await record(
        db,
        p.id,
        "role.delete",
        "role",
        role_id,
        {"name": [role.name, None], "permissions": diff_of(before, {})},
    )
