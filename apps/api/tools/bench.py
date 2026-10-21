"""In-process latency + SQL-query-count benchmark (warm, N requests per endpoint) against a
local database filled by `tools.seed_load`:

    DATABASE_URL=postgresql+asyncpg://ilm@localhost:55433/<db> uv run python -m tools.bench [out.json]
"""

import asyncio
import json
import os
import statistics
import sys
import time
from typing import Any

import httpx
from sqlalchemy import event, text

from app.core.db import engine
from app.main import app

N = int(os.environ.get("BENCH_N", "100"))
H = {"x-requested-with": "ilm"}
counter = {"n": 0}


@event.listens_for(engine.sync_engine, "before_cursor_execute")
def _count(*_: Any) -> None:
    counter["n"] += 1


async def main() -> None:
    out: dict[str, Any] = {}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t", headers=H
    ) as c:
        r = await c.post(
            "/api/v1/auth/login", json={"login": "load_admin", "password": "Load-test-pass-1"}
        )
        assert r.status_code == 200, r.text
        async with engine.connect() as conn:
            cohort = (
                await conn.execute(
                    text(
                        "SELECT id FROM cohort WHERE status <> 'набор' ORDER BY code LIMIT 1 OFFSET 40"
                    )
                )
            ).scalar_one()
            student = (await conn.execute(text("SELECT id FROM student LIMIT 1"))).scalar_one()
            lesson = (
                await conn.execute(
                    text("SELECT id FROM lesson WHERE cohort_id = :c LIMIT 1"), {"c": cohort}
                )
            ).scalar_one()
        cases = {
            "auth/me": "/api/v1/auth/me",
            "dashboard/overview": "/api/v1/dashboard/overview",
            "dashboard/by-month": "/api/v1/dashboard/by-month",
            "dashboard/by-course": "/api/v1/dashboard/by-course",
            "master-list": "/api/v1/master-list",
            "graduates/students": "/api/v1/graduates/students",
            "graduates/courses": "/api/v1/graduates/courses",
            "students list": "/api/v1/students",
            "students search": "/api/v1/students?q=Азим",
            "student detail": f"/api/v1/students/{student}",
            "cohorts list": "/api/v1/cohorts",
            "cohort detail": f"/api/v1/cohorts/{cohort}",
            "cohort enrollments": f"/api/v1/cohorts/{cohort}/enrollments",
            "cohort attendance grid": f"/api/v1/cohorts/{cohort}/attendance",
            "cohort grades": f"/api/v1/cohorts/{cohort}/grades",
            "lesson attendance": f"/api/v1/lessons/{lesson}/attendance",
            "payments list": "/api/v1/payments",
            "payments debtors": "/api/v1/payments/debtors",
            "salaries": "/api/v1/salaries",
            "payouts": "/api/v1/payouts",
            "leads": "/api/v1/leads",
            "audit list": "/api/v1/audit",
            "audit filtered": "/api/v1/audit?section=students&date_from=2026-01-01&q=Азим",
            "me/today": "/api/v1/me/today",
            "export students": "/api/v1/students/export",
            "export payments": "/api/v1/payments/export",
            "export audit": "/api/v1/audit/export",
        }
        for name, url in cases.items():
            r = await c.get(url)
            if r.status_code != 200:
                print(f"!! {name}: {r.status_code} {r.text[:120]}")
                continue
            lat: list[float] = []
            qs: list[int] = []
            n = int(os.environ.get("BENCH_EXPORT_N", "20")) if name.startswith("export") else N
            for _ in range(n):
                counter["n"] = 0
                t = time.perf_counter()
                await c.get(url)
                lat.append((time.perf_counter() - t) * 1000)
                qs.append(counter["n"])
            lat.sort()
            out[name] = {
                "p50": round(statistics.median(lat), 1),
                "p95": round(lat[max(int(len(lat) * 0.95) - 1, 0)], 1),
                "queries": qs[-1],
                "bytes": len(r.content),
            }
            o = out[name]
            print(
                f"{name:24} p50 {o['p50']:8} p95 {o['p95']:8}  q {o['queries']:4}  {o['bytes']}B",
                flush=True,
            )
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w") as f:
            json.dump(out, f, indent=1, ensure_ascii=False)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
