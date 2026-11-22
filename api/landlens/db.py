"""Database connections for the API and the landlens CLI (psycopg 3, raw SQL, ADR-002)."""

from __future__ import annotations

import os

import psycopg


def conninfo() -> str:
    """DATABASE_URL when set, otherwise the standard libpq environment (PGHOST, PGUSER, ...)."""
    return os.environ.get("DATABASE_URL", "")


def connect(autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(conninfo(), autocommit=autocommit)
