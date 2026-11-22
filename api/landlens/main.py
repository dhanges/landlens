"""LandLens FastAPI application (spec 2.9).

All endpoints are JSON under ``/api``; interactive docs at ``/api/docs``. The server connects as ``landlens_api``
(spec 2.10) through an async pool opened in the lifespan; errors share one shape (app/errors.py); every request
is logged with its duration (app/timing.py).
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from landlens import __version__
from landlens.app import config, errors
from landlens.app.db import make_pool
from landlens.app.ratelimit import SlidingWindow
from landlens.app.routers import health
from landlens.app.timing import TimingMiddleware

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = config.load()
    app.state.settings = s
    app.state.auth_limiter = SlidingWindow(s.rate_auth_per_min, s.rate_window_s)
    app.state.chat_limiter = SlidingWindow(s.rate_chat_per_min, s.rate_window_s)
    app.state.cache = {}
    app.state.pool = make_pool(s)
    await app.state.pool.open(wait=False)
    try:
        yield
    finally:
        await app.state.pool.close()


def create_app() -> FastAPI:
    app = FastAPI(title="LandLens API", version=__version__, docs_url="/api/docs",
                  openapi_url="/api/openapi.json", redoc_url=None, lifespan=lifespan)
    errors.install(app)
    app.add_middleware(TimingMiddleware)
    for r in (health,):
        app.include_router(r.router, prefix="/api")
    return app


app = create_app()
