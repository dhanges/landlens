"""pytest setup (spec 2.16): a fresh landlens_test database on the compose server, built with the real
migrations (schema phase -> 10-parcel fixture -> post-load phase, so the views are computed over the fixture),
then the app under test connecting as landlens_api with AS_OF_DATE pinned to 2026-11-25 (DEC-004, OQ-27).

Run with `make test` (the compose `test` service). Needs DATABASE_URL (owner) and LANDLENS_API_PASSWORD.
"""

from __future__ import annotations

import os
import uuid
from urllib.parse import quote, urlsplit, urlunsplit

import psycopg
import pytest

from . import fixture

TEST_DB = "landlens_test"


def _url(db: str, user: str | None = None, password: str | None = None) -> str:
    parts = urlsplit(os.environ["DATABASE_URL"])
    netloc = parts.netloc
    if user:
        host = netloc.rsplit("@", 1)[-1]
        netloc = f"{user}:{quote(password or '', safe='')}@{host}"
    return urlunsplit(parts._replace(netloc=netloc, path=f"/{db}"))


@pytest.fixture(scope="session")
def database() -> str:
    os.environ["AS_OF_DATE"] = fixture.AS_OF
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        conn.execute(f"CREATE DATABASE {TEST_DB}")
    os.environ["LANDLENS_DB_NAME"] = TEST_DB          # landlens.db.connect() and migrate use it
    from landlens.cli import migrate
    assert migrate.run("schema") == 0
    with psycopg.connect(_url(TEST_DB)) as conn:
        for stmt in fixture.statements():
            conn.execute(stmt)
    assert migrate.run("post-load") == 0
    return TEST_DB


@pytest.fixture(scope="session")
def owner(database):
    """Owner connection to the test database (autocommit), for checks behind the API's back."""
    with psycopg.connect(_url(database), autocommit=True) as conn:
        conn.execute("SELECT set_config('landlens.as_of_date', %s, false)", (fixture.AS_OF,))
        yield conn


@pytest.fixture(scope="session")
def app(database):
    os.environ["API_DATABASE_URL"] = _url(database, "landlens_api", os.environ["LANDLENS_API_PASSWORD"])
    os.environ.setdefault("JWT_SECRET", "test-secret-" + uuid.uuid4().hex)
    os.environ["POOL_MAX"] = "4"
    from landlens.main import create_app
    return create_app()


@pytest.fixture(scope="session")
def client(app):
    from fastapi.testclient import TestClient
    # https base URL: the session cookie is Secure (COOKIE_SECURE default true), so httpx only sends it over https
    with TestClient(app, base_url="https://testserver") as c:
        yield c


@pytest.fixture(autouse=True)
def _isolate(request):
    """Fresh rate-limit counters and an empty cookie jar for every test (sessions travel as explicit headers)."""
    if "client" in request.fixturenames:
        c = request.getfixturevalue("client")
        c.app.state.auth_limiter.reset()
        c.cookies.clear()
    yield


def session_headers(response) -> dict:
    token = response.cookies.get("landlens_session")
    assert token, f"no session cookie in {response.headers}"
    return {"cookie": f"landlens_session={token}"}


@pytest.fixture
def make_user(client):
    """Sign up a fresh user: returns (headers carrying its session cookie, the signup response body)."""
    def _make(password: str = "correct horse battery"):
        r = client.post("/api/auth/signup", json={"email": f"u{uuid.uuid4().hex[:12]}@example.com",
                                                  "password": password})
        assert r.status_code == 201, r.text
        client.cookies.clear()
        return session_headers(r), r.json()
    return _make
