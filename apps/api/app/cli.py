"""`python -m app.cli create-superadmin --login X` — bootstrap the first account.

Prints a temporary password (shown once, valid 7 days, changed at the first sign-in).

`python -m app.cli daily` — the daily job: cohort statuses by dates and the enrollments of
cohorts that finished (#20, #11). Safe to run any number of times.
"""

import argparse
import asyncio
import sys
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.audit.log import record
from app.cohorts.status import STATUSES, sync_status
from app.core.config import settings
from app.core.db import engine, sessionmaker
from app.core.security import hash_password, temp_password
from app.models import AppUser, Cohort, Role
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


async def daily(on: date | None = None) -> int:
    """Re-derive every open cohort's status from the dates. Returns how many changed."""
    changed = 0
    async with sessionmaker() as db:
        cohorts = (
            await db.execute(
                select(Cohort).where(Cohort.status.in_(STATUSES[:2])).order_by(Cohort.code)
            )
        ).scalars()
        for cohort in list(cohorts):
            before = cohort.status
            if await sync_status(db, cohort, None, on):
                changed += 1
                await record(
                    db,
                    None,
                    "cohort.status",
                    "cohort",
                    cohort.id,
                    {"status": [before, cohort.status], "cli": [None, "daily"]},
                    branch_id=cohort.branch_id,
                )
        await db.commit()
    return changed


async def _daily_and_close() -> int:
    count = await daily()
    await engine.dispose()
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-superadmin", help="create a superadmin with a temp password")
    create.add_argument("--login", required=True)
    create.add_argument("--full-name", default="Суперадмин")
    sub.add_parser("daily", help="update cohort statuses and finished enrollments")
    args = parser.parse_args(argv)
    if args.command == "daily":
        count = asyncio.run(_daily_and_close())
        print(f"cohort statuses changed: {count}")
        return 0
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
