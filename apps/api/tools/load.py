"""Parallel load against a running API (local only): N workers, each M mixed requests.

    uv run python -m tools.load http://127.0.0.1:8580 [workers] [requests per worker]
"""

import asyncio
import sys
import time

import httpx

BASE = sys.argv[1]
WORKERS = int(sys.argv[2]) if len(sys.argv) > 2 else 20
EACH = int(sys.argv[3]) if len(sys.argv) > 3 else 50
URLS = [
    "/api/v1/auth/me",
    "/api/v1/dashboard/overview",
    "/api/v1/students",
    "/api/v1/payments",
    "/api/v1/cohorts",
    "/api/v1/graduates/students",
    "/api/v1/audit",
]


async def worker(c: httpx.AsyncClient, k: int, bad: list[str]) -> None:
    for i in range(EACH):
        try:
            r = await c.get(URLS[(i + k) % len(URLS)])
            if r.status_code != 200:
                bad.append(str(r.status_code))
        except httpx.HTTPError as exc:
            bad.append(type(exc).__name__)


async def main() -> None:
    bad: list[str] = []
    async with httpx.AsyncClient(
        base_url=BASE, headers={"x-requested-with": "ilm"}, timeout=30, limits=httpx.Limits(max_connections=WORKERS)
    ) as c:
        r = await c.post("/api/v1/auth/login", json={"login": "load_admin", "password": "Load-test-pass-1"})
        assert r.status_code == 200, r.text
        t = time.perf_counter()
        await asyncio.gather(*(worker(c, k, bad) for k in range(WORKERS)))
        dt = time.perf_counter() - t
    total = WORKERS * EACH
    print(f"{total} requests, {WORKERS} parallel, {dt:.1f}s, {total / dt:.0f} req/s, errors: {len(bad)} {set(bad)}")


asyncio.run(main())
