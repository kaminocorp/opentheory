import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.router import api_router
from app.core.auth import prewarm_jwks
from app.core.config import settings
from app.db.session import engine
from app.models.append_only import register_append_only_guards

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Best-effort startup warm-ups so the first real request doesn't pay one-time costs.

    With the backend co-located with the database (same region), a request's latency is dominated
    by two *one-time* costs: establishing the first DB connection, and fetching the Supabase JWKS
    key set. Doing both at boot — before the machine takes traffic — keeps the first user-facing
    request fast:

      * open a pooled DB connection and ``SELECT 1`` so asyncpg has a live connection ready
        (otherwise request #1 pays the connect + TLS + auth handshake);
      * fetch + cache the JWKS set so the first authenticated request is an in-memory cache hit
        rather than a blocking network round-trip on the event loop.

    Both are best-effort: a transient failure at boot must never stop the app from starting
    (``/health`` is DB-free and has to stay up), and the request path still falls back to a lazy
    fetch if a warm-up didn't populate its cache.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # best-effort: a cold/unreachable DB must not block startup
        logger.warning("DB pool warm-up failed at startup: %s", exc)
    # prewarm_jwks does synchronous (urllib) network I/O — run it off the event loop.
    await asyncio.to_thread(prewarm_jwks)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    # Append-only ORM guards are registered on import of app.models, but we call the
    # idempotent registrar explicitly here so the ledger invariant never depends on
    # import order or an incidental side effect.
    register_append_only_guards()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    if settings.backend_cors_origins:
        # str(AnyHttpUrl(...)) normalizes with a trailing slash ("http://localhost:3000/"),
        # but browsers send the Origin header without one ("http://localhost:3000") and
        # Starlette's CORS matches origins exactly — so strip the slash or every preflight fails.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[str(origin).rstrip("/") for origin in settings.backend_cors_origins],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
