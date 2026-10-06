"""Migration 0024 — agent definition catalog (0.59.0).

DB-free structural checks plus a Postgres upgrade/downgrade round-trip.
Skips the DB-gated tests without ``TEST_DATABASE_URL``.
Revises ``0023_lock_public_api_rls``; ENABLE+FORCE on the new table.
"""

from __future__ import annotations

import importlib.util
import inspect
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.models.actor import Actor
from app.models.agent_definition import AgentDefinition
from app.models.append_only import _APPEND_ONLY_MODELS
from tests.agent.public_rls import assert_public_tables_force_rls
from tests.conftest import TEST_DB_URL, _reset_schema

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
_MIGRATION_PATH = _VERSIONS / "0024_agent_definitions.py"
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REVISION = "0024_agent_definitions"
_DOWN = "0023_lock_public_api_rls"


def _load_migration():
    spec = importlib.util.spec_from_file_location("_m0024", _MIGRATION_PATH)
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


def test_the_tables_the_models_declare_are_the_tables_the_migration_adds() -> None:
    source = _MIGRATION_PATH.read_text()
    assert AgentDefinition.__table__.name == "agent_definitions"
    for column in (
        "account_id",
        "family_id",
        "version",
        "display_name",
        "config_fingerprint",
        "config",
    ):
        assert column in AgentDefinition.__table__.columns
        assert column in source
    assert "agent_definition_id" in Actor.__table__.columns
    assert "agent_definition_id" in source
    assert "uq_agent_definitions_family_version" in source
    assert "ix_agent_definitions_account_id" in source
    assert "ix_agent_definitions_family_id" in source
    assert "ix_actors_agent_definition_id" in source
    assert "op.add_column" in source
    assert '"actors"' in source
    assert "LOCK_PUBLIC_TABLES_SQL" in source


def test_indexes_are_transactional() -> None:
    mod = _load_migration()
    body = inspect.getsource(mod.upgrade) + inspect.getsource(mod.downgrade)
    assert "CONCURRENTLY" not in body
    assert "autocommit_block" not in body
    assert "postgresql_concurrently" not in body
    assert "if_not_exists" not in body
    assert "if_exists" not in body
    assert "op.create_index" in body
    assert "op.drop_index" in body


def test_catalog_is_not_append_only() -> None:
    names = {model.__name__ for model in _APPEND_ONLY_MODELS}
    assert "AgentDefinition" not in names
    assert "Actor" not in names


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


async def _indexes(engine: AsyncEngine, table: str) -> set[str]:
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE tablename = :t"),
                {"t": table},
            )
        ).fetchall()
    return {row[0] for row in rows}


async def _columns(engine: AsyncEngine, table: str) -> set[str]:
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = :t"
                ),
                {"t": table},
            )
        ).fetchall()
    return {row[0] for row in rows}


async def _tables(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
        ).fetchall()
    return {row[0] for row in rows}


async def test_upgrade_head_adds_catalog_and_pointer(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        await _reset_schema(conn)
    result = _alembic("upgrade", "head")
    assert result.returncode == 0, result.stdout + result.stderr
    tables = await _tables(db_engine)
    assert "agent_definitions" in tables
    actor_cols = await _columns(db_engine, "actors")
    assert "agent_definition_id" in actor_cols
    indexes = await _indexes(db_engine, "agent_definitions")
    assert "uq_agent_definitions_family_version" in indexes
    assert "ix_agent_definitions_account_id" in indexes
    assert "ix_agent_definitions_family_id" in indexes
    actor_indexes = await _indexes(db_engine, "actors")
    assert "ix_actors_agent_definition_id" in actor_indexes
    await assert_public_tables_force_rls(db_engine)


async def test_downgrade_round_trip(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        await _reset_schema(conn)
    up_to_prev = _alembic("upgrade", _DOWN)
    assert up_to_prev.returncode == 0, up_to_prev.stdout + up_to_prev.stderr
    assert "agent_definitions" not in await _tables(db_engine)
    assert "agent_definition_id" not in await _columns(db_engine, "actors")

    owner_acct = uuid4()
    owner_actor = uuid4()
    now = datetime.now(UTC)
    async with db_engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO accounts (
                    id, display_name, username, roles, account_metadata,
                    created_at, updated_at
                ) VALUES (
                    :id, 'Owner', 'owner0024', '{}', '{}'::json, :now, :now
                )
                """
            ),
            {"id": owner_acct, "now": now},
        )
        await conn.execute(
            text(
                """
                INSERT INTO actors (
                    id, type, display_name, actor_metadata, account_id,
                    created_at, updated_at
                ) VALUES (
                    :id, 'HUMAN', 'Owner', '{}'::json, :acct, :now, :now
                )
                """
            ),
            {"id": owner_actor, "acct": owner_acct, "now": now},
        )

    upgraded = _alembic("upgrade", _REVISION)
    assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr
    assert "agent_definitions" in await _tables(db_engine)
    assert "agent_definition_id" in await _columns(db_engine, "actors")

    family_id = uuid4()
    definition_id = uuid4()
    async with db_engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO agent_definitions (
                    id, account_id, family_id, version, display_name,
                    config_fingerprint, config, created_at, updated_at
                ) VALUES (
                    :id, :acct, :family, 1, 'DeepSeek researcher',
                    'abc', '{}'::json, :now, :now
                )
                """
            ),
            {
                "id": definition_id,
                "acct": owner_acct,
                "family": family_id,
                "now": now,
            },
        )
        await conn.execute(
            text(
                """
                UPDATE actors SET agent_definition_id = :def
                WHERE id = :id
                """
            ),
            {"def": definition_id, "id": owner_actor},
        )

    async with db_engine.connect() as conn:
        pointed = (
            await conn.execute(
                text("SELECT agent_definition_id FROM actors WHERE id = :id"),
                {"id": owner_actor},
            )
        ).one()
        assert pointed[0] == definition_id

    downgraded = _alembic("downgrade", _DOWN)
    assert downgraded.returncode == 0, downgraded.stdout + downgraded.stderr
    assert "agent_definitions" not in await _tables(db_engine)
    assert "agent_definition_id" not in await _columns(db_engine, "actors")

    again = _alembic("upgrade", _REVISION)
    assert again.returncode == 0, again.stdout + again.stderr
    assert "agent_definitions" in await _tables(db_engine)
    assert "agent_definition_id" in await _columns(db_engine, "actors")
    async with db_engine.connect() as conn:
        count = (
            await conn.execute(text("SELECT COUNT(*) FROM agent_definitions"))
        ).scalar_one()
        assert count == 0
        pointed = (
            await conn.execute(
                text("SELECT agent_definition_id FROM actors WHERE id = :id"),
                {"id": owner_actor},
            )
        ).one()
        assert pointed[0] is None


async def test_family_version_unique_and_retarget_rejected(
    session_factory: async_sessionmaker,
) -> None:
    from app.models.account import Account
    from app.models.enums import ActorType

    async with session_factory() as session:
        account = Account(display_name="A", username=f"u-{uuid4().hex[:12]}")
        session.add(account)
        await session.flush()
        family_id = uuid4()
        first = AgentDefinition(
            account_id=account.id,
            family_id=family_id,
            version=1,
            display_name="Kind",
            config_fingerprint="one",
            config={"model_id": "a"},
        )
        session.add(first)
        await session.flush()
        session.add(
            AgentDefinition(
                account_id=account.id,
                family_id=family_id,
                version=1,
                display_name="Kind",
                config_fingerprint="two",
                config={"model_id": "b"},
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

    async with session_factory() as session:
        account = Account(display_name="B", username=f"u-{uuid4().hex[:12]}")
        definition = AgentDefinition(
            family_id=uuid4(),
            version=1,
            display_name="Kind",
            config_fingerprint="one",
            config={},
        )
        other = AgentDefinition(
            family_id=uuid4(),
            version=1,
            display_name="Other",
            config_fingerprint="two",
            config={},
        )
        actor = Actor(type=ActorType.AGENT, display_name="Named", actor_metadata={})
        session.add_all([account, definition, other, actor])
        await session.flush()
        actor.agent_definition_id = definition.id
        with pytest.raises(ValueError, match="deploy-time only"):
            await session.flush()
        await session.rollback()

    async with session_factory() as session:
        definition = AgentDefinition(
            family_id=uuid4(),
            version=1,
            display_name="Kind",
            config_fingerprint="one",
            config={},
        )
        actor = Actor(
            type=ActorType.AGENT,
            display_name="Named",
            actor_metadata={},
            agent_definition_id=None,
        )
        session.add_all([definition, actor])
        await session.flush()
        # Insert-time pointer is the allowed path; recreate with the FK set.
        pointed = Actor(
            type=ActorType.AGENT,
            display_name="Pointed",
            actor_metadata={},
            agent_definition_id=definition.id,
        )
        session.add(pointed)
        await session.flush()
        pointed.display_name = "Still pointed"
        await session.flush()
        pointed.agent_definition_id = None
        with pytest.raises(ValueError, match="deploy-time only"):
            await session.flush()
