"""Cross-site request guard (CSRF defence in depth, SECURITY.md).

The session cookie is SameSite=Lax, so browsers do not send it on cross-site POSTs, and every state-changing route
takes a JSON body or a custom header (Idempotency-Key), which a cross-site form cannot send without a CORS
preflight that the API never answers. This middleware adds a third layer for unsafe methods:
- Sec-Fetch-Site: cross-site  -> 403 cross_site_request (browsers set it; same-origin/same-site/none pass);
- an Origin header whose host differs from the request's Host -> 403 cross_site_request.
Requests without either header (curl, the test client, the concurrency harness) are not browsers and pass.
Pure ASGI, like timing.py, so it adds no per-request task.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

UNSAFE = {b"POST", b"PUT", b"PATCH", b"DELETE"}
BODY = json.dumps({"error": {"code": "cross_site_request",
                             "message": "Cross-site requests are not allowed."}}).encode()


class CrossSiteGuard:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"].encode() in UNSAFE:
            h = {k.lower(): v for k, v in scope["headers"]}
            site = h.get(b"sec-fetch-site", b"").decode("latin-1").lower()
            origin = h.get(b"origin", b"").decode("latin-1")
            hosts = {h.get(b"host", b"").decode("latin-1").lower(),
                     h.get(b"x-forwarded-host", b"").decode("latin-1").lower()} - {""}
            bad = site == "cross-site"
            if origin and origin != "null" and not bad:
                bad = urlsplit(origin).netloc.lower() not in hosts
            elif origin == "null":
                bad = True
            if bad:
                await send({"type": "http.response.start", "status": 403,
                            "headers": [(b"content-type", b"application/json"),
                                        (b"content-length", str(len(BODY)).encode())]})
                await send({"type": "http.response.body", "body": BODY})
                return
        await self.app(scope, receive, send)
