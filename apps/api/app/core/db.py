"""Engine and the request session. The session commits when the handler returns, before the
response is sent (function-scoped dependency), so a failed commit is an error response."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
sessionmaker = async_sessionmaker(engine, expire_on_commit=False)


async def _session() -> AsyncIterator[AsyncSession]:
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


DB = Annotated[AsyncSession, Depends(_session, scope="function")]
