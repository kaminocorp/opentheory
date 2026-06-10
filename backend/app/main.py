from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.models.append_only import register_append_only_guards


def create_app() -> FastAPI:
    # Append-only ORM guards are registered on import of app.models, but we call the
    # idempotent registrar explicitly here so the ledger invariant never depends on
    # import order or an incidental side effect.
    register_append_only_guards()

    app = FastAPI(title=settings.app_name)

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
