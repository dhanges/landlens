"""Async connection pool (spec 2.18 psycopg_pool, spec 2.14 pool of 10 per API worker) and transaction helpers.

Every pooled connection gets the as-of date (DEC-004, OQ-27) and a statement timeout as startup options.
A request that waits longer than POOL_TIMEOUT_S for a connection raises PoolTimeout -> 503 with Retry-After.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

from fastapi import Request
from psycopg import AsyncConnection, errors
from psycopg.rows import dict_row
from psycopg.types.numeric import FloatLoader
from psycopg_pool import AsyncConnectionPool

from .config import Settings
from .errors import ApiError

T = TypeVar("T")
RETRYABLE = (errors.SerializationFailure, errors.DeadlockDetected)   # SQLSTATE 40001, 40P01
MAX_RETRIES = 3                                                        # spec 2.14


async def _configure(conn: AsyncConnection) -> None:
    # numeric -> float, so JSON carries numbers, not strings (money fits float64 exactly to the paisa)
    conn.adapters.register_loader("numeric", FloatLoader)


def make_pool(s: Settings) -> AsyncConnectionPool:
    options = f"-c statement_timeout={s.statement_timeout_ms}"
    if s.as_of_date:
        options += f" -c landlens.as_of_date={s.as_of_date}"
    return AsyncConnectionPool(
        s.database_url, min_size=s.pool_min, max_size=s.pool_max, timeout=s.pool_timeout_s, open=False,
        kwargs={"row_factory": dict_row, "options": options, "application_name": "landlens_api"},
        configure=_configure, name="landlens_api")


def pool(request: Request) -> AsyncConnectionPool:
    return request.app.state.pool


async def fetchall(p: AsyncConnectionPool, query: str, params=None) -> list[dict]:
    async with p.connection() as conn:
        cur = await conn.execute(query, params)
        return await cur.fetchall()


async def fetchone(p: AsyncConnectionPool, query: str, params=None) -> dict | None:
    async with p.connection() as conn:
        cur = await conn.execute(query, params)
        return await cur.fetchone()


async def in_transaction(p: AsyncConnectionPool, fn: Callable[[AsyncConnection], Awaitable[T]]) -> T:
    """Run fn(conn) in one transaction; retry 40001/40P01 up to 3 times with jitter, then 503 (spec 2.14)."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            async with p.connection() as conn, conn.transaction():
                return await fn(conn)
        except RETRYABLE:
            if attempt == MAX_RETRIES:
                raise ApiError(503, "serialization_failure", "Too much contention, retry shortly.",
                               {"Retry-After": "1"}) from None
            await asyncio.sleep(random.uniform(0.005, 0.02) * 2 ** attempt)
    raise AssertionError("unreachable")
