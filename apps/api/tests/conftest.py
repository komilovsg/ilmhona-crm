"""Tests run against a fresh database `TEST_DB_NAME` (default `ilmhona_test`) on the Postgres
that DATABASE_URL points to (compose.yaml, CI service). Never the dev database."""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

TEST_DB = os.environ.get("TEST_DB_NAME", "ilmhona_test")
SERVER_URL = make_url(
    os.environ.get("DATABASE_URL", "postgresql+asyncpg://ilm@localhost:55433/ilmhona")
)
TEST_URL = SERVER_URL.set(database=TEST_DB)
# Point the app itself at the test database before anything imports its settings or engine.
os.environ["DATABASE_URL"] = TEST_URL.render_as_string(hide_password=False)
os.environ["ENV"] = "test"
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-123"

from app.core.db import sessionmaker  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AppUser, Branch, Role  # noqa: E402

PASSWORD = "Passw0rd!x"


async def _recreate_database() -> None:
    admin = create_async_engine(SERVER_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)'))
        await conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    await admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    # Sync fixture: alembic's env.py calls asyncio.run, which needs no running loop.
    asyncio.run(_recreate_database())
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", TEST_URL.render_as_string(hide_password=False))
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
async def clean(migrated_database: None) -> None:
    """Every test starts with the seeded branches and system roles only."""
    async with sessionmaker() as db:
        for sql in (
            "DELETE FROM audit_log",
            "DELETE FROM refresh_token",
            "DELETE FROM login_attempt",
            "DELETE FROM app_user",
            "DELETE FROM role WHERE code IS NULL",
        ):
            await db.execute(text(sql))
        await db.commit()


Client = httpx.AsyncClient


def make_client() -> httpx.AsyncClient:
    """A browser: its own cookie jar; the CSRF header is set like the web app does."""
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Requested-With": "ilm"},
    )


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with make_client() as c:
        yield c


@pytest.fixture
async def browser() -> AsyncIterator[Callable[[], httpx.AsyncClient]]:
    """Factory for more than one signed-in user in a test."""
    opened: list[httpx.AsyncClient] = []

    def new() -> httpx.AsyncClient:
        c = make_client()
        opened.append(c)
        return c

    yield new
    for c in opened:
        await c.aclose()


async def branch_id(name: str) -> uuid.UUID:
    async with sessionmaker() as db:
        return (
            await db.execute(text("SELECT id FROM branch WHERE name = :n"), {"n": name})
        ).scalar_one()


async def role_id(code: str) -> uuid.UUID:
    async with sessionmaker() as db:
        return (
            await db.execute(text("SELECT id FROM role WHERE code = :c"), {"c": code})
        ).scalar_one()


async def make_role(name: str, permissions: dict[str, str]) -> uuid.UUID:
    async with sessionmaker() as db:
        rid = (
            await db.execute(text("INSERT INTO role (name) VALUES (:n) RETURNING id"), {"n": name})
        ).scalar_one()
        for section, level in permissions.items():
            await db.execute(
                text("INSERT INTO role_permission VALUES (:r, :s, :l)"),
                {"r": rid, "s": section, "l": level},
            )
        await db.commit()
        return rid  # type: ignore[no-any-return]


async def make_user(
    login: str,
    role: uuid.UUID | str,
    *,
    branch: str | None = None,
    password: str = PASSWORD,
    must_change: bool = False,
    active: bool = True,
    phone: str | None = None,
) -> uuid.UUID:
    rid = await role_id(role) if isinstance(role, str) else role
    async with sessionmaker() as db:
        user = AppUser(
            login=login,
            full_name=f"User {login}",
            phone=phone,
            branch_id=await branch_id(branch) if branch else None,
            role_id=rid,
            is_active=active,
            password_hash=hash_password(password),
            must_change_password=must_change,
        )
        db.add(user)
        await db.commit()
        return user.id


async def sign_in(c: httpx.AsyncClient, login: str, password: str = PASSWORD) -> dict[str, Any]:
    r = await c.post("/api/v1/auth/login", json={"login": login, "password": password})
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


SignedIn = Callable[..., Awaitable[httpx.AsyncClient]]


@pytest.fixture
async def login_as(browser: Callable[[], httpx.AsyncClient]) -> SignedIn:
    """`await login_as("anna", "manager", branch="Душанбе")` -> a client signed in as them."""

    async def go(login: str, role: uuid.UUID | str, **kwargs: Any) -> httpx.AsyncClient:
        await make_user(login, role, **kwargs)
        c = browser()
        await sign_in(c, login)
        return c

    return go


@pytest.fixture
async def admin(login_as: SignedIn) -> httpx.AsyncClient:
    return await login_as("root", "superadmin")


async def sql(query: str, **params: Any) -> Any:
    async with sessionmaker() as db:
        result = await db.execute(text(query), params)
        await db.commit()
        return result.all() if result.returns_rows else None


_ = (Branch, Role)
