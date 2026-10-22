"""Engine and the request session. The session commits when the handler returns, before the
response is sent (function-scoped dependency), so a failed commit is an error response."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# Neon (direct URL, free compute): few connections, and an idle one is dropped when the compute
# suspends (~5 min), so connections are recycled before that and pinged on checkout. The pool is
# sized for one Render instance: 5 held + 5 burst, far below Neon's connection cap.
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=settings.db_pool_recycle,
    pool_timeout=15,
    # bound values (names, phones, amounts) stay out of error messages, logs and Sentry
    hide_parameters=True,
)
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
