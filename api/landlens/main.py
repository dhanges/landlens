"""LandLens FastAPI application.

M0 scaffolding: the app exposes only GET /api/health. All endpoints live under
``/api`` and the interactive docs are served at ``/api/docs`` (spec 2.9).
"""

from __future__ import annotations

import os

import psycopg
from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from landlens import __version__

app = FastAPI(
    title="LandLens API",
    version=__version__,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

router = APIRouter(prefix="/api")


class HealthResponse(BaseModel):
    """Health of the backing services (spec 2.9)."""

    db: str
    openai: str


def _db_ok() -> bool:
    """Return True when the database answers ``SELECT 1`` via psycopg 3.

    Connection settings come from the standard libpq environment variables
    (PGHOST, PGUSER, ...); ``DATABASE_URL`` overrides them when set.
    """
    conninfo = os.environ.get("DATABASE_URL", "")
    try:
        with psycopg.connect(conninfo, connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone() == (1,)
    except psycopg.Error:
        return False


def _openai_status() -> str:
    """Report OpenAI health without any external spend (M0, harness cost policy).

    We never call the OpenAI API here: "ok" merely means a key is configured;
    an unset ``OPENAI_API_KEY`` reports "degraded" (graceful fallback, spec 2.1).
    """
    return "ok" if os.environ.get("OPENAI_API_KEY") else "degraded"


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness of the database and OpenAI dependency."""
    return HealthResponse(
        db="ok" if _db_ok() else "error",
        openai=_openai_status(),
    )


app.include_router(router)
