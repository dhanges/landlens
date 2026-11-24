"""Security controls in the API (SECURITY.md): cross-site request guard, JSON-only bodies, no stack traces,
headers that do not leak the server, parameterized screener input."""

from __future__ import annotations

import json


def test_cross_site_posts_are_rejected(client, make_user):
    body = {"email": "nobody@example.com", "password": "whatever-password"}
    r = client.post("/api/auth/login", json=body, headers={"origin": "https://evil.example"})
    assert r.status_code == 403 and r.json() == {"error": {"code": "cross_site_request",
                                                           "message": "Cross-site requests are not allowed."}}
    assert client.post("/api/auth/login", json=body, headers={"sec-fetch-site": "cross-site"}).status_code == 403
    assert client.post("/api/auth/login", json=body, headers={"origin": "null"}).status_code == 403
    # same origin (and same-site, e.g. the dev proxy via X-Forwarded-Host) pass the guard
    assert client.post("/api/auth/login", json=body, headers={"origin": "https://testserver"}).status_code == 401
    assert client.post("/api/auth/login", json=body, headers={"origin": "http://localhost:3001",
                                                              "x-forwarded-host": "localhost:3001",
                                                              "sec-fetch-site": "same-site"}).status_code == 401
    # GET is never blocked (no state change)
    assert client.get("/api/health", headers={"origin": "https://evil.example"}).status_code == 200
    h, _ = make_user()
    r = client.post("/api/reports/1/unlock", headers={**h, "Idempotency-Key": "00000000-0000-4000-8000-000000000001",
                                                      "origin": "https://evil.example"})
    assert r.status_code == 403                                      # a forged unlock never reaches the handler


def test_json_bodies_only(client):
    # a cross-site HTML form can only send text/plain or form-encoded bodies; FastAPI must not parse them as JSON
    raw = json.dumps({"email": "nobody@example.com", "password": "whatever-password"})
    r = client.post("/api/auth/login", content=raw, headers={"content-type": "text/plain"})
    assert r.status_code == 422
    r = client.post("/api/auth/login", content="email=a%40b.c&password=x", headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 422


def test_errors_do_not_leak_internals(client):
    r = client.get("/api/parcels/abc/summary")
    assert r.status_code == 422 and "Traceback" not in r.text
    r = client.post("/api/screener", json={"filters": {"zone_code": ["R') OR 1=1 --"]}})
    assert r.status_code == 200 and r.json()["items"] == []           # bound as a value, matches nothing
    r = client.get("/api/search", params={"q": "'; DROP TABLE parcel; --"})
    assert r.status_code == 200 and r.json() == {"villages": [], "parcels": []}


def test_docs_can_be_disabled(monkeypatch):
    monkeypatch.setenv("API_DOCS", "false")
    from landlens.main import create_app
    paths = {getattr(r, "path", None) for r in create_app().routes}
    assert "/api/docs" not in paths and "/api/openapi.json" not in paths
