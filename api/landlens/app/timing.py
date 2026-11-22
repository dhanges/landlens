"""Request-timing log: one line per request with method, path, status and duration (pure ASGI middleware, so it
also sees responses produced by the error handlers)."""

from __future__ import annotations

import logging
import time

log = logging.getLogger("landlens.access")


class TimingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        t0 = time.perf_counter()
        status = {"code": 500}

        async def _send(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                ms = (time.perf_counter() - t0) * 1000
                message.setdefault("headers", []).append((b"server-timing", f"app;dur={ms:.1f}".encode()))
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            ms = (time.perf_counter() - t0) * 1000
            log.info("%s %s %d %.1fms", scope["method"], scope["path"], status["code"], ms)
