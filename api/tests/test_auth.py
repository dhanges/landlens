"""Auth (spec 2.9, 2.10): signup with 3 credits and a signup_bonus ledger row, login, logout, me, rate limits."""

from __future__ import annotations

import uuid

from .conftest import session_headers

PW = "correct horse battery"


def _email():
    return f"a{uuid.uuid4().hex[:12]}@example.com"


def test_signup_sets_cookie_and_three_credits(client, owner):
    email = _email()
    r = client.post("/api/auth/signup", json={"email": email.upper(), "password": PW})
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == email and body["credit_balance"] == 3
    cookie = r.headers["set-cookie"].lower()
    for attr in ("httponly", "secure", "samesite=lax", "max-age=86400", "path=/"):
        assert attr in cookie
    row = owner.execute("SELECT u.credit_balance, u.password_hash, array_agg(l.reason::text), sum(l.delta) "
                        "FROM app_user u JOIN credit_ledger l USING (user_id) WHERE u.user_id = %s GROUP BY 1, 2",
                        (body["user_id"],)).fetchone()
    assert row[0] == 3 and row[2] == ["signup_bonus"] and row[3] == 3
    assert row[1].startswith("$argon2id$")


def test_signup_validation_and_duplicates(client):
    assert client.post("/api/auth/signup", json={"email": _email(), "password": "short"}).status_code == 422
    r = client.post("/api/auth/signup", json={"email": "not-an-email", "password": PW})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    email = _email()
    assert client.post("/api/auth/signup", json={"email": email, "password": PW}).status_code == 201
    r = client.post("/api/auth/signup", json={"email": email.upper(), "password": PW})
    assert r.status_code == 409 and r.json() == {"error": {"code": "email_taken",
                                                           "message": "An account with this email already exists."}}


def test_login_me_logout(client):
    email = _email()
    client.post("/api/auth/signup", json={"email": email, "password": PW})
    client.cookies.clear()
    bad = client.post("/api/auth/login", json={"email": email, "password": "wrong password"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "invalid_credentials"
    unknown = client.post("/api/auth/login", json={"email": _email(), "password": PW})
    assert unknown.status_code == 401 and unknown.json()["error"]["code"] == "invalid_credentials"
    ok = client.post("/api/auth/login", json={"email": email, "password": PW})
    assert ok.status_code == 200 and ok.json()["email"] == email
    h = session_headers(ok)
    client.cookies.clear()
    me = client.get("/api/me", headers=h)
    assert me.status_code == 200 and me.json()["credit_balance"] == 3
    out = client.post("/api/auth/logout", headers=h)
    assert out.status_code == 204 and "max-age=0" in out.headers["set-cookie"].lower()


def test_session_required_and_tampered_tokens(client):
    for path in ("/api/me", "/api/credits/ledger"):
        r = client.get(path)
        assert r.status_code == 401 and r.json()["error"]["code"] == "auth_required"
    assert client.post("/api/auth/logout").status_code == 401
    r = client.get("/api/me", headers={"cookie": "landlens_session=eyJhbGciOiJub25lIn0.eyJzdWIiOiIxIn0."})
    assert r.status_code == 401
    import jwt
    forged = jwt.encode({"sub": "1", "exp": 9999999999}, "not-the-secret", algorithm="HS256")
    assert client.get("/api/me", headers={"cookie": f"landlens_session={forged}"}).status_code == 401
    expired = jwt.encode({"sub": "1", "exp": 1}, client.app.state.settings.jwt_secret, algorithm="HS256")
    assert client.get("/api/me", headers={"cookie": f"landlens_session={expired}"}).status_code == 401


def test_auth_rate_limit_per_ip(client):
    email = _email()
    codes = [client.post("/api/auth/login", json={"email": f"{i}{email}", "password": PW}).status_code
             for i in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429
    r = client.post("/api/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited" and int(r.headers["retry-after"]) >= 1


def test_auth_rate_limit_per_email(client):
    email = _email()
    lim = client.app.state.auth_limiter
    for _ in range(10):
        lim.hits.pop(("ip", "testclient"), None)          # different "IPs": only the per-email counter grows
        assert client.post("/api/auth/login", json={"email": email, "password": "x"}).status_code == 401
    lim.hits.pop(("ip", "testclient"), None)
    assert client.post("/api/auth/login", json={"email": email, "password": "x"}).status_code == 429
