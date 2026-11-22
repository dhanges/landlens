"""The shared error shape (spec 2.9): {"error": {"code": "...", "message": "..."}}, for every failure path.

ApiError is raised by routers; the handlers below map framework errors (404/405, request validation), pool
exhaustion (503 + Retry-After, spec 2.14), database outages and unexpected exceptions onto the same shape.
"""

from __future__ import annotations

import logging

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg_pool import PoolTimeout
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("landlens.errors")

STATUS_CODES = {400: "bad_request", 401: "auth_required", 403: "forbidden", 404: "not_found",
                405: "method_not_allowed", 409: "conflict", 413: "payload_too_large", 415: "unsupported_media_type",
                422: "validation_error", 429: "rate_limited", 500: "internal_error", 503: "unavailable"}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, headers: dict | None = None, details=None):
        super().__init__(message)
        self.status, self.code, self.message, self.headers, self.details = status, code, message, headers, details


def error_response(status: int, code: str, message: str, headers: dict | None = None, details=None) -> JSONResponse:
    body = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(body, status_code=status, headers=headers)


def _validation_details(exc: RequestValidationError) -> list[dict]:
    out = []
    for e in exc.errors():
        out.append({"loc": [str(x) for x in e.get("loc", ())], "msg": e.get("msg", ""), "type": e.get("type", "")})
    return out


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return error_response(exc.status, exc.code, exc.message, exc.headers, exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = STATUS_CODES.get(exc.status_code, "error")
        msg = exc.detail if isinstance(exc.detail, str) else code
        return error_response(exc.status_code, code, msg, getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        details = _validation_details(exc)
        first = details[0] if details else {"loc": [], "msg": "invalid request"}
        where = ".".join(x for x in first["loc"] if x not in ("body", "query", "path", "header")) or "request"
        return error_response(422, "validation_error", f"{where}: {first['msg']}", details=details)

    @app.exception_handler(PoolTimeout)
    async def _pool(_: Request, exc: PoolTimeout):
        log.warning("connection pool exhausted: %s", exc)
        return error_response(503, "pool_exhausted", "The service is busy, retry shortly.", {"Retry-After": "1"})

    @app.exception_handler(psycopg.OperationalError)
    async def _db_down(_: Request, exc: psycopg.OperationalError):
        log.error("database unavailable: %s", exc)
        return error_response(503, "db_unavailable", "The database is unavailable, retry shortly.", {"Retry-After": "5"})

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception):
        log.exception("unhandled error", exc_info=exc)
        return error_response(500, "internal_error", "Unexpected server error.")
