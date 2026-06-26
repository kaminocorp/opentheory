import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app

# The suite exercises the 0.3.x X-Dev-Actor-Id attribution path; enable it process-wide so
# writes resolve without an IdP (matches the plan's "auth_dev_header_enabled True in test").
# Auth-specific tests flip individual auth settings via monkeypatch (auto-restored).
settings.auth_dev_header_enabled = True

# DB-backed tests run only when a Postgres URL is configured; otherwise they skip cleanly so the
# suite stays green. Prefer an explicit TEST_DATABASE_URL (a deliberate opt-in, trusted for any
# host); fall back to DATABASE_URL only for a *local* host.
#
# SAFETY: the fixtures run `DROP SCHEMA public CASCADE` on every test, so pointing them at a real
# database destroys it. Because the live DB's env var is literally named DATABASE_URL, honoring
# that fallback unconditionally means a stray `export DATABASE_URL=<prod>` before `pytest` would
# wipe production. So the implicit fallback is accepted only when it targets localhost; to run the
# destructive suite against any non-local database, set TEST_DATABASE_URL explicitly.
#
# An empty/missing host (socket-form URLs parse to host=None) is NOT proof of localhost, so it is
# deliberately excluded — such a URL fails safe (skips). The host is lowercased before the check so
# an uppercase `LOCALHOST` is still recognized as local.
_LOCAL_DB_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _resolve_test_db_url() -> str | None:
    explicit = os.getenv("TEST_DATABASE_URL")
    if explicit:
        return explicit
    fallback = os.getenv("DATABASE_URL")
    if not fallback:
        return None
    try:
        host = (make_url(fallback).host or "").lower()
    except Exception:
        return None
    return fallback if host in _LOCAL_DB_HOSTS else None


TEST_DB_URL = _resolve_test_db_url()


async def _reset_schema(conn) -> None:  # type: ignore[no-untyped-def]
    """Drop and recreate the ``public`` schema — a clean slate that ignores FK cycles."""
    await conn.execute(text("DROP SCHEMA public CASCADE"))
    await conn.execute(text("CREATE SCHEMA public"))


class _UnusableSession:
    """A DB-session stand-in whose every use raises — for DB-free auth-gate tests.

    Those tests assert a request is rejected (401/404) *before* the handler touches the
    database. Overriding ``get_db`` with this makes that hermetic: if a guard regresses and the
    handler reaches the DB, the test fails loudly here instead of silently connecting to
    whatever ``DATABASE_URL`` points at — which, in this live-verify setup, is production.
    """

    def __getattr__(self, name: str) -> object:
        raise AssertionError(
            f"DB-free gate test reached the database (session.{name}); the request should "
            "have been rejected before any DB access."
        )


@pytest.fixture
def dbfree_client() -> TestClient:
    """A sync ``TestClient`` whose DB dependency raises on use (see ``_UnusableSession``).

    For route-level auth-gate tests that must reject before any DB access; they never connect
    to a real database, so they run safely in the default suite regardless of ``DATABASE_URL``.
    """
    app = create_app()

    async def _unusable_db() -> AsyncIterator[_UnusableSession]:
        yield _UnusableSession()

    app.dependency_overrides[get_db] = _unusable_db
    return TestClient(app)


@pytest_asyncio.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    """A per-test engine with a freshly created (and torn-down) schema.

    Skips if no database is configured or reachable. The ``client`` and
    ``session_factory`` fixtures share this one engine so HTTP writes and direct DB
    assertions see the same data.
    """
    if not TEST_DB_URL:
        pytest.skip(
            "No usable test database. Set TEST_DATABASE_URL (a non-local DATABASE_URL is "
            "ignored here — the fixtures DROP SCHEMA, so they must never touch the live DB)."
        )

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    try:
        async with engine.connect():
            pass
    except Exception:
        await engine.dispose()
        pytest.skip("Configured database is not reachable; skipping DB-backed test")

    # Reset to a pristine schema before creating, so a previous aborted run can't leave
    # tables/enums behind that would collide. ``branches`` and ``checkpoints`` form a
    # foreign-key cycle (branches.forked_from_checkpoint_id <-> checkpoints.branch_id), which
    # ``Base.metadata.drop_all`` cannot topologically sort — so we reset the whole ``public``
    # schema instead of dropping table-by-table. ``create_all`` handles the cycle natively
    # (it emits the cyclic FK as a post-create ALTER).
    async with engine.begin() as conn:
        await _reset_schema(conn)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await _reset_schema(conn)
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(db_engine: AsyncEngine) -> async_sessionmaker:
    """An async session factory bound to the test engine for direct DB assertions."""
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def client(
    db_engine: AsyncEngine, session_factory: async_sessionmaker
) -> AsyncIterator[AsyncClient]:
    """An httpx client bound to the app, sharing the test engine's schema/data."""

    async def override_get_db() -> AsyncIterator:
        async with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
