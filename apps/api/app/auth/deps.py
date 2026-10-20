"""Request guards: CSRF header, the signed-in user and `require(section, level)` — the one
permission check every endpoint uses. Branch scope helpers live here too (`Principal.in_scope`)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Request
from sqlalchemy import exists, select

from app.auth.errors import PASSWORD_CHANGE_REQUIRED
from app.core.config import settings
from app.core.db import DB
from app.core.errors import (
    CSRF_HEADER_MISSING,
    FORBIDDEN,
    NOT_AUTHENTICATED,
    NOT_FOUND,
    DomainError,
)
from app.models import AppUser, RefreshToken, Role, RolePermission
from app.permissions import SECTIONS, SUPERADMIN_CODE, allows

ACCESS_COOKIE = "ilm_access"
REFRESH_COOKIE = "ilm_refresh"
CSRF_VALUE = "ilm"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def require_csrf_header(request: Request) -> None:
    """Cross-site forms cannot set custom headers, so a state change must carry one.
    Second layer on top of SameSite=Lax cookies."""
    if request.method not in SAFE_METHODS and request.headers.get("x-requested-with") != CSRF_VALUE:
        raise DomainError(CSRF_HEADER_MISSING)


def make_access_token(user_id: UUID, session_id: UUID) -> str:
    """`sid` is the refresh token family: revoking the family (logout, password change,
    refresh reuse) ends this access token at once, not when it expires."""
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "sid": str(session_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_ttl_minutes),
        "typ": "access",
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm="HS256")


def _claims_of(token: str | None) -> tuple[UUID, UUID] | None:
    if not token:
        return None
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp", "sub", "sid"]},
        )
        if claims.get("typ") != "access":
            return None
        return UUID(claims["sub"]), UUID(claims["sid"])
    except jwt.PyJWTError, ValueError, TypeError:
        return None


@dataclass
class Principal:
    user: AppUser
    role: Role
    permissions: dict[str, str]  # section -> level; absent = none

    @property
    def id(self) -> UUID:
        return self.user.id

    @property
    def branch_id(self) -> UUID | None:
        return self.user.branch_id

    @property
    def is_superadmin(self) -> bool:
        return self.role.code == SUPERADMIN_CODE

    def level(self, section: str) -> str | None:
        return self.permissions.get(section)

    def in_scope(self, branch_id: UUID | None) -> bool:
        """A user bound to a branch works with that branch's rows only; no branch = all."""
        return self.branch_id is None or branch_id == self.branch_id

    def check_scope(self, branch_id: UUID | None) -> None:
        """404, not 403: a row of another branch must look like it does not exist."""
        if not self.in_scope(branch_id):
            raise DomainError(NOT_FOUND)

    def covers(self, permissions: dict[str, str]) -> bool:
        """May this user hand out `permissions`? Nobody gives more than they have."""
        return self.is_superadmin or all(
            allows(self.level(s), level) for s, level in permissions.items()
        )

    def can_assign(self, role_code: str | None, permissions: dict[str, str]) -> bool:
        """May this user put someone into a role? Superadmin role only for a superadmin."""
        return self.is_superadmin or (role_code != SUPERADMIN_CODE and self.covers(permissions))


async def permissions_of(db: DB, role: Role) -> dict[str, str]:
    if role.code == SUPERADMIN_CODE:
        return dict.fromkeys(SECTIONS, "change")
    rows = await db.execute(
        select(RolePermission.section, RolePermission.level).where(
            RolePermission.role_id == role.id
        )
    )
    return {s: lvl for s, lvl in rows.all()}


async def _principal(request: Request, db: DB) -> Principal:
    claims = _claims_of(request.cookies.get(ACCESS_COOKIE))
    if claims is None:
        raise DomainError(NOT_AUTHENTICATED)
    user_id, session_id = claims
    live_session = exists().where(
        RefreshToken.family_id == session_id,
        RefreshToken.user_id == AppUser.id,
        RefreshToken.revoked_at.is_(None),
    )
    row = (
        await db.execute(
            select(AppUser, Role)
            .join(Role, Role.id == AppUser.role_id)
            .where(AppUser.id == user_id, AppUser.is_active, live_session)
        )
    ).first()
    if row is None:
        raise DomainError(NOT_AUTHENTICATED)
    user, role = row
    # A user who must change the temporary password reaches only the routes that say so.
    route = request.scope.get("route")
    pending_ok = bool(getattr(getattr(route, "endpoint", None), "allow_pending_password", False))
    if user.must_change_password and not pending_ok:
        raise DomainError(PASSWORD_CHANGE_REQUIRED)
    return Principal(user, role, await permissions_of(db, role))


CurrentUser = Annotated[Principal, Depends(_principal)]


def allow_pending_password[F](func: F) -> F:
    """Mark a route a user with must_change_password may still call (change-password only)."""
    func.allow_pending_password = True  # type: ignore[attr-defined]
    return func


def require(section: str, level: str = "view") -> object:
    """`p: Annotated[Principal, require("users", "change")]` — 403 unless the user's role gives
    at least `level` on `section`. Superadmin passes everywhere."""
    if section not in SECTIONS:
        raise ValueError(f"unknown section {section!r}")

    async def dependency(p: CurrentUser) -> Principal:
        if not allows(p.level(section), level):
            raise DomainError(FORBIDDEN, section=section, level=level)
        return p

    return Depends(dependency)
