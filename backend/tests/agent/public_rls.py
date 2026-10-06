"""Assertions for the public PostgREST lock (0.58.1).

Used by the 0023 round-trip and by the Alembic-head CI check so a later
revision that creates a public table without ENABLE+FORCE fails CI.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.rls_lock import POSTGREST_TABLE_GRANTS_SQL, PUBLIC_RLS_STATUS_SQL

ENSURE_POSTGREST_ROLES_SQL = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated NOLOGIN;
    END IF;
END
$$;
"""


async def public_rls_status(engine: AsyncEngine) -> list[tuple[str, bool, bool]]:
    async with engine.connect() as conn:
        rows = (await conn.execute(text(PUBLIC_RLS_STATUS_SQL))).fetchall()
    return [(str(name), bool(enabled), bool(forced)) for name, enabled, forced in rows]


async def postgrest_table_grants(
    engine: AsyncEngine,
) -> list[tuple[str, str, str]]:
    async with engine.connect() as conn:
        rows = (await conn.execute(text(POSTGREST_TABLE_GRANTS_SQL))).fetchall()
    return [(str(grantee), str(table), str(priv)) for grantee, table, priv in rows]


async def assert_public_tables_force_rls(engine: AsyncEngine) -> None:
    rows = await public_rls_status(engine)
    assert rows, "expected public base tables after upgrade"
    missing = [name for name, enabled, forced in rows if not enabled or not forced]
    assert not missing, f"public tables missing RLS+FORCE: {missing}"


async def assert_no_postgrest_table_grants(engine: AsyncEngine) -> None:
    grants = await postgrest_table_grants(engine)
    assert grants == [], f"anon/authenticated still have table grants: {grants}"


async def ensure_postgrest_roles(engine: AsyncEngine) -> None:
    """Test-only. Live already has these roles; CI Postgres may not."""
    async with engine.begin() as conn:
        await conn.execute(text(ENSURE_POSTGREST_ROLES_SQL))
