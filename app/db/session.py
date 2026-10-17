from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Build the engine and session factory on first use, so importing the app doesn't need a database."""
    engine = create_async_engine(get_settings().database_url)
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields one AsyncSession per request."""
    async with get_sessionmaker()() as session:
        yield session
