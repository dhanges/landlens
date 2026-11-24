"""API settings from the environment, read once when the app starts (tests set the environment first)."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from dataclasses import dataclass

from landlens.db import conninfo

log = logging.getLogger("landlens.config")


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name, "").strip().lower()
    return default if v == "" else v in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    v = os.environ.get(name, "").strip()
    return int(v) if v else default


@dataclass(frozen=True)
class Settings:
    database_url: str           # the server connects as landlens_api (spec 2.10); the CLI keeps DATABASE_URL
    jwt_secret: str
    cookie_secure: bool         # DEC-003 (OQ-25): Secure by default behind COOKIE_SECURE
    as_of_date: str | None      # DEC-004 (OQ-27)
    pool_min: int
    pool_max: int               # spec 2.14: pool of 10 per API worker
    pool_timeout_s: float       # waiting longer for a connection gives 503 + Retry-After (spec 2.14)
    statement_timeout_ms: int
    rate_auth_per_min: int      # spec 2.10: 10 per minute on auth routes
    rate_chat_per_min: int      # spec 2.10: 20 per minute on chat (M5)
    rate_window_s: int
    chat_max_distance: float    # spec 2.13 not-found rule: best cosine distance above this and no keyword hit
    seed_inputs: str            # documents are served from here (file_path is relative to it)


def _jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET", "")
    if secret:
        if len(secret.encode()) < 32:
            # HS256 keys under 32 bytes are brute-forceable offline from one captured token (RFC 7518 3.2)
            log.warning("JWT_SECRET is %d bytes; use at least 32 random bytes (openssl rand -hex 32)",
                        len(secret.encode()))
        return secret
    # Fallback so `make up` works with an empty JWT_SECRET: a key derived from the landlens_api password, which
    # every API worker shares. Logged loudly; set JWT_SECRET in .env for anything beyond local use.
    base = os.environ.get("LANDLENS_API_PASSWORD", "")
    if not base:
        raise RuntimeError("JWT_SECRET is not set (and no LANDLENS_API_PASSWORD to derive a local key from)")
    log.warning("JWT_SECRET is empty: using a key derived from LANDLENS_API_PASSWORD (set JWT_SECRET in .env)")
    return hmac.new(base.encode(), b"landlens-jwt-v1", hashlib.sha256).hexdigest()


def load() -> Settings:
    return Settings(
        database_url=os.environ.get("API_DATABASE_URL") or conninfo(),
        jwt_secret=_jwt_secret(),
        cookie_secure=_bool("COOKIE_SECURE", True),
        as_of_date=os.environ.get("AS_OF_DATE") or None,
        pool_min=_int("POOL_MIN", 2),
        pool_max=_int("POOL_MAX", 10),
        pool_timeout_s=float(os.environ.get("POOL_TIMEOUT_S", "5")),
        statement_timeout_ms=_int("STATEMENT_TIMEOUT_MS", 15000),
        rate_auth_per_min=_int("RATE_LIMIT_AUTH", 10),
        rate_chat_per_min=_int("RATE_LIMIT_CHAT", 20),
        rate_window_s=_int("RATE_LIMIT_WINDOW_S", 60),
        chat_max_distance=float(os.environ.get("CHAT_MAX_DISTANCE") or 0.6),
        seed_inputs=os.environ.get("LANDLENS_SEED_INPUTS", "/app/seed_inputs"),
    )
