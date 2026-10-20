"""Migrations are hand-written SQL; the URL comes from settings (or alembic's own option)."""

import asyncio

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings


def run(connection: Connection) -> None:
    context.configure(connection=connection, transaction_per_migration=True)
    with context.begin_transaction():
        context.run_migrations()


async def main() -> None:
    url = context.config.get_main_option("sqlalchemy.url") or settings.database_url
    engine = create_async_engine(url)
    async with engine.connect() as conn:
        await conn.run_sync(run)
        await conn.commit()
    await engine.dispose()


connection = context.config.attributes.get("connection")
if connection is not None:
    run(connection)
else:
    asyncio.run(main())
