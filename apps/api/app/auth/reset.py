"""«Забыли пароль?»: the user names a login, the administrator gets a request.

The answer is always the same 202 with the same text and the same database work, whether the
login exists, is deactivated, or the limit was hit: nothing tells an outsider which logins are
real. Limits (3 per hour) count per client address and per login, plus a global cap."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import func, select

from app.audit.log import record
from app.auth.deps import require_csrf_header
from app.core.db import DB
from app.core.proxy import client_ip
from app.models import AppUser, PasswordResetRequest

router = APIRouter(
    prefix="/api/v1/auth", tags=["auth"], dependencies=[Depends(require_csrf_header)]
)

LIMIT = 3
GLOBAL_LIMIT = 100  # all addresses together: a spread-out flood cannot grow the table
WINDOW = timedelta(hours=1)
NEUTRAL = "Если такой логин есть, администратор получит запрос"


class ForgotIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    login: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


@router.post("/forgot-password", status_code=202)
async def forgot_password(body: ForgotIn, request: Request, db: DB) -> dict[str, Any]:
    ip = client_ip(request)
    since = datetime.now(UTC) - WINDOW
    recent = select(func.count()).select_from(PasswordResetRequest)
    by_ip = (
        await db.execute(
            recent.where(PasswordResetRequest.ip == ip, PasswordResetRequest.created_at > since)
        )
    ).scalar_one()
    by_login = (
        await db.execute(
            recent.where(
                PasswordResetRequest.login == body.login, PasswordResetRequest.created_at > since
            )
        )
    ).scalar_one()
    overall = (await db.execute(recent.where(PasswordResetRequest.created_at > since))).scalar_one()
    user = (
        await db.execute(select(AppUser).where(AppUser.login == body.login, AppUser.is_active))
    ).scalar_one_or_none()
    if by_ip < LIMIT and by_login < LIMIT and overall < GLOBAL_LIMIT:
        db.add(PasswordResetRequest(login=body.login, user_id=user.id if user else None, ip=ip))
        await db.flush()
        await record(db, None, "auth.reset_requested", "login", body.login[:64])
    return {"message": NEUTRAL}
