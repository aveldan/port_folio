import asyncio
import asyncpg
import redis.asyncio as redis

async def main():
    conn = await asyncpg.connect(
        user="m5demon_portfolio",
        password="demon@1749",
        host="localhost",
        port=5432,
        database="portfolio",
    )
    print("Postgres:", await conn.fetchval("SELECT version()"))
    await conn.close()

    r = redis.from_url("redis://localhost:6379/0")
    print("Redis:", await r.ping())
    await r.aclose()

asyncio.run(main())