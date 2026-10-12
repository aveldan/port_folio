"""Shared pytest fixtures.

Database tests run against the real local Postgres from .env. Each test gets its
own transaction: tables are created inside it and everything is rolled back when
the test ends, so tests never see each other's data and the database is left as
it was.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import configure_mappers

import app.db.models  # noqa: F401  (registers every model on Base.metadata)
from app.db.base import Base

ROOT = Path(__file__).resolve().parent.parent

configure_mappers()


def _read_setting(name: str) -> str:
    """Read a setting from the environment, falling back to the project's .env file."""
    if name in os.environ:
        return os.environ[name]
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == name:
                return value.strip().strip("'\"")
    pytest.fail(f"{name} is not set in the environment or in {env_file}", pytrace=False)


@pytest.fixture
def anyio_backend() -> str:
    # Run async tests on asyncio only (anyio would otherwise also try trio).
    return "asyncio"


@pytest.fixture(scope="session")
def database_url() -> str:
    return _read_setting("DATABASE_URL")


@pytest.fixture(scope="session")
def redis_url() -> str:
    return _read_setting("REDIS_URL")


@pytest.fixture
async def db(database_url: str):
    """An AsyncSession inside a transaction that is always rolled back."""
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            trans = await conn.begin()
            await conn.run_sync(Base.metadata.create_all)
            # Commits inside tests become savepoints, so the outer rollback still undoes them.
            session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
            try:
                yield session
            finally:
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()


@pytest.fixture
def rejected_by(db: AsyncSession):
    """Assert that the database rejects whatever the block adds or executes.

    Usage:
        async with rejected_by("ck_folio_holdings_quantity_non_negative"):
            db.add(Holding(...))

    The block runs in a savepoint and is flushed at the end. The test fails unless
    Postgres raises an IntegrityError whose message mentions `expected`, which is
    usually a constraint name. The savepoint is rolled back, so the session stays usable.
    """

    @asynccontextmanager
    async def _rejected_by(expected: str):
        with pytest.raises(IntegrityError) as exc_info:
            async with db.begin_nested():
                yield
                await db.flush()
        message = str(exc_info.value.orig)
        assert expected in message, f"rejected for a different reason: {message.splitlines()[0]}"

    return _rejected_by
