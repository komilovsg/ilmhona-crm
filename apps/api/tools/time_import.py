"""Time one import apply and count the SQL statements (each is a network round trip over WAN):

DATABASE_URL=... uv run python -m tools.time_import snapshot.json [--dry-run]
"""

import asyncio
import json
import sys
import time

from sqlalchemy import event

from app.core.db import engine, sessionmaker
from app.importer import run_import

n = {"stmts": 0}
kinds: dict[str, int] = {}


@event.listens_for(engine.sync_engine, "before_cursor_execute")
def _count(conn: object, cursor: object, statement: str, *_: object) -> None:
    n["stmts"] += 1
    key = " ".join(statement.split())[:70]
    kinds[key] = kinds.get(key, 0) + 1


async def main() -> None:
    snap = json.load(open(sys.argv[1], encoding="utf-8"))
    t = time.perf_counter()
    async with sessionmaker() as db:
        report = await run_import(db, snap, apply="--dry-run" not in sys.argv)
    print(
        f"{time.perf_counter() - t:.1f}s, {n['stmts']} statements, imported {dict(report.imported)}"
    )
    for k, v in sorted(kinds.items(), key=lambda kv: -kv[1])[:8]:
        print(f"  {v:5} {k}")
    await engine.dispose()


asyncio.run(main())
