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
from app.core.password_policy import MAX_LENGTH as PASSWORD_MAX_LENGTH
from app.core.password_policy import policy, violations
from app.core.proxy import client_ip
from app.core.security import (
    hash_password,
    new_token,
    token_hash,
    verify_password,
)
from app.core.versioning import Version, check_version
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
    """Only the fields present change."""

    full_name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
        | None
    ) = None
    phone: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)] | None = None
    email: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None


def me_out(p: Principal, branch_name: str | None) -> dict[str, Any]:
    u = p.user
    return {
        "id": u.id,
        "version": u.version,
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
    family_id = family_id or uuid.uuid4()
    db.add(
        RefreshToken(
            user_id=user_id,
            family_id=family_id,
            token_hash=token_hash(token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_ttl_days),
        )
    )
    await db.flush()
    access = make_access_token(user_id, family_id)
    _set_cookie(response, ACCESS_COOKIE, access, settings.refresh_ttl_days * 86400, "/")
    _set_cookie(response, REFRESH_COOKIE, token, settings.refresh_ttl_days * 86400, "/api/v1/auth")


async def revoke_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


_BUMP = """
    INSERT INTO {table} ({keys}, failures) VALUES ({binds}, 1)
    ON CONFLICT ({keys}) DO UPDATE SET
      failures = CASE WHEN {table}.failures + 1 >= :max THEN 0
                      ELSE {table}.failures + 1 END,
      locked_until = CASE WHEN {table}.failures + 1 >= :max
                          THEN now() + make_interval(mins => :mins)
                          ELSE {table}.locked_until END,
      updated_at = now()
    RETURNING failures
"""


async def _bump(db: AsyncSession, table: str, keys: dict[str, str], limit: int) -> bool:
    """Count one failure; True when it tripped the lock."""
    sql = _BUMP.format(
        table=table,
        keys=", ".join(keys),
        binds=", ".join(f":{k}" for k in keys),
    )
    params = {**keys, "max": limit, "mins": settings.lockout_minutes}
    return bool((await db.execute(text(sql), params)).scalar_one() == 0)


async def _record_failure(db: AsyncSession, login: str, ip: str) -> None:
    """Count a failed login against (login, address) and against the login as a whole, lock
    either after too many, and put both in the audit log (the login name only, never the
    password). Five bad tries from one address lock that address only; the higher per-login
    ceiling still stops a spread-out attack."""
    by_ip = await _bump(
        db, "login_ip_attempt", {"login": login, "ip": ip}, settings.max_failed_logins
    )
    overall = await _bump(db, "login_attempt", {"login": login}, settings.max_failed_logins_global)
    name = login[:64]
    await record(db, None, "auth.login_failed", "login", name)
    if by_ip or overall:  # this failure tripped a lock
        await record(
            db, None, "auth.locked", "login", name, {"minutes": [None, settings.lockout_minutes]}
        )
    await db.commit()  # the failure must outlive the error response


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response, db: DB) -> dict[str, Any]:
    ip = client_ip(request)
    locked = (
        await db.execute(
            text(
                "SELECT coalesce((SELECT locked_until > now() FROM login_attempt WHERE login = :l)"
                ", false) OR coalesce((SELECT locked_until > now() FROM login_ip_attempt "
                "WHERE login = :l AND ip = :ip), false)"
            ),
            {"l": body.login, "ip": ip},
        )
    ).scalar_one()
    if locked:
        raise DomainError(TOO_MANY_ATTEMPTS)
    user = (
        await db.execute(select(AppUser).where(AppUser.login == body.login))
    ).scalar_one_or_none()
    password_ok = verify_password(user.password_hash if user else None, body.password)
    if user is None or not password_ok or not user.is_active:
        await _record_failure(db, body.login, ip)
        raise DomainError(INVALID_CREDENTIALS)
    if _temp_password_expired(user, datetime.now(UTC)):
        raise DomainError(TEMP_PASSWORD_EXPIRED)
    await db.execute(text("DELETE FROM login_attempt WHERE login = :l"), {"l": body.login})
    await db.execute(
        text("DELETE FROM login_ip_attempt WHERE login = :l AND ip = :ip"),
        {"l": body.login, "ip": ip},
    )
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
        raise DomainError(NOT_AUTHENTICATED)
    if row.used_at is not None:
        if now - row.used_at > REUSE_GRACE:  # a used token again later: assume theft
            await revoke_family(db, row.family_id)
            await db.commit()
        raise DomainError(NOT_AUTHENTICATED)
    user = (
        await db.execute(select(AppUser).where(AppUser.id == row.user_id, AppUser.is_active))
    ).scalar_one_or_none()
    if user is None or _temp_password_expired(user, now):
        raise DomainError(NOT_AUTHENTICATED)
    # Claim the token atomically: of concurrent requests with the same token only one wins,
    # so a stolen copy cannot fork a second live session.
    claimed = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.id == row.id, RefreshToken.used_at.is_(None))
        .values(used_at=now)
        .returning(RefreshToken.id)
    )
    if claimed.first() is None:
        raise DomainError(NOT_AUTHENTICATED)
    await issue_session(db, response, user.id, row.family_id)


def _temp_password_expired(user: AppUser, now: datetime) -> bool:
    return (
        user.must_change_password
        and user.temp_password_expires_at is not None
        and user.temp_password_expires_at < now
    )


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
async def update_me(body: ProfileIn, version: Version, p: CurrentUser, db: DB) -> dict[str, Any]:
    u = p.user

    async def current() -> dict[str, Any]:
        return me_out(p, await _branch_name(db, u.branch_id))

    await check_version(db, u, version, "app_user", current)
    before = {"full_name": u.full_name, "phone": u.phone, "email": u.email}
    sent = body.model_fields_set
    if "full_name" in sent and body.full_name:
        u.full_name = body.full_name
    if "phone" in sent:
        u.phone = body.phone or None
    if "email" in sent:
        u.email = body.email or None
    u.updated_at = datetime.now(UTC)
    await db.flush()  # a taken phone number is a 409 through the constraint map
    after = {"full_name": u.full_name, "phone": u.phone, "email": u.email}
    await record(
        db, u.id, "profile.update", "app_user", u.id, diff_of(before, after), branch_id=u.branch_id
    )
    return me_out(p, await _branch_name(db, u.branch_id))


@router.get("/password-policy")
async def password_policy() -> dict[str, object]:
    """Public: the rules the web shows while typing. Nothing secret in it."""
    return policy()


@router.post("/change-password")
@allow_pending_password
async def change_password(
    body: ChangePasswordIn, request: Request, response: Response, p: CurrentUser, db: DB
) -> dict[str, Any]:
    u = p.user
    if _temp_password_expired(u, datetime.now(UTC)):  # a session opened before the expiry
        raise DomainError(TEMP_PASSWORD_EXPIRED)
    if not verify_password(u.password_hash, body.current_password):
        raise DomainError(WRONG_PASSWORD)
    if body.new_password == body.current_password:
        raise DomainError(SAME_PASSWORD)
    if violations(body.new_password, login=u.login):
        raise DomainError(WEAK_PASSWORD)
    u.password_hash = hash_password(body.new_password)
    u.must_change_password = False
    u.temp_password_expires_at = None
    u.updated_at = datetime.now(UTC)
    await revoke_sessions(db, u.id)  # every other device signs in again
    await issue_session(db, response, u.id)
    await record(db, u.id, "auth.change_password", "app_user", u.id, branch_id=u.branch_id)
    return me_out(p, await _branch_name(db, u.branch_id))
