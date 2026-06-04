import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.db.session import get_db
from app.main import create_app

# DB-backed tests run only when a Postgres URL is configured. Until a database is
# chosen (Supabase vs. self-hosted), these tests skip cleanly so the suite stays green.
# Prefer TEST_DATABASE_URL; fall back to DATABASE_URL.
TEST_DB_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")


@pytest_asyncio.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    """A per-test engine with a freshly created (and torn-down) schema.

    Skips if no database is configured or reachable. The ``client`` and
    ``session_factory`` fixtures share this one engine so HTTP writes and direct DB
    assertions see the same data.
    """
    if not TEST_DB_URL:
        pytest.skip("No TEST_DATABASE_URL/DATABASE_URL set; skipping DB-backed test")

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    try:
        async with engine.connect():
            pass
    except Exception:
        await engine.dispose()
        pytest.skip("Configured database is not reachable; skipping DB-backed test")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
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
