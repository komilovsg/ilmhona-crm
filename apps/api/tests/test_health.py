import httpx
import pytest

from app.core.config import settings


async def test_health_reports_the_running_commit(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "render_git_commit", "0123abcd" * 5)
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": "0123abcd" * 5}


async def test_health_without_a_commit_says_dev(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "render_git_commit", "")
    assert (await client.get("/api/health")).json()["version"] == "dev"
