"""In-memory sliding-window rate limits (spec 2.10, DEC-003 OQ-26).

Counters live in each API worker's memory, so with 2 uvicorn workers the effective limit is up to 2x the
configured one; that is the accepted MVP trade-off. The event loop is single-threaded, so no lock is needed.
"""

from __future__ import annotations

import math
import time
from collections import deque

from fastapi import Request

from .errors import ApiError

MAX_KEYS = 50_000


class SlidingWindow:
    def __init__(self, limit: int, window_s: int):
        self.limit, self.window = limit, window_s
        self.hits: dict[tuple, deque] = {}

    def hit(self, key: tuple) -> None:
        """Record one hit for key, or raise 429 rate_limited with Retry-After."""
        now = time.monotonic()
        q = self.hits.setdefault(key, deque())
        while q and q[0] <= now - self.window:
            q.popleft()
        if len(q) >= self.limit:
            retry = max(1, math.ceil(q[0] + self.window - now))
            raise ApiError(429, "rate_limited", f"Too many requests, retry in {retry} s.", {"Retry-After": str(retry)})
        q.append(now)
        if len(self.hits) > MAX_KEYS:
            self._prune(now)

    def _prune(self, now: float) -> None:
        for k in [k for k, q in self.hits.items() if not q or q[-1] <= now - self.window]:
            del self.hits[k]

    def reset(self) -> None:
        self.hits.clear()


def client_ip(request: Request) -> str:
    """Caddy is the only way in (spec 2.2) and sets X-Forwarded-For; its last entry is the peer Caddy saw."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"
