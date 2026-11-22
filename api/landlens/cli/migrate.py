"""`landlens migrate`: numbered SQL migrations with checksums (spec 2.17).

- Applies db/migrations/NNN_*.sql in filename order, each in its own transaction.
- Records filename and SHA-256 checksum in schema_migrations; refuses to run if an already-applied file changed.
- Phases by file number: 010, 011, 012, 014 form the post-load phase; every other file (001-009, 013) the schema phase.
- After the schema phase, sets the passwords of landlens_api / landlens_tiles from LANDLENS_API_PASSWORD /
  LANDLENS_TILES_PASSWORD when those are set, so no secret lives in a migration file (DEC-004).
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path

from psycopg import sql

from landlens.db import connect

POST_LOAD = {"010", "011", "012", "014"}
FILE_RE = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")


def migrations_dir() -> Path:
    return Path(os.environ.get("LANDLENS_MIGRATIONS_DIR", "/app/migrations"))


def discover(phase: str) -> list[Path]:
    files = []
    for p in sorted(migrations_dir().glob("*.sql")):
        m = FILE_RE.match(p.name)
        if not m:
            raise SystemExit(f"migrate: unexpected file name {p.name} (expected NNN_name.sql)")
        is_post = m.group(1) in POST_LOAD
        if phase == "all" or (phase == "post-load") == is_post:
            files.append(p)
    return files


def checksum(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def set_role_passwords(cur) -> None:
    for role, env in (("landlens_api", "LANDLENS_API_PASSWORD"), ("landlens_tiles", "LANDLENS_TILES_PASSWORD")):
        pw = os.environ.get(env)
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        if pw and cur.fetchone():
            cur.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(role), sql.Literal(pw)))
            print(f"  set password for {role} from {env}")


def run(phase: str) -> int:
    files = discover(phase)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                     filename   text PRIMARY KEY,
                     checksum   char(64) NOT NULL,
                     applied_at timestamptz NOT NULL DEFAULT now())"""
            )
            cur.execute("SELECT filename, checksum FROM schema_migrations")
            applied = dict(cur.fetchall())
        conn.commit()

        # refuse to run if any applied file changed (all phases, not just this one)
        changed = [p.name for p in discover("all") if p.name in applied and applied[p.name] != checksum(p)]
        if changed:
            print("migrate: refusing to run, applied migration files changed: " + ", ".join(changed), file=sys.stderr)
            return 1

        n = 0
        for p in files:
            if p.name in applied:
                continue
            print(f"  applying {p.name}")
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(p.read_text())
                cur.execute("INSERT INTO schema_migrations (filename, checksum) VALUES (%s, %s)", (p.name, checksum(p)))
            n += 1
        if phase in ("schema", "all"):
            with conn.transaction(), conn.cursor() as cur:
                set_role_passwords(cur)
    print(f"migrate --phase {phase}: {n} applied, {len(files) - n} already up to date")
    return 0
