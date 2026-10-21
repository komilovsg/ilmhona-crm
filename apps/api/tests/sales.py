"""Fixtures for the sales tests: leads, campaigns (all fake)."""

import uuid
from typing import Any

import httpx

from app.permissions import MANAGER_DEFAULT
from tests.conftest import branch_id, make_role

L = "/api/v1/leads"
CA = "/api/v1/campaigns"
M = "/api/v1/metrics"


async def make_lead(
    c: httpx.AsyncClient, name: str = "Алишер Каримов", *, branch: str = "Душанбе", **kw: Any
) -> dict[str, Any]:
    r = await c.post(L, json={"full_name": name, "branch_id": str(await branch_id(branch)), **kw})
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def make_campaign(
    c: httpx.AsyncClient,
    name: str = "Осень",
    *,
    branch: str = "Душанбе",
    budget: str | int = 1000,
    **kw: Any,
) -> dict[str, Any]:
    r = await c.post(
        CA,
        json={
            "name": name,
            "branch_id": str(await branch_id(branch)),
            "platform": "Facebook Ads",
            "start_date": "2026-09-01",
            "budget": str(budget),
            **kw,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def manager_role() -> uuid.UUID:
    return await make_role("Менеджер (тест)", dict(MANAGER_DEFAULT))


def csv_bytes(rows: list[list[str]], delimiter: str = ",") -> bytes:
    def esc(v: str) -> str:
        return f'"{v}"' if any(ch in v for ch in (delimiter, '"', "\n")) else v

    return "\n".join(delimiter.join(esc(v) for v in r) for r in rows).encode()
