"""Credits (spec 2.9, 2.11, ADR-010, FR-10): report unlock, mock top-up, ledger.

POST /reports/{id}/unlock runs the spec 2.11 transaction, READ COMMITTED with a row lock:

    BEGIN;
    SELECT credit_balance FROM app_user WHERE user_id = $u FOR UPDATE;   -- serializes this user's purchases
    -- already unlocked -> COMMIT, charged = 0
    -- credit_balance < 1 -> ROLLBACK, 402 insufficient_credits
    INSERT INTO report_unlock (user_id, parcel_id, credits_spent) VALUES ($u, $p, 1);
    INSERT INTO credit_ledger (user_id, delta, reason, parcel_id, idempotency_key) VALUES ($u, -1, 'report_unlock', $p, $key);
    UPDATE app_user SET credit_balance = credit_balance - 1 WHERE user_id = $u;
    COMMIT;

Three layers stop double charges: the row lock, the report_unlock primary key, the unique idempotency_key.
A missing Idempotency-Key -> 422 idempotency_key_required (DEC-003, OQ-29). The same key replayed for the same
parcel is "already unlocked" -> charged 0; a key already used for another unlock -> 409 idempotency_key_reused.
40001/40P01 are retried 3 times with jitter, then 503 (spec 2.14); pool exhaustion -> 503 with Retry-After.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from psycopg import errors as pgerr
from pydantic import BaseModel

from ..db import fetchall, fetchone, in_transaction
from ..errors import ApiError
from ..security import require_user
from .parcels import PARCEL_ID

router = APIRouter(tags=["credits"])

# DEC-004 (OQ-23): mock packs, "mock payment, no money moves"
PACKS = {"5": {"credits": 5, "price_inr": 1999}, "20": {"credits": 20, "price_inr": 6999},
         "50": {"credits": 50, "price_inr": 14999}}
MOCK_NOTE = "mock payment, no money moves"


class UnlockResponse(BaseModel):
    unlocked: bool
    charged: int
    credit_balance: int


def _key(raw: str | None, required: bool) -> uuid.UUID | None:
    if raw is None or raw.strip() == "":
        if required:
            raise ApiError(422, "idempotency_key_required", "Send an Idempotency-Key header (a UUID).")
        return None
    try:
        return uuid.UUID(raw.strip())
    except ValueError:
        raise ApiError(422, "invalid_idempotency_key", "Idempotency-Key must be a UUID.") from None


@router.post("/reports/{parcel_id}/unlock", response_model=UnlockResponse)
async def unlock(request: Request, parcel_id: int = PARCEL_ID, user_id: int = Depends(require_user),
                 idempotency_key: str | None = Header(None, alias="Idempotency-Key")) -> UnlockResponse:
    """Spend 1 credit to unlock a parcel report, at most once per user and parcel (spec 2.11)."""
    key = _key(idempotency_key, required=True)
    pool = request.app.state.pool
    if await fetchone(pool, "SELECT 1 FROM parcel WHERE parcel_id = %s", (parcel_id,)) is None:
        raise ApiError(404, "parcel_not_found", f"No parcel with id {parcel_id}.")

    async def tx(conn) -> UnlockResponse:
        cur = await conn.execute("SELECT credit_balance FROM app_user WHERE user_id = %s FOR UPDATE", (user_id,))
        row = await cur.fetchone()
        if row is None:
            raise ApiError(401, "auth_required", "This session's account no longer exists.")
        balance = row["credit_balance"]
        cur = await conn.execute("SELECT 1 FROM report_unlock WHERE user_id = %s AND parcel_id = %s",
                                 (user_id, parcel_id))
        if await cur.fetchone() is not None:
            return UnlockResponse(unlocked=True, charged=0, credit_balance=balance)          # COMMIT, charged 0
        if balance < 1:
            raise ApiError(402, "insufficient_credits", "Not enough credits: top up to unlock this report.")
        await conn.execute("INSERT INTO report_unlock (user_id, parcel_id, credits_spent) VALUES (%s, %s, 1)",
                           (user_id, parcel_id))
        await conn.execute("INSERT INTO credit_ledger (user_id, delta, reason, parcel_id, idempotency_key) "
                           "VALUES (%s, -1, 'report_unlock', %s, %s)", (user_id, parcel_id, key))
        cur = await conn.execute("UPDATE app_user SET credit_balance = credit_balance - 1 WHERE user_id = %s "
                                 "RETURNING credit_balance", (user_id,))
        return UnlockResponse(unlocked=True, charged=1, credit_balance=(await cur.fetchone())["credit_balance"])

    for attempt in range(2):
        try:
            return await in_transaction(pool, tx)
        except pgerr.UniqueViolation as e:
            if e.diag.constraint_name == "credit_ledger_idempotency_key_key":
                raise ApiError(409, "idempotency_key_reused",
                               "This Idempotency-Key was already used for another request.") from None
            # report_unlock_pkey: the row lock makes this unreachable, but if it ever fires, a second run sees the
            # unlock and returns charged 0 (the primary key is the second layer against double charges).
            if e.diag.constraint_name != "report_unlock_pkey" or attempt == 1:
                raise
    raise AssertionError("unreachable")


class TopUpBody(BaseModel):
    pack: Literal["5", "20", "50"]


@router.post("/credits/topup")
async def topup(body: TopUpBody, request: Request, user_id: int = Depends(require_user),
                idempotency_key: str | None = Header(None, alias="Idempotency-Key")) -> dict:
    """Mock top-up: adds a top_up ledger row and the pack's credits; no money moves (DEC-004, OQ-23).
    An optional Idempotency-Key makes a retried top-up a no-op."""
    key = _key(idempotency_key, required=False)
    pack = PACKS[body.pack]

    async def tx(conn) -> dict:
        cur = await conn.execute("SELECT credit_balance FROM app_user WHERE user_id = %s FOR UPDATE", (user_id,))
        row = await cur.fetchone()
        if row is None:
            raise ApiError(401, "auth_required", "This session's account no longer exists.")
        if key is not None:
            cur = await conn.execute("SELECT user_id, reason FROM credit_ledger WHERE idempotency_key = %s", (key,))
            prev = await cur.fetchone()
            if prev is not None:
                if prev["user_id"] != user_id or prev["reason"] != "top_up":
                    raise ApiError(409, "idempotency_key_reused",
                                   "This Idempotency-Key was already used for another request.")
                return {"pack": body.pack, "credits_added": 0, "price_inr": pack["price_inr"], "mock": True,
                        "note": MOCK_NOTE, "credit_balance": row["credit_balance"]}
        await conn.execute("INSERT INTO credit_ledger (user_id, delta, reason, idempotency_key) "
                           "VALUES (%s, %s, 'top_up', %s)", (user_id, pack["credits"], key))
        cur = await conn.execute("UPDATE app_user SET credit_balance = credit_balance + %s WHERE user_id = %s "
                                 "RETURNING credit_balance", (pack["credits"], user_id))
        return {"pack": body.pack, "credits_added": pack["credits"], "price_inr": pack["price_inr"], "mock": True,
                "note": MOCK_NOTE, "credit_balance": (await cur.fetchone())["credit_balance"]}

    try:
        return await in_transaction(request.app.state.pool, tx)
    except pgerr.UniqueViolation:
        raise ApiError(409, "idempotency_key_reused", "This Idempotency-Key was already used.") from None


def _ledger_cursor(raw: str) -> tuple[str, int]:
    try:
        c = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        if isinstance(c, list) and len(c) == 2 and isinstance(c[0], str) and isinstance(c[1], int):
            return c[0], c[1]
    except (ValueError, binascii.Error, UnicodeDecodeError):
        pass
    raise ApiError(422, "invalid_cursor", "The cursor is malformed.")


@router.get("/credits/ledger")
async def ledger(request: Request, user_id: int = Depends(require_user),
                 cursor: str | None = Query(None, max_length=200), limit: int = Query(50, ge=1, le=100)) -> dict:
    """Your ledger entries, newest first, keyset on (created_at, entry_id) (ledger_user_ix)."""
    pool = request.app.state.pool
    params = {"uid": user_id, "lim": limit + 1, "ts": None, "eid": None}
    if cursor:
        params["ts"], params["eid"] = _ledger_cursor(cursor)
    rows = await fetchall(pool, """
        SELECT entry_id, delta, reason::text AS reason, parcel_id, created_at FROM credit_ledger
        WHERE user_id = %(uid)s
          AND (%(ts)s::timestamptz IS NULL OR (created_at, entry_id) < (%(ts)s::timestamptz, %(eid)s::bigint))
        ORDER BY created_at DESC, entry_id DESC LIMIT %(lim)s""", params)
    bal = await fetchone(pool, "SELECT credit_balance FROM app_user WHERE user_id = %s", (user_id,))
    items = rows[:limit]
    nxt = None
    if len(rows) > limit:
        last = items[-1]
        nxt = base64.urlsafe_b64encode(json.dumps([last["created_at"].isoformat(), last["entry_id"]]).encode()
                                       ).decode().rstrip("=")
    return {"items": items, "next_cursor": nxt, "credit_balance": bal["credit_balance"] if bal else None}
