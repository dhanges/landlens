"""Passwords, sessions and the session dependencies (spec 2.10, DEC-003 OQ-13/OQ-25).

- argon2id hashes (argon2-cffi defaults), hashed off the event loop; unknown emails still pay one verify, so
  login timing does not reveal which emails exist.
- Session: HS256 JWT, 24-hour expiry, in an httpOnly, SameSite=Lax cookie that is Secure unless COOKIE_SECURE=false.
"""

from __future__ import annotations

import time

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Request, Response
from starlette.concurrency import run_in_threadpool

from .errors import ApiError

COOKIE = "landlens_session"
TTL_S = 24 * 3600
ALG = "HS256"
_ph = PasswordHasher()                   # argon2id
_DUMMY_HASH = _ph.hash("landlens-dummy-password")


async def hash_password(pw: str) -> str:
    return await run_in_threadpool(_ph.hash, pw)


async def verify_password(stored_hash: str | None, pw: str) -> bool:
    def _verify() -> bool:
        try:
            return _ph.verify(stored_hash or _DUMMY_HASH, pw) and stored_hash is not None
        except (VerificationError, InvalidHashError):
            return False
    return await run_in_threadpool(_verify)


def issue(response: Response, request: Request, user_id: int) -> None:
    s = request.app.state.settings
    now = int(time.time())
    token = jwt.encode({"sub": str(user_id), "iat": now, "exp": now + TTL_S}, s.jwt_secret, algorithm=ALG)
    response.set_cookie(COOKIE, token, max_age=TTL_S, path="/", httponly=True, secure=s.cookie_secure, samesite="lax")


def clear(response: Response, request: Request) -> None:
    s = request.app.state.settings
    response.delete_cookie(COOKIE, path="/", httponly=True, secure=s.cookie_secure, samesite="lax")


def _user_id(request: Request) -> int | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    try:
        claims = jwt.decode(token, request.app.state.settings.jwt_secret, algorithms=[ALG],
                            options={"require": ["exp", "sub"]})
        return int(claims["sub"])
    except (jwt.PyJWTError, ValueError):
        return None


def optional_user(request: Request) -> int | None:
    """User id from a valid session cookie, or None (free routes that change with a session, OQ-29)."""
    return _user_id(request)


def require_user(request: Request) -> int:
    uid = _user_id(request)
    if uid is None:
        raise ApiError(401, "auth_required", "Sign in to continue.")
    return uid
