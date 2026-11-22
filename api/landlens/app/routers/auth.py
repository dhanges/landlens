"""Auth (spec 2.9, 2.10; FR-9): signup with 3 free credits, login, logout, me.

Signup writes the user and a `signup_bonus` +3 ledger row in one transaction, so credit_balance = SUM(delta)
holds from the first moment (ADR-010). Auth routes are rate-limited per IP and per email (or user): 10 per
minute per worker (DEC-003, OQ-26).
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Request, Response
from psycopg import errors as pgerr
from pydantic import BaseModel, Field, field_validator

from ..db import fetchone, in_transaction
from ..errors import ApiError
from ..ratelimit import client_ip
from ..security import clear, hash_password, issue, optional_user, require_user, verify_password

router = APIRouter(tags=["auth"])
SIGNUP_BONUS = 3
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Credentials(BaseModel):
    email: str = Field(max_length=254, examples=["you@example.com"])
    password: str = Field(min_length=10, max_length=1024)   # spec 2.10: minimum length 10

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("not a valid email address")
        return v


class LoginBody(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class User(BaseModel):
    user_id: int
    email: str
    credit_balance: int


def limit_ip(request: Request) -> None:
    request.app.state.auth_limiter.hit(("ip", client_ip(request)))


@router.post("/auth/signup", response_model=User, status_code=201, dependencies=[Depends(limit_ip)])
async def signup(body: Credentials, request: Request, response: Response) -> User:
    request.app.state.auth_limiter.hit(("email", body.email))
    pw_hash = await hash_password(body.password)

    async def tx(conn):
        cur = await conn.execute(
            "INSERT INTO app_user (email, password_hash, credit_balance) VALUES (%s, %s, %s) "
            "RETURNING user_id, email, credit_balance", (body.email, pw_hash, SIGNUP_BONUS))
        u = await cur.fetchone()
        await conn.execute("INSERT INTO credit_ledger (user_id, delta, reason) VALUES (%s, %s, 'signup_bonus')",
                           (u["user_id"], SIGNUP_BONUS))
        return u

    try:
        u = await in_transaction(request.app.state.pool, tx)
    except pgerr.UniqueViolation:
        raise ApiError(409, "email_taken", "An account with this email already exists.") from None
    issue(response, request, u["user_id"])
    return User(**u)


@router.post("/auth/login", response_model=User, dependencies=[Depends(limit_ip)])
async def login(body: LoginBody, request: Request, response: Response) -> User:
    email = body.email.strip().lower()
    request.app.state.auth_limiter.hit(("email", email))
    u = await fetchone(request.app.state.pool,
                       "SELECT user_id, email, credit_balance, password_hash FROM app_user WHERE lower(email) = %s",
                       (email,))
    if not await verify_password(u["password_hash"] if u else None, body.password):
        raise ApiError(401, "invalid_credentials", "Email or password is incorrect.")
    issue(response, request, u["user_id"])
    return User(user_id=u["user_id"], email=u["email"], credit_balance=u["credit_balance"])


@router.post("/auth/logout", status_code=204, dependencies=[Depends(limit_ip)])
async def logout(request: Request, user_id: int = Depends(require_user)) -> Response:
    request.app.state.auth_limiter.hit(("user", user_id))
    response = Response(status_code=204)
    clear(response, request)
    return response


@router.get("/me", response_model=User, tags=["auth"])
async def me(request: Request, user_id: int = Depends(require_user)) -> User:
    u = await fetchone(request.app.state.pool,
                       "SELECT user_id, email, credit_balance FROM app_user WHERE user_id = %s", (user_id,))
    if u is None:
        raise ApiError(401, "auth_required", "This session's account no longer exists.")
    return User(**u)


@router.get("/auth/session", tags=["auth"])
async def session(request: Request, user_id: int | None = Depends(optional_user)) -> dict:
    """The current user or null, always 200: lets the web app check for a session without a 401 in the browser
    console on every signed-out page view. /me keeps its 401 contract."""
    if user_id is None:
        return {"user": None}
    u = await fetchone(request.app.state.pool,
                       "SELECT user_id, email, credit_balance FROM app_user WHERE user_id = %s", (user_id,))
    return {"user": User(**u).model_dump() if u else None}
