"""asyncpg connection pool — initialized on app startup, closed on shutdown."""
import json
import os
import asyncpg

_pool: asyncpg.Pool | None = None

DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://studyflow:studyflow@localhost:5432/studyflow",
).replace("+asyncpg", "")


async def _init_conn(conn):
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def init_pool():
    global _pool
    _pool = await asyncpg.create_pool(DSN, min_size=2, max_size=10, init=_init_conn)


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised — call init_pool() first")
    return _pool
