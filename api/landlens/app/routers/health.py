"""GET /health (spec 2.9)."""

from __future__ import annotations

import os

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    db: str
    openai: str


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Database answers SELECT 1 through the pool; OpenAI is "ok" when a key is configured (never called here)."""
    try:
        async with request.app.state.pool.connection(timeout=3) as conn:
            cur = await conn.execute("SELECT 1 AS ok")
            db_ok = (await cur.fetchone())["ok"] == 1
    except Exception:
        db_ok = False
    return HealthResponse(db="ok" if db_ok else "error", openai="ok" if os.environ.get("OPENAI_API_KEY") else "degraded")
