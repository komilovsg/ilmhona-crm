"""EXPLAIN ANALYZE of every SQL statement the hot endpoints run (local database only):

    DATABASE_URL=... uv run python -m tools.explain [out.txt]

Prints the slowest statements with their plans, so an index can be judged by numbers.
"""

import asyncio
import re
import sys
from typing import Any

import httpx
from sqlalchemy import event, text

from app.core.db import engine
from app.main import app

H = {"x-requested-with": "ilm"}
seen: dict[str, tuple[str, tuple[Any, ...], str]] = {}
current = {"url": ""}


@event.listens_for(engine.sync_engine, "before_cursor_execute")
def _capture(conn: Any, cursor: Any, statement: str, parameters: Any, *_: Any) -> None:
    if statement.lstrip().upper().startswith("SELECT"):
        key = re.sub(r"\s+", " ", statement)
        seen.setdefault(key, (statement, tuple(parameters), current["url"]))


async def main() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t", headers=H
    ) as c:
        await c.post(
            "/api/v1/auth/login", json={"login": "load_admin", "password": "Load-test-pass-1"}
        )
        async with engine.connect() as conn:
            cohort = (
                await conn.execute(
                    text("SELECT id FROM cohort WHERE status <> 'набор' ORDER BY code LIMIT 1 OFFSET 40")
                )
            ).scalar_one()
        urls = [
            "/api/v1/dashboard/overview",
            "/api/v1/dashboard/by-month",
            "/api/v1/dashboard/by-course",
            "/api/v1/master-list",
            "/api/v1/graduates/students",
            "/api/v1/students",
            "/api/v1/students?q=Азим",
            "/api/v1/cohorts",
            f"/api/v1/cohorts/{cohort}/attendance",
            f"/api/v1/cohorts/{cohort}/grades",
            "/api/v1/payments",
            "/api/v1/payments/debtors",
            "/api/v1/salaries",
            "/api/v1/leads",
            "/api/v1/audit",
            "/api/v1/audit?section=students&date_from=2026-01-01&q=Азим",
            "/api/v1/audit?entity=student&action=student.update",
            "/api/v1/me/today",
        ]
        for u in urls:
            current["url"] = u
            r = await c.get(u)
            assert r.status_code == 200, (u, r.status_code)
    raw = await engine.raw_connection()
    drv = raw.driver_connection
    results = []
    for _key, (statement, params, url) in seen.items():
        try:
            rows = await drv.fetch("EXPLAIN (ANALYZE, BUFFERS OFF) " + statement, *params)
        except Exception as exc:  # noqa: BLE001
            print("skip:", type(exc).__name__, str(exc)[:80])
            continue
        plan = "\n".join(r[0] for r in rows)
        ms = float(re.search(r"Execution Time: ([\d.]+) ms", plan).group(1))  # type: ignore[union-attr]
        results.append((ms, url, statement, plan))
    results.sort(key=lambda x: -x[0])
    out = []
    for ms, url, statement, plan in results[:14]:
        out.append(f"=== {ms:.2f} ms  [{url}]\n{' '.join(statement.split())[:400]}\n{plan}\n")
    text_out = "\n".join(out)
    if len(sys.argv) > 1:
        open(sys.argv[1], "w").write(text_out)
    if len(sys.argv) > 2:  # every statement with its time and plan, for before / after diffs
        import json

        json.dump(
            {" ".join(st.split()): {"ms": ms, "url": url, "plan": plan} for ms, url, st, plan in results},
            open(sys.argv[2], "w"),
            ensure_ascii=False,
        )
    print("\n".join(f"{ms:8.2f} ms {url}" for ms, url, *_ in results[:14]))
    raw.close()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
