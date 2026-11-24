"""Advisory lock helpers using PostgreSQL pg_try_advisory_lock."""
import asyncpg


async def try_advisory_lock(pool: asyncpg.Pool, user_id: str) -> bool:
    """Return True if lock acquired, False if another build is running."""
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT pg_try_advisory_lock(hashtext($1))", user_id)


async def release_advisory_lock(pool: asyncpg.Pool, user_id: str) -> None:
    async with pool.acquire() as conn:
        await conn.execute("SELECT pg_advisory_unlock(hashtext($1))", user_id)
