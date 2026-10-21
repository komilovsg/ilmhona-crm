"""`python -m app.cli create-superadmin --login X` — bootstrap the first account.

Prints a temporary password (shown once, valid 7 days, changed at the first sign-in).

`python -m app.cli daily` — the daily job: cohort statuses by dates and the enrollments of
cohorts that finished (#20, #11), then the login-attempt rows older than a day are deleted.
Safe to run any number of times.

`python -m app.cli seed-demo` / `wipe-demo` — a fake dataset for demos and its removal
(app/demo.py); the wipe deletes only the rows the seed made.
"""

import argparse
import asyncio
import sys
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select, text

from app.audit.log import record
from app.cohorts.status import STATUSES, sync_status
from app.core.config import settings
from app.core.db import engine, sessionmaker
from app.core.security import hash_password, temp_password
from app.demo import demo_exists, seed_demo, wipe_demo
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


async def purge_login_attempts() -> int:
    """Failed-login counters untouched for a day (any lock is long over). Returns the rows."""
    async with sessionmaker() as db:
        removed = 0
        for table in ("login_attempt", "login_ip_attempt"):
            result = await db.execute(
                text(f"DELETE FROM {table} WHERE updated_at < now() - interval '1 day'")
            )
            removed += int(result.rowcount or 0)  # type: ignore[attr-defined]
        await db.execute(
            text("DELETE FROM password_reset_request WHERE created_at < now() - interval '30 days'")
        )
        await db.commit()
    return removed


async def _daily_and_close() -> tuple[int, int]:
    count = await daily()
    purged = await purge_login_attempts()
    await engine.dispose()
    return count, purged


async def seed_command() -> str | None:
    async with sessionmaker() as db:
        if await demo_exists(db):
            return None
        password, rows = await seed_demo(db)
        await db.commit()
    await engine.dispose()
    print(f"demo rows created: {rows}")
    return password


async def wipe_command() -> int:
    async with sessionmaker() as db:
        rows = await wipe_demo(db)
        await db.commit()
    await engine.dispose()
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-superadmin", help="create a superadmin with a temp password")
    create.add_argument("--login", required=True)
    create.add_argument("--full-name", default="Суперадмин")
    sub.add_parser("daily", help="update cohort statuses, finished enrollments; purge old logins")
    sub.add_parser("seed-demo", help="load a fake dataset (all names invented)")
    sub.add_parser("wipe-demo", help="delete the rows seed-demo created, and only those")
    args = parser.parse_args(argv)
    if args.command == "daily":
        count, purged = asyncio.run(_daily_and_close())
        print(f"cohort statuses changed: {count}; login attempts purged: {purged}")
        return 0
    if args.command == "seed-demo":
        demo_password = asyncio.run(seed_command())
        if demo_password is None:
            print("demo data already loaded: run wipe-demo first", file=sys.stderr)
            return 1
        print(f"logins demo_admin, demo_manager1, demo_instructor11 ...; password: {demo_password}")
        return 0
    if args.command == "wipe-demo":
        print(f"demo rows deleted: {asyncio.run(wipe_command())}")
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
