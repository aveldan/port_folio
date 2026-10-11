"""Checks that the local Postgres and Redis servers configured in .env are reachable."""

import asyncpg
import pytest
import redis.asyncio as redis

pytestmark = pytest.mark.anyio


async def test_postgres_is_reachable(database_url: str):
    # asyncpg takes a plain postgresql:// URL, without SQLAlchemy's +asyncpg driver suffix.
    conn = await asyncpg.connect(database_url.replace("postgresql+asyncpg://", "postgresql://", 1))
    try:
        version = await conn.fetchval("SELECT version()")
    finally:
        await conn.close()
    assert version.startswith("PostgreSQL")


async def test_redis_is_reachable(redis_url: str):
    client = redis.from_url(redis_url)
    try:
        assert await client.ping() is True
    finally:
        await client.aclose()
