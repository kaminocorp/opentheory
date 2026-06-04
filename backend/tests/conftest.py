import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.db.session import get_db
from app.main import create_app

# DB-backed tests run only when a Postgres URL is configured. Until a database is
# chosen (Supabase vs. self-hosted), these tests skip cleanly so the suite stays green.
# Prefer TEST_DATABASE_URL; fall back to DATABASE_URL.
TEST_DB_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """An httpx client bound to the app with a real (test) database session.

    Creates all tables before the test and drops them after, so each test runs against
    a clean schema. Skips if no database is configured or reachable.
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

    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with session_maker() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
