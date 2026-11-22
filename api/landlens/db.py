"""Database connections for the API and the landlens CLI (psycopg 3, raw SQL, ADR-002)."""

from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

import psycopg


def conninfo() -> str:
    """DATABASE_URL when set, otherwise the standard libpq environment (PGHOST, PGUSER, ...).
    LANDLENS_DB_NAME switches the database (e.g. landlens_sf5 for the SF5 benchmarks, spec 3.3 M2)."""
    url = os.environ.get("DATABASE_URL", "")
    name = os.environ.get("LANDLENS_DB_NAME")
    if name and url:
        parts = urlsplit(url)
        url = urlunsplit(parts._replace(path=f"/{name}"))
    return url


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
