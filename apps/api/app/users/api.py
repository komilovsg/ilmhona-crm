"""Users: list, create, edit, activate / reset password, deactivate, delete.

Rights: `users` view for reads, `users` change for everything else (change covers delete).
Branch scope: a user bound to a branch sees and edits that branch's users only (404 otherwise).
Nobody gives or touches a role with more rights than their own.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import diff_of, record
from app.auth.api import revoke_sessions
from app.auth.deps import Principal, permissions_of, require, require_csrf_header
from app.core.config import settings
from app.core.db import DB
from app.core.errors import NOT_FOUND, DomainError
from app.core.paging import Page, PageSize
from app.core.security import hash_password, temp_password
from app.core.versioning import Version, check_version
from app.export import MAX_ROWS, Col, xlsx_response
from app.models import AppUser, Branch, Role
from app.permissions import SUPERADMIN_CODE
from app.users.errors import (
    BRANCH_FORBIDDEN,
    CANNOT_DEACTIVATE_SELF,
    LAST_SUPERADMIN,
    ROLE_NOT_ASSIGNABLE,
    USER_IN_USE,
)

router = APIRouter(
    prefix="/api/v1/users", tags=["users"], dependencies=[Depends(require_csrf_header)]
)

View = Annotated[Principal, require("users", "view")]
Change = Annotated[Principal, require("users", "change")]

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
LoginText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=64, pattern=r"^[\w.@-]+$"),
]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UserCreate(Strict):
    login: LoginText
    full_name: Text
    phone: Phone | None = None
    email: Text | None = None
    branch_id: uuid.UUID | None = None
    role_id: uuid.UUID


class UserUpdate(Strict):
    """Only the fields present in the body change (`phone: null` clears the phone)."""

    full_name: Text | None = None
    phone: Phone | None = None
    email: Text | None = None
    branch_id: uuid.UUID | None = None
    role_id: uuid.UUID | None = None


def user_out(u: AppUser, role: Role, branch_name: str | None) -> dict[str, Any]:
    return {
        "id": u.id,
        "version": u.version,
        "login": u.login,
        "full_name": u.full_name,
        "phone": u.phone,
        "email": u.email,
        "branch_id": u.branch_id,
        "branch_name": branch_name,
        "role_id": u.role_id,
        "role_name": role.name,
        "is_active": u.is_active,
        "must_change_password": u.must_change_password,
        "temp_password_expires_at": u.temp_password_expires_at,
        "created_at": u.created_at,
    }


def _snapshot(u: AppUser) -> dict[str, Any]:
    return {
        "login": u.login,
        "full_name": u.full_name,
        "phone": u.phone,
        "email": u.email,
        "branch_id": u.branch_id,
        "role_id": u.role_id,
        "is_active": u.is_active,
    }


async def _out(db: AsyncSession, u: AppUser) -> dict[str, Any]:
    role = (await db.execute(select(Role).where(Role.id == u.role_id))).scalar_one()
    branch = None
    if u.branch_id:
        branch = (
            await db.execute(select(Branch.name).where(Branch.id == u.branch_id))
        ).scalar_one()
    return user_out(u, role, branch)


async def _role_perms(db: AsyncSession, role: Role) -> dict[str, str]:
    return await permissions_of(db, role)


async def _assignable_role(db: AsyncSession, p: Principal, role_id: uuid.UUID) -> Role:
    role = (await db.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()
    if role is None:
        raise DomainError(NOT_FOUND)
    if not p.can_assign(role.code, await _role_perms(db, role)):
        raise DomainError(ROLE_NOT_ASSIGNABLE)
    return role


def _branch_for_write(p: Principal, branch_id: uuid.UUID | None) -> uuid.UUID | None:
    if p.branch_id is None:
        return branch_id
    if branch_id not in (None, p.branch_id):
        raise DomainError(BRANCH_FORBIDDEN)
    return p.branch_id  # a branch-bound user can only create into their own branch


async def _load(db: AsyncSession, p: Principal, user_id: uuid.UUID, *, touch: bool) -> AppUser:
    """The user, or 404 outside the actor's branch. `touch`: the actor will modify them, so
    their role must not outrank the actor's."""
    u = (await db.execute(select(AppUser).where(AppUser.id == user_id))).scalar_one_or_none()
    if u is None:
        raise DomainError(NOT_FOUND)
    p.check_scope(u.branch_id)
    if touch and not p.is_superadmin:
        role = (await db.execute(select(Role).where(Role.id == u.role_id))).scalar_one()
        if role.code == SUPERADMIN_CODE or not p.covers(await _role_perms(db, role)):
            raise DomainError(ROLE_NOT_ASSIGNABLE)
    return u


async def _ensure_not_last_superadmin(db: AsyncSession, u: AppUser) -> None:
    role = (await db.execute(select(Role).where(Role.id == u.role_id))).scalar_one()
    if role.code != SUPERADMIN_CODE or not u.is_active:
        return
    others = (
        await db.execute(
            select(func.count())
            .select_from(AppUser)
            .where(AppUser.role_id == role.id, AppUser.is_active, AppUser.id != u.id)
        )
    ).scalar_one()
    if others == 0:
        raise DomainError(LAST_SUPERADMIN)


def _user_where(
    p: Principal,
    q: str | None,
    branch_id: uuid.UUID | None,
    role_id: uuid.UUID | None,
    is_active: bool | None,
) -> list[Any]:
    where: list[Any] = []
    if p.branch_id is not None:
        where.append(AppUser.branch_id == p.branch_id)
    if branch_id:
        where.append(AppUser.branch_id == branch_id)
    if role_id:
        where.append(AppUser.role_id == role_id)
    if is_active is not None:
        where.append(AppUser.is_active == is_active)
    if q:
        like = f"%{q.strip().replace('%', r'\%').replace('_', r'\_')}%"
        where.append(
            or_(
                AppUser.login.ilike(like),
                AppUser.full_name.ilike(like),
                AppUser.phone.ilike(like),
            )
        )
    return where


def _user_select(where: list[Any]) -> Any:
    return (
        select(AppUser, Role, Branch.name)
        .join(Role, Role.id == AppUser.role_id)
        .outerjoin(Branch, Branch.id == AppUser.branch_id)
        .where(*where)
        .order_by(AppUser.full_name, AppUser.id)
    )


@router.get("")
async def list_users(
    p: View,
    db: DB,
    q: str | None = None,
    branch_id: uuid.UUID | None = None,
    role_id: uuid.UUID | None = None,
    is_active: bool | None = None,
    page: Page = 1,
    page_size: PageSize = 25,
) -> dict[str, Any]:
    where = _user_where(p, q, branch_id, role_id, is_active)
    total = (await db.execute(select(func.count()).select_from(AppUser).where(*where))).scalar_one()
    rows = (
        await db.execute(_user_select(where).limit(page_size).offset((page - 1) * page_size))
    ).all()
    return {
        "items": [user_out(u, r, b) for u, r, b in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


USER_COLUMNS: list[Col[Any]] = [
    Col("ФИО", lambda r: r[0].full_name),
    Col("Логин", lambda r: r[0].login),
    Col("Телефон", lambda r: r[0].phone),
    Col("Email", lambda r: r[0].email),
    Col("Роль", lambda r: r[1].name),
    Col("Филиал", lambda r: r[2] or "Все филиалы"),
    Col("Активен", lambda r: r[0].is_active, "bool"),
    Col("Создан", lambda r: r[0].created_at, "datetime"),
]


@router.get("/export")
async def export_users(
    p: View,
    db: DB,
    q: str | None = None,
    branch_id: uuid.UUID | None = None,
    role_id: uuid.UUID | None = None,
    is_active: bool | None = None,
) -> Response:
    where = _user_where(p, q, branch_id, role_id, is_active)
    rows = (await db.execute(_user_select(where).limit(MAX_ROWS + 1))).all()
    return await xlsx_response(
        db,
        p,
        entity="app_user",
        slug="polzovateli",
        title="Пользователи",
        columns=USER_COLUMNS,
        rows=rows,
        filters={"q": q, "branch_id": branch_id, "role_id": role_id, "is_active": is_active},
    )


@router.post("", status_code=201)
async def create_user(body: UserCreate, p: Change, db: DB) -> dict[str, Any]:
    role = await _assignable_role(db, p, body.role_id)
    password = temp_password()
    u = AppUser(
        login=body.login,
        full_name=body.full_name,
        phone=body.phone or None,
        email=body.email,
        branch_id=_branch_for_write(p, body.branch_id),
        role_id=role.id,
        password_hash=hash_password(password),
        must_change_password=True,
        temp_password_expires_at=datetime.now(UTC) + timedelta(days=settings.temp_password_days),
    )
    db.add(u)
    await db.flush()
    await record(
        db, p.id, "user.create", "app_user", u.id, diff_of({}, _snapshot(u)), branch_id=u.branch_id
    )
    # The temporary password is shown once, here; only its hash is stored.
    return {"user": await _out(db, u), "temp_password": password}


@router.get("/{user_id}")
async def get_user(user_id: uuid.UUID, p: View, db: DB) -> dict[str, Any]:
    return await _out(db, await _load(db, p, user_id, touch=False))


@router.patch("/{user_id}")
async def update_user(
    user_id: uuid.UUID, body: UserUpdate, version: Version, p: Change, db: DB
) -> dict[str, Any]:
    u = await _load(db, p, user_id, touch=True)
    await check_version(db, u, version, "app_user", lambda: _out(db, u))
    before = _snapshot(u)
    sent = body.model_fields_set
    if "full_name" in sent and body.full_name:
        u.full_name = body.full_name
    if "phone" in sent:
        u.phone = body.phone or None
    if "email" in sent:
        u.email = body.email
    if "branch_id" in sent:
        u.branch_id = _branch_for_write(p, body.branch_id)
    if "role_id" in sent and body.role_id:
        if body.role_id != u.role_id:
            await _ensure_not_last_superadmin(db, u)
        u.role_id = (await _assignable_role(db, p, body.role_id)).id
    u.updated_at = datetime.now(UTC)
    await db.flush()
    await record(
        db,
        p.id,
        "user.update",
        "app_user",
        u.id,
        diff_of(before, _snapshot(u)),
        branch_id=u.branch_id,
    )
    return await _out(db, u)


@router.post("/{user_id}/activate")
@router.post("/{user_id}/reset-password")
async def activate_user(user_id: uuid.UUID, p: Change, db: DB) -> dict[str, Any]:
    """Activate the account or reset its password: a new temporary password (7 days), shown once."""
    u = await _load(db, p, user_id, touch=True)
    was_active = u.is_active
    password = temp_password()
    u.is_active = True
    u.password_hash = hash_password(password)
    u.must_change_password = True
    u.temp_password_expires_at = datetime.now(UTC) + timedelta(days=settings.temp_password_days)
    u.updated_at = datetime.now(UTC)
    await revoke_sessions(db, u.id)
    await record(
        db,
        p.id,
        "user.activate" if not was_active else "user.reset_password",
        "app_user",
        u.id,
        {"expires_at": [None, u.temp_password_expires_at]},
        branch_id=u.branch_id,
    )
    return {
        "user": await _out(db, u),
        "temp_password": password,
        "expires_at": u.temp_password_expires_at,
    }


@router.post("/{user_id}/deactivate")
async def deactivate_user(user_id: uuid.UUID, p: Change, db: DB) -> dict[str, Any]:
    u = await _load(db, p, user_id, touch=True)
    if u.id == p.id:
        raise DomainError(CANNOT_DEACTIVATE_SELF)
    await _ensure_not_last_superadmin(db, u)
    before = _snapshot(u)
    u.is_active = False
    u.updated_at = datetime.now(UTC)
    await revoke_sessions(db, u.id)
    await db.flush()
    await record(
        db,
        p.id,
        "user.deactivate",
        "app_user",
        u.id,
        diff_of(before, _snapshot(u)),
        branch_id=u.branch_id,
    )
    return await _out(db, u)


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: uuid.UUID, p: Change, db: DB) -> None:
    u = await _load(db, p, user_id, touch=True)
    if u.id == p.id:
        raise DomainError(CANNOT_DEACTIVATE_SELF)
    await _ensure_not_last_superadmin(db, u)
    snapshot, branch_id = _snapshot(u), u.branch_id
    try:
        async with db.begin_nested():
            await db.delete(u)
            await db.flush()
    except IntegrityError as exc:
        raise DomainError(USER_IN_USE) from exc
    await record(
        db, p.id, "user.delete", "app_user", user_id, diff_of(snapshot, {}), branch_id=branch_id
    )
