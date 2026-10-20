"""`python -m app.cli create-superadmin --login X` — bootstrap the first account.

Prints a temporary password (shown once, valid 7 days, changed at the first sign-in).
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.audit.log import record
from app.core.config import settings
from app.core.db import engine, sessionmaker
from app.core.security import hash_password, temp_password
from app.models import AppUser, Role
from app.permissions import SUPERADMIN_CODE


async def create_superadmin(login: str, full_name: str) -> str | None:
    """The temporary password, or None when the login exists."""
    async with sessionmaker() as db:
        exists = (await db.execute(select(AppUser.id).where(AppUser.login == login))).first()
        if exists:
            return None
        role = (await db.execute(select(Role).where(Role.code == SUPERADMIN_CODE))).scalar_one()
        password = temp_password()
        user = AppUser(
            login=login,
            full_name=full_name,
            role_id=role.id,
            password_hash=hash_password(password),
            must_change_password=True,
            temp_password_expires_at=datetime.now(UTC)
            + timedelta(days=settings.temp_password_days),
        )
        db.add(user)
        await db.flush()
        await record(
            db,
            None,
            "user.create",
            "app_user",
            user.id,
            {"login": [None, login], "cli": [None, True]},
        )
        await db.commit()
    await engine.dispose()
    return password


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-superadmin", help="create a superadmin with a temp password")
    create.add_argument("--login", required=True)
    create.add_argument("--full-name", default="Суперадмин")
    args = parser.parse_args(argv)
    password = asyncio.run(create_superadmin(args.login.strip(), args.full_name))
    if password is None:
        print(f"login {args.login!r} already exists", file=sys.stderr)
        return 1
    print(
        f"login: {args.login}\ntemporary password (shown once, valid "
        f"{settings.temp_password_days} days): {password}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
