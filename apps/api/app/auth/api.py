"""login, logout, refresh, me, change-password.

Access token: short JWT in an httpOnly cookie. Refresh token: opaque, stored hashed, rotated on
every use, in an httpOnly cookie that only /api/v1/auth sees. State changes need the
`X-Requested-With: ilm` header (deps.require_csrf_header).
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.log import diff_of, record
from app.auth.deps import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    CurrentUser,
    Principal,
    allow_pending_password,
    make_access_token,
    permissions_of,
    require_csrf_header,
)
from app.auth.errors import (
    INVALID_CREDENTIALS,
    SAME_PASSWORD,
    TEMP_PASSWORD_EXPIRED,
    TOO_MANY_ATTEMPTS,
    WEAK_PASSWORD,
    WRONG_PASSWORD,
)
from app.core.config import settings
from app.core.db import DB
from app.core.errors import NOT_AUTHENTICATED, DomainError
from app.core.security import (
    PASSWORD_MAX_LENGTH,
    hash_password,
    is_strong,
    new_token,
    token_hash,
    verify_password,
)
from app.models import AppUser, Branch, RefreshToken, Role

router = APIRouter(
    prefix="/api/v1/auth", tags=["auth"], dependencies=[Depends(require_csrf_header)]
)

REUSE_GRACE = timedelta(seconds=10)  # two tabs refreshing at once are not a theft

Login = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
Password = Annotated[str, StringConstraints(min_length=1, max_length=PASSWORD_MAX_LENGTH)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginIn(Strict):
    login: Login
    password: Password


class ChangePasswordIn(Strict):
    current_password: Password
    new_password: Password


class ProfileIn(Strict):
    full_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)] | None = None
    email: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None


def me_out(p: Principal, branch_name: str | None) -> dict[str, Any]:
    u = p.user
    return {
        "id": u.id,
        "login": u.login,
        "full_name": u.full_name,
        "phone": u.phone,
        "email": u.email,
        "branch": {"id": u.branch_id, "name": branch_name} if u.branch_id else None,
        "role": {"id": p.role.id, "name": p.role.name, "code": p.role.code},
        "must_change_password": u.must_change_password,
        "permissions": p.permissions,
    }


async def _branch_name(db: AsyncSession, branch_id: uuid.UUID | None) -> str | None:
    if branch_id is None:
        return None
    return (await db.execute(select(Branch.name).where(Branch.id == branch_id))).scalar_one()


def _set_cookie(response: Response, name: str, value: str, max_age: int, path: str) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=path,
    )


def clear_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")


async def issue_session(
    db: AsyncSession, response: Response, user_id: uuid.UUID, family_id: uuid.UUID | None = None
) -> None:
    token = new_token()
    db.add(
        RefreshToken(
            user_id=user_id,
            family_id=family_id or uuid.uuid4(),
            token_hash=token_hash(token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_ttl_days),
        )
    )
    await db.flush()
    _set_cookie(
        response, ACCESS_COOKIE, make_access_token(user_id), settings.access_ttl_minutes * 60, "/"
    )
    _set_cookie(response, REFRESH_COOKIE, token, settings.refresh_ttl_days * 86400, "/api/v1/auth")


async def revoke_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def _record_failure(db: AsyncSession, login: str) -> None:
    await db.execute(
        text(
            """
            INSERT INTO login_attempt (login, failures) VALUES (:l, 1)
            ON CONFLICT (login) DO UPDATE SET
              failures = CASE WHEN login_attempt.failures + 1 >= :max THEN 0
                              ELSE login_attempt.failures + 1 END,
              locked_until = CASE WHEN login_attempt.failures + 1 >= :max
                                  THEN now() + make_interval(mins => :mins)
                                  ELSE login_attempt.locked_until END
            """
        ),
        {"l": login, "max": settings.max_failed_logins, "mins": settings.lockout_minutes},
    )
    await db.commit()  # the failure must outlive the error response


@router.post("/login")
async def login(body: LoginIn, response: Response, db: DB) -> dict[str, Any]:
    locked = (
        await db.execute(
            text("SELECT locked_until > now() FROM login_attempt WHERE login = :l"),
            {"l": body.login},
        )
    ).scalar_one_or_none()
    if locked:
        raise DomainError(TOO_MANY_ATTEMPTS)
    user = (
        await db.execute(select(AppUser).where(AppUser.login == body.login))
    ).scalar_one_or_none()
    password_ok = verify_password(user.password_hash if user else None, body.password)
    if user is None or not password_ok or not user.is_active:
        await _record_failure(db, body.login)
        raise DomainError(INVALID_CREDENTIALS)
    if (
        user.must_change_password
        and user.temp_password_expires_at is not None
        and user.temp_password_expires_at < datetime.now(UTC)
    ):
        raise DomainError(TEMP_PASSWORD_EXPIRED)
    await db.execute(text("DELETE FROM login_attempt WHERE login = :l"), {"l": body.login})
    await issue_session(db, response, user.id)
    await record(db, user.id, "auth.login", "app_user", user.id, branch_id=user.branch_id)
    role = (await db.execute(select(Role).where(Role.id == user.role_id))).scalar_one()
    p = Principal(user, role, await permissions_of(db, role))
    return me_out(p, await _branch_name(db, user.branch_id))


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: DB) -> None:
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        row = (
            await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash(raw)))
        ).scalar_one_or_none()
        if row is not None:
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == row.family_id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=datetime.now(UTC))
            )
    clear_cookies(response)


@router.post("/refresh", status_code=204)
@allow_pending_password
async def refresh(request: Request, response: Response, db: DB) -> None:
    raw = request.cookies.get(REFRESH_COOKIE)
    now = datetime.now(UTC)
    row = (
        (
            await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash(raw)))
        ).scalar_one_or_none()
        if raw
        else None
    )
    if row is None or row.revoked_at is not None or row.expires_at < now:
        clear_cookies(response)
        raise DomainError(NOT_AUTHENTICATED)
    if row.used_at is not None:
        if now - row.used_at > REUSE_GRACE:  # a used token again later: assume theft
            await revoke_family(db, row.family_id)
            await db.commit()
        raise DomainError(NOT_AUTHENTICATED)
    user = (
        await db.execute(select(AppUser).where(AppUser.id == row.user_id, AppUser.is_active))
    ).scalar_one_or_none()
    if user is None:
        raise DomainError(NOT_AUTHENTICATED)
    row.used_at = now
    await issue_session(db, response, user.id, row.family_id)


async def revoke_family(db: AsyncSession, family_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


@router.get("/me")
async def me(p: CurrentUser, db: DB) -> dict[str, Any]:
    return me_out(p, await _branch_name(db, p.user.branch_id))


@router.patch("/me")
async def update_me(body: ProfileIn, p: CurrentUser, db: DB) -> dict[str, Any]:
    u = p.user
    before = {"full_name": u.full_name, "phone": u.phone, "email": u.email}
    u.full_name = body.full_name
    u.phone = body.phone or None
    u.email = body.email or None
    u.updated_at = datetime.now(UTC)
    await db.flush()  # a taken phone number is a 409 through the constraint map
    after = {"full_name": u.full_name, "phone": u.phone, "email": u.email}
    await record(
        db, u.id, "profile.update", "app_user", u.id, diff_of(before, after), branch_id=u.branch_id
    )
    return me_out(p, await _branch_name(db, u.branch_id))


@router.post("/change-password")
@allow_pending_password
async def change_password(
    body: ChangePasswordIn, request: Request, response: Response, p: CurrentUser, db: DB
) -> dict[str, Any]:
    u = p.user
    if not verify_password(u.password_hash, body.current_password):
        raise DomainError(WRONG_PASSWORD)
    if body.new_password == body.current_password:
        raise DomainError(SAME_PASSWORD)
    if not is_strong(body.new_password):
        raise DomainError(WEAK_PASSWORD)
    u.password_hash = hash_password(body.new_password)
    u.must_change_password = False
    u.temp_password_expires_at = None
    u.updated_at = datetime.now(UTC)
    await revoke_sessions(db, u.id)  # every other device signs in again
    await issue_session(db, response, u.id)
    await record(db, u.id, "auth.change_password", "app_user", u.id, branch_id=u.branch_id)
    return me_out(p, await _branch_name(db, u.branch_id))
