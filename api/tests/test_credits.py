"""Credits (spec 2.11, ADR-010): unlock transaction, idempotency, 402, top-up, ledger, reconciliation."""

from __future__ import annotations

import uuid

import psycopg
import pytest


def key():
    return {"Idempotency-Key": str(uuid.uuid4())}


def reconcile(owner, user_id):
    bal, total, unlocks, charged = owner.execute(
        "SELECT u.credit_balance, (SELECT sum(delta) FROM credit_ledger l WHERE l.user_id = u.user_id),"
        " (SELECT count(*) FROM report_unlock r WHERE r.user_id = u.user_id),"
        " (SELECT count(*) FROM credit_ledger l WHERE l.user_id = u.user_id AND l.reason = 'report_unlock')"
        " FROM app_user u WHERE u.user_id = %s", (user_id,)).fetchone()
    assert bal == total, "credit_balance must equal SUM(ledger.delta)"
    return bal, unlocks, charged


def test_unlock_charges_once_then_402(client, owner, make_user):
    h, u = make_user()
    assert [client.post(f"/api/reports/{p}/unlock", headers={**h, **key()}).json()["charged"]
            for p in (1, 2, 3)] == [1, 1, 1]
    again = client.post("/api/reports/1/unlock", headers={**h, **key()})
    assert again.status_code == 200 and again.json() == {"unlocked": True, "charged": 0, "credit_balance": 0}
    r = client.post("/api/reports/4/unlock", headers={**h, **key()})
    assert r.status_code == 402 and r.json()["error"]["code"] == "insufficient_credits"
    assert reconcile(owner, u["user_id"]) == (0, 3, 3)


def test_idempotency_key_rules(client, owner, make_user):
    h, u = make_user()
    r = client.post("/api/reports/1/unlock", headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "idempotency_key_required"
    r = client.post("/api/reports/1/unlock", headers={**h, "Idempotency-Key": "123"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_idempotency_key"
    k = key()
    assert client.post("/api/reports/1/unlock", headers={**h, **k}).json()["charged"] == 1
    replay = client.post("/api/reports/1/unlock", headers={**h, **k})                 # retried request
    assert replay.status_code == 200 and replay.json()["charged"] == 0
    reused = client.post("/api/reports/2/unlock", headers={**h, **k})                 # same key, other parcel
    assert reused.status_code == 409 and reused.json()["error"]["code"] == "idempotency_key_reused"
    assert reconcile(owner, u["user_id"]) == (2, 1, 1)


def test_unlock_errors(client, make_user):
    assert client.post("/api/reports/1/unlock", headers=key()).status_code == 401
    h, _ = make_user()
    r = client.post("/api/reports/999/unlock", headers={**h, **key()})
    assert r.status_code == 404 and r.json()["error"]["code"] == "parcel_not_found"


def test_topup_and_ledger(client, owner, make_user):
    h, u = make_user()
    r = client.post("/api/credits/topup", headers=h, json={"pack": "20"})
    assert r.status_code == 200
    assert r.json() == {"pack": "20", "credits_added": 20, "price_inr": 6999, "mock": True,
                        "note": "mock payment, no money moves", "credit_balance": 23}
    k = key()
    assert client.post("/api/credits/topup", headers={**h, **k}, json={"pack": "5"}).json()["credits_added"] == 5
    assert client.post("/api/credits/topup", headers={**h, **k}, json={"pack": "5"}).json()["credits_added"] == 0
    assert client.post("/api/credits/topup", headers=h, json={"pack": "7"}).status_code == 422
    assert client.post("/api/credits/topup", json={"pack": "5"}).status_code == 401
    client.post("/api/reports/5/unlock", headers={**h, **key()})
    page1 = client.get("/api/credits/ledger", headers=h, params={"limit": 2}).json()
    assert [(e["reason"], e["delta"]) for e in page1["items"]] == [("report_unlock", -1), ("top_up", 5)]
    assert page1["items"][0]["parcel_id"] == 5 and page1["credit_balance"] == 27
    page2 = client.get("/api/credits/ledger", headers=h, params={"cursor": page1["next_cursor"]}).json()
    assert [(e["reason"], e["delta"]) for e in page2["items"]] == [("top_up", 20), ("signup_bonus", 3)]
    assert page2["next_cursor"] is None
    assert client.get("/api/credits/ledger", headers=h, params={"cursor": "zz"}).status_code == 422
    assert reconcile(owner, u["user_id"])[0] == 27


def test_schema_constraints(owner, make_user):
    """Spec 2.16 schema layer: the database itself rejects negative balances and duplicate unlocks."""
    _, u = make_user()
    with pytest.raises(psycopg.errors.CheckViolation):
        owner.execute("UPDATE app_user SET credit_balance = -1 WHERE user_id = %s", (u["user_id"],))
    owner.execute("INSERT INTO report_unlock (user_id, parcel_id, credits_spent) VALUES (%s, 10, 0)", (u["user_id"],))
    with pytest.raises(psycopg.errors.UniqueViolation):
        owner.execute("INSERT INTO report_unlock (user_id, parcel_id, credits_spent) VALUES (%s, 10, 0)",
                      (u["user_id"],))
    k = uuid.uuid4()
    owner.execute("INSERT INTO credit_ledger (user_id, delta, reason, idempotency_key) VALUES (%s, 1, 'top_up', %s)",
                  (u["user_id"], k))
    with pytest.raises(psycopg.errors.UniqueViolation):
        owner.execute("INSERT INTO credit_ledger (user_id, delta, reason, idempotency_key) "
                      "VALUES (%s, 1, 'top_up', %s)", (u["user_id"], k))
    owner.execute("DELETE FROM report_unlock WHERE user_id = %s", (u["user_id"],))
    owner.execute("DELETE FROM credit_ledger WHERE idempotency_key = %s", (k,))


def test_api_role_cannot_rewrite_ledger(database):
    """landlens_api may append to the ledger, never update or delete it (013)."""
    import os

    from .conftest import _url
    url = _url(database, "landlens_api", os.environ["LANDLENS_API_PASSWORD"])
    with psycopg.connect(url, autocommit=True) as conn:
        for stmt in ("UPDATE credit_ledger SET delta = 100", "DELETE FROM credit_ledger",
                     "CREATE TABLE x (i int)", "ALTER TABLE app_user ADD COLUMN x int"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute(stmt)
