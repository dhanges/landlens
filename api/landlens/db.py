"""Database connections for the API and the landlens CLI (psycopg 3, raw SQL, ADR-002)."""

from __future__ import annotations

import os

import psycopg


def conninfo() -> str:
    """DATABASE_URL when set, otherwise the standard libpq environment (PGHOST, PGUSER, ...)."""
    return os.environ.get("DATABASE_URL", "")


def connect(autocommit: bool = False) -> psycopg.Connection:
    """Connection with the session's as-of date set from AS_OF_DATE when given (DEC-004, OQ-27)."""
    conn = psycopg.connect(conninfo(), autocommit=autocommit)
    as_of = os.environ.get("AS_OF_DATE")
    if as_of:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('landlens.as_of_date', %s, false)", (as_of,))
        if not autocommit:
            conn.commit()
    return conn
