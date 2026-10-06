"""Migration 0023 — lock public PostgREST (0.58.1).

DB-free structural checks plus a Postgres upgrade/downgrade round-trip.
The Alembic-head check fails CI if any public table lacks RLS+FORCE.
"""

from __future__ import annotations

import importlib.util
import inspect
import os
import re
import subprocess
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app import models as _models  # noqa: F401 — populate Base.metadata
from app.db.base import Base
from app.db.rls_lock import (
    LOCK_PUBLIC_TABLES_SQL,
    REVOKE_POSTGREST_GRANTS_SQL,
    UNLOCK_PUBLIC_TABLES_SQL,
)
from tests.agent.public_rls import (
    assert_no_postgrest_table_grants,
    assert_public_tables_force_rls,
    ensure_postgrest_roles,
    postgrest_table_grants,
    public_rls_status,
)
from tests.conftest import TEST_DB_URL, _reset_schema

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
_MIGRATION_PATH = _VERSIONS / "0023_lock_public_api_rls.py"
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REVISION = "0023_lock_public_api_rls"
_DOWN = "0022_agent_actor_identity"


def _load_migration():
    spec = importlib.util.spec_from_file_location("_m0023", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_linkage() -> None:
    mod = _load_migration()
    assert mod.revision == _REVISION
    assert mod.down_revision == _DOWN


def test_it_is_the_only_head() -> None:
    down_revisions = {
        match.group(1)
        for path in _VERSIONS.glob("*.py")
        if (match := re.search(r'down_revision[^=]*=\s*"([^"]+)"', path.read_text()))
    }
    assert _REVISION not in down_revisions


def test_upgrade_is_a_pg_tables_loop_not_a_hard_coded_list() -> None:
    source = _MIGRATION_PATH.read_text()
    assert "LOCK_PUBLIC_TABLES_SQL" in source
    assert "REVOKE_POSTGREST_GRANTS_SQL" in source
    assert "UNLOCK_PUBLIC_TABLES_SQL" in source
    assert "pg_tables" in LOCK_PUBLIC_TABLES_SQL
    assert "ENABLE ROW LEVEL SECURITY" in LOCK_PUBLIC_TABLES_SQL
    assert "FORCE ROW LEVEL SECURITY" in LOCK_PUBLIC_TABLES_SQL
    assert "REVOKE ALL ON ALL TABLES" in REVOKE_POSTGREST_GRANTS_SQL
    assert "REVOKE ALL ON ALL SEQUENCES" in REVOKE_POSTGREST_GRANTS_SQL
    assert "ALTER DEFAULT PRIVILEGES" in REVOKE_POSTGREST_GRANTS_SQL
    assert "anon" in REVOKE_POSTGREST_GRANTS_SQL
    assert "authenticated" in REVOKE_POSTGREST_GRANTS_SQL
    assert "GRANT " not in UNLOCK_PUBLIC_TABLES_SQL
    assert "CREATE POLICY" not in source
    assert "CREATE POLICY" not in LOCK_PUBLIC_TABLES_SQL


def test_indexes_are_transactional() -> None:
    mod = _load_migration()
    body = inspect.getsource(mod.upgrade) + inspect.getsource(mod.downgrade)
    assert "CONCURRENTLY" not in body
    assert "autocommit_block" not in body
    assert "postgresql_concurrently" not in body


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "DATABASE_URL": TEST_DB_URL or "",
        "MIGRATION_DATABASE_URL": TEST_DB_URL or "",
    }
    return subprocess.run(
        ["uv", "run", "alembic", *args],
        cwd=_BACKEND_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


async def test_upgrade_head_locks_every_public_table(db_engine: AsyncEngine) -> None:
    """CI hook: Alembic head must ENABLE+FORCE RLS on every public base table."""
    async with db_engine.begin() as conn:
        await _reset_schema(conn)
    result = _alembic("upgrade", "head")
    assert result.returncode == 0, result.stdout + result.stderr
    await assert_public_tables_force_rls(db_engine)
    await assert_no_postgrest_table_grants(db_engine)
    locked = {
        name
        for name, enabled, forced in await public_rls_status(db_engine)
        if enabled and forced
    }
    meta = {
        table.name
        for table in Base.metadata.tables.values()
        if table.schema in (None, "public")
    }
    missing = sorted(meta - locked)
    assert not missing, f"SQLAlchemy public tables missing RLS+FORCE after head: {missing}"


async def test_downgrade_round_trip_does_not_regrant(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        await _reset_schema(conn)
    up_to_prev = _alembic("upgrade", _DOWN)
    assert up_to_prev.returncode == 0, up_to_prev.stdout + up_to_prev.stderr

    await ensure_postgrest_roles(db_engine)
    async with db_engine.begin() as conn:
        await conn.execute(
            text("GRANT SELECT ON ALL TABLES IN SCHEMA public TO anon, authenticated")
        )
    assert await postgrest_table_grants(db_engine)

    before = await public_rls_status(db_engine)
    assert before
    assert all(not enabled and not forced for _name, enabled, forced in before)

    upgraded = _alembic("upgrade", _REVISION)
    assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr
    await assert_public_tables_force_rls(db_engine)
    await assert_no_postgrest_table_grants(db_engine)

    again = _alembic("upgrade", _REVISION)
    assert again.returncode == 0, again.stdout + again.stderr
    await assert_public_tables_force_rls(db_engine)
    await assert_no_postgrest_table_grants(db_engine)

    downgraded = _alembic("downgrade", _DOWN)
    assert downgraded.returncode == 0, downgraded.stdout + downgraded.stderr
    after = await public_rls_status(db_engine)
    assert after
    assert all(not enabled and not forced for _name, enabled, forced in after)
    # Downgrade must not reintroduce PostgREST grants.
    await assert_no_postgrest_table_grants(db_engine)
