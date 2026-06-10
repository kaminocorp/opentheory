from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# statement_cache_size=0 disables asyncpg's prepared-statement cache, which is required to
# run safely behind the Supabase transaction pooler (Supavisor in transaction mode reassigns
# server connections per transaction, so cached prepared statements can't be relied upon).
# At our query scale the lost caching is negligible; injection safety is unaffected (params
# are still bound). Harmless on a direct/session connection too.
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"statement_cache_size": 0},
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
