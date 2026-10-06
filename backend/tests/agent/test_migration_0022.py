"""Migration 0022 — agent actor identity schema (0.53.0).

DB-free structural checks plus a Postgres upgrade/downgrade round-trip with
the Research-crew and ComputeDebit backfills. Skips the DB-gated tests
without ``TEST_DATABASE_URL``.
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
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.models.actor import Actor
from app.models.agent_session_token import AgentSessionToken
from app.models.checkpoint import Checkpoint
from app.models.compute_debit import ComputeDebit
from app.models.enums import (
    ActorType,
    ComputeDebitKind,
    ProjectAgentRole,
    ProjectAgentStatus,
)
from app.models.project_agent_member import ProjectAgentMember
from tests.conftest import TEST_DB_URL, _reset_schema

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
_MIGRATION_PATH = _VERSIONS / "0022_agent_actor_identity.py"
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REVISION = "0022_agent_actor_identity"
_DOWN = "0021_concurrent_campaign_cycles"


def _load_migration():
    spec = importlib.util.spec_from_file_location("_m0022", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_linkage() -> None:
    mod = _load_migration()
    assert mod.revision == _REVISION
    assert mod.down_revision == _DOWN


def test_it_is_revised_by_0023() -> None:
    """0023 (public API RLS lock) revises 0022; catalog is 0024."""
    down_revisions = {
        match.group(1)
        for path in _VERSIONS.glob("*.py")
        if (match := re.search(r'down_revision[^=]*=\s*"([^"]+)"', path.read_text()))
    }
    assert _REVISION in down_revisions


def test_enum_labels_match_the_model() -> None:
    mod = _load_migration()
    assert set(mod._ROLE_LABELS) == {member.name for member in ProjectAgentRole}
    assert set(mod._STATUS_LABELS) == {member.name for member in ProjectAgentStatus}
    assert ProjectAgentRole.RESEARCHER.name == "RESEARCHER"
    assert "VALIDATOR" not in mod._ROLE_LABELS


def test_the_tables_the_models_declare_are_the_tables_the_migration_adds() -> None:
    source = _MIGRATION_PATH.read_text()
    assert ProjectAgentMember.__table__.name == "project_agent_members"
    assert AgentSessionToken.__table__.name == "agent_session_tokens"
    for column in (
        "project_id",
        "actor_id",
        "deployed_by_account_id",
        "responsible_account_id",
        "role",
        "status",
        "token_budget_cap",
        "usd_budget_cap",
    ):
        assert column in ProjectAgentMember.__table__.columns
        assert column in source
    for column in (
        "token_hash",
        "expires_at",
        "revoked_at",
        "minted_by_account_id",
        "minted_by_actor_id",
        "last_used_at",
    ):
        assert column in AgentSessionToken.__table__.columns
        assert column in source
    assert "sponsored_by_actor_id" in Checkpoint.__table__.columns
    assert "sponsored_by_actor_id" in source
    assert "actor_id" in ComputeDebit.__table__.columns
    assert "ix_compute_debits_actor_id" in source
    assert "uq_project_agent_member" in source
    assert "uq_agent_session_tokens_hash" in source
    assert "uq_actors_one_research_crew_per_project" in source
    assert "uq_actors_one_agent_per_project" in source


def test_owner_override_omits_agent_definition_id() -> None:
    """0022 itself does not add ``actors.agent_definition_id`` (catalog is 0024)."""
    source = _MIGRATION_PATH.read_text()
    assert "ADD COLUMN" not in source or "agent_definition_id" not in source
    assert "actors.agent_definition_id" in source  # named as deferred
    assert "op.add_column(\n        \"actors\"" not in source


def test_indexes_are_transactional() -> None:
    """0022 upgrade/downgrade is one transaction: no CONCURRENTLY / autocommit hedges."""
    mod = _load_migration()
    body = inspect.getsource(mod.upgrade) + inspect.getsource(mod.downgrade)
    assert "CONCURRENTLY" not in body
    assert "autocommit_block" not in body
    assert "postgresql_concurrently" not in body
    assert "if_not_exists" not in body
    assert "if_exists" not in body
    assert "op.create_index" in body
    assert "op.drop_index" in body
    assert not hasattr(mod, "_create_index_concurrently")
    assert not hasattr(mod, "_drop_index_concurrently")


def test_migration_is_not_append_only_on_the_new_tables() -> None:
    from app.models.append_only import _APPEND_ONLY_MODELS

    names = {model.__name__ for model in _APPEND_ONLY_MODELS}
    assert "ProjectAgentMember" not in names
    assert "AgentSessionToken" not in names
    assert "Checkpoint" in names
    assert "ComputeDebit" in names


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "DATABASE_URL": TEST_DB_URL or "",
        "MIGRATION_DATABASE_URL": TEST_DB_URL or "",
    }
    result = subprocess.run(
        ["uv", "run", "alembic", *args],
        cwd=_BACKEND_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    return result


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
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                )
            )
        ).fetchall()
    return {row[0] for row in rows}


@pytest.fixture
def alembic_db(db_engine: AsyncEngine) -> AsyncEngine:
    """Reuse the reachable-DB gate; caller resets to empty before invoking Alembic."""
    return db_engine


async def test_upgrade_head_on_empty_postgres(db_engine: AsyncEngine) -> None:
    """The deploy path: empty schema → ``alembic upgrade head``. Backfills no-op."""
    async with db_engine.begin() as conn:
        await _reset_schema(conn)
    result = _alembic("upgrade", _REVISION)
    assert result.returncode == 0, result.stdout + result.stderr
    tables = await _tables(db_engine)
    assert "project_agent_members" in tables
    assert "agent_session_tokens" in tables
    cols = await _columns(db_engine, "checkpoints")
    assert "sponsored_by_actor_id" in cols
    debit_cols = await _columns(db_engine, "compute_debits")
    assert "actor_id" in debit_cols
    actor_cols = await _columns(db_engine, "actors")
    assert "agent_definition_id" not in actor_cols
    indexes = await _indexes(db_engine, "actors")
    assert "uq_actors_one_research_crew_per_project" in indexes
    assert "uq_actors_one_agent_per_project" not in indexes


async def test_backfill_and_downgrade_round_trip(db_engine: AsyncEngine) -> None:
    async with db_engine.begin() as conn:
        await _reset_schema(conn)
    up_to_prev = _alembic("upgrade", _DOWN)
    assert up_to_prev.returncode == 0, up_to_prev.stdout + up_to_prev.stderr

    owner_acct = uuid4()
    owner_actor = uuid4()
    owned_project = uuid4()
    owned_crew = uuid4()
    orphan_project = uuid4()
    orphan_crew = uuid4()
    garbage_crew = uuid4()
    thread_id = uuid4()
    run_with_actor = uuid4()
    run_without_actor = uuid4()
    debit_from_run = uuid4()
    debit_from_null_run = uuid4()
    debit_harness_spend = uuid4()
    debit_harness_hold = uuid4()
    debit_other = uuid4()
    now = datetime.now(UTC)

    async with db_engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO accounts (
                    id, display_name, username, roles, account_metadata,
                    created_at, updated_at
                ) VALUES (
                    :id, 'Owner', 'owner0022', '{}', '{}'::json, :now, :now
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
        for project_id, slug, title in (
            (owned_project, "owned-0022", "Owned"),
            (orphan_project, "orphan-0022", "Orphan"),
        ):
            await conn.execute(
                text(
                    """
                    INSERT INTO projects (
                        id, title, slug, question, status, agent_models,
                        created_at, updated_at
                    ) VALUES (
                        :id, :title, :slug, 'q?', 'DRAFT', '{}'::json, :now, :now
                    )
                    """
                ),
                {"id": project_id, "title": title, "slug": slug, "now": now},
            )
        await conn.execute(
            text(
                """
                INSERT INTO project_members (
                    id, project_id, account_id, role, created_at, updated_at
                ) VALUES (
                    :id, :project, :acct, 'OWNER', :now, :now
                )
                """
            ),
            {"id": uuid4(), "project": owned_project, "acct": owner_acct, "now": now},
        )
        for actor_id, project_id in (
            (owned_crew, str(owned_project)),
            (orphan_crew, str(orphan_project)),
        ):
            await conn.execute(
                text(
                    """
                    INSERT INTO actors (
                        id, type, display_name, actor_metadata, account_id,
                        created_at, updated_at
                    ) VALUES (
                        :id, 'AGENT', 'Research crew',
                        json_build_object('project_id', CAST(:pid AS text))::json,
                        NULL, :now, :now
                    )
                    """
                ),
                {"id": actor_id, "pid": project_id, "now": now},
            )
        await conn.execute(
            text(
                """
                INSERT INTO actors (
                    id, type, display_name, actor_metadata, account_id,
                    created_at, updated_at
                ) VALUES (
                    :id, 'AGENT', 'Research crew',
                    '{"project_id": "not-a-uuid"}'::json,
                    NULL, :now, :now
                )
                """
            ),
            {"id": garbage_crew, "now": now},
        )
        await conn.execute(
            text(
                """
                INSERT INTO threads (
                    id, project_id, title, question, stage, status,
                    thread_metadata, created_at, updated_at
                ) VALUES (
                    :id, :project, 'T', 'q?', 'DECOMPOSE', 'OPEN',
                    '{}'::json, :now, :now
                )
                """
            ),
            {"id": thread_id, "project": owned_project, "now": now},
        )
        for run_id, agent_actor in (
            (run_with_actor, owned_crew),
            (run_without_actor, None),
        ):
            await conn.execute(
                text(
                    """
                    INSERT INTO agent_runs (
                        id, project_id, thread_id, agent_actor_id,
                        triggered_by_actor_id, role, status, plan, steps,
                        planned_count, ran_count, tokens_used, grounding_yield,
                        created_at, updated_at
                    ) VALUES (
                        :id, :project, :thread, :agent, :human, 'researcher',
                        'COMPLETED', '{}'::json, '[]'::json, 0, 0, 10,
                        '{}'::json, :now, :now
                    )
                    """
                ),
                {
                    "id": run_id,
                    "project": owned_project,
                    "thread": thread_id,
                    "agent": agent_actor,
                    "human": owner_actor,
                    "now": now,
                },
            )
        debit_rows = (
            (debit_from_run, run_with_actor, "dark-loop", 12, "1.000000"),
            (debit_from_null_run, run_without_actor, "failed-before-resolve", 8, "0.500000"),
            (debit_harness_spend, None, "harness_session_turn; spend", 20, "0.002000"),
            (debit_harness_hold, None, "harness_session_turn; daily_cap_hold hold_id=abc", 0, "0"),
            (debit_other, None, "something_else", 3, "0.100000"),
        )
        for debit_id, run_id, notes, tokens, amount in debit_rows:
            await conn.execute(
                text(
                    """
                    INSERT INTO compute_debits (
                        id, project_id, agent_run_id, tokens_used, amount,
                        currency, rate_per_1k, kind, notes, created_at, updated_at
                    ) VALUES (
                        :id, :project, :run, :tokens, :amount, 'USD', 1,
                        'PLANNING', :notes, :now, :now
                    )
                    """
                ),
                {
                    "id": debit_id,
                    "project": owned_project,
                    "run": run_id,
                    "tokens": tokens,
                    "amount": amount,
                    "notes": notes,
                    "now": now,
                },
            )

    upgraded = _alembic("upgrade", _REVISION)
    assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr

    async with db_engine.connect() as conn:
        crew = (
            await conn.execute(
                text("SELECT account_id FROM actors WHERE id = :id"),
                {"id": owned_crew},
            )
        ).one()
        assert crew[0] == owner_acct
        orphan = (
            await conn.execute(
                text("SELECT account_id FROM actors WHERE id = :id"),
                {"id": orphan_crew},
            )
        ).one()
        assert orphan[0] is None
        garbage = (
            await conn.execute(
                text("SELECT account_id FROM actors WHERE id = :id"),
                {"id": garbage_crew},
            )
        ).one()
        assert garbage[0] is None

        roster = (
            await conn.execute(
                text(
                    """
                    SELECT project_id, actor_id, role, status,
                           deployed_by_account_id, responsible_account_id,
                           token_budget_cap, usd_budget_cap
                    FROM project_agent_members
                    ORDER BY actor_id
                    """
                )
            )
        ).fetchall()
        assert len(roster) == 1
        row = roster[0]
        assert row[0] == owned_project
        assert row[1] == owned_crew
        assert row[2] == "RESEARCHER"
        assert row[3] == "ACTIVE"
        assert row[4] == owner_acct
        assert row[5] == owner_acct
        assert row[6] is None
        assert row[7] is None

        debit_actors = {
            r[0]: r[1]
            for r in (
                await conn.execute(
                    text("SELECT id, actor_id FROM compute_debits")
                )
            ).fetchall()
        }
        assert debit_actors[debit_from_run] == owned_crew
        assert debit_actors[debit_from_null_run] is None
        assert debit_actors[debit_harness_spend] is None
        assert debit_actors[debit_harness_hold] is None
        assert debit_actors[debit_other] is None

        # Amounts / notes / tokens were not rewritten.
        spend = (
            await conn.execute(
                text(
                    "SELECT amount, tokens_used, notes FROM compute_debits WHERE id = :id"
                ),
                {"id": debit_harness_spend},
            )
        ).one()
        assert str(spend[0]) == "0.002000"
        assert spend[1] == 20
        assert spend[2] == "harness_session_turn; spend"

    # Idempotent: a second pass of the backfill statements (via upgrade no-op)
    # plus a re-run of the SQL would not duplicate roster rows.
    again = _alembic("upgrade", _REVISION)
    assert again.returncode == 0, again.stdout + again.stderr
    async with db_engine.connect() as conn:
        count = (
            await conn.execute(text("SELECT COUNT(*) FROM project_agent_members"))
        ).scalar_one()
        assert count == 1

    downgraded = _alembic("downgrade", _DOWN)
    assert downgraded.returncode == 0, downgraded.stdout + downgraded.stderr

    tables = await _tables(db_engine)
    assert "project_agent_members" not in tables
    assert "agent_session_tokens" not in tables
    assert "sponsored_by_actor_id" not in await _columns(db_engine, "checkpoints")
    assert "actor_id" not in await _columns(db_engine, "compute_debits")
    indexes = await _indexes(db_engine, "actors")
    assert "uq_actors_one_agent_per_project" in indexes
    assert "uq_actors_one_research_crew_per_project" not in indexes
    async with db_engine.connect() as conn:
        restored = (
            await conn.execute(
                text("SELECT account_id FROM actors WHERE id = :id"),
                {"id": owned_crew},
            )
        ).one()
        assert restored[0] is None


async def test_downgrade_refuses_when_two_agents_share_a_project(
    db_engine: AsyncEngine,
) -> None:
    async with db_engine.begin() as conn:
        await _reset_schema(conn)
    assert _alembic("upgrade", _REVISION).returncode == 0

    project_id = uuid4()
    now = datetime.now(UTC)
    async with db_engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO projects (
                    id, title, slug, question, status, agent_models,
                    created_at, updated_at
                ) VALUES (
                    :id, 'Two agents', 'two-agents-0022', 'q?', 'DRAFT',
                    '{}'::json, :now, :now
                )
                """
            ),
            {"id": project_id, "now": now},
        )
        for name in ("Research crew", "DeepSeek researcher"):
            await conn.execute(
                text(
                    """
                    INSERT INTO actors (
                        id, type, display_name, actor_metadata, created_at, updated_at
                    ) VALUES (
                        :id, 'AGENT', :name,
                        json_build_object('project_id', CAST(:pid AS text))::json,
                        :now, :now
                    )
                    """
                ),
                {"id": uuid4(), "name": name, "pid": str(project_id), "now": now},
            )

    refused = _alembic("downgrade", _DOWN)
    assert refused.returncode != 0
    assert "more than one type=agent Actor" in (refused.stderr + refused.stdout)


async def test_roster_unique_pair_and_enums(
    session_factory: async_sessionmaker,
) -> None:
    from app.models.account import Account
    from app.models.project import Project

    async with session_factory() as session:
        account = Account(display_name="A", username=f"u-{uuid4().hex[:12]}")
        project = Project(title="P", slug=f"s-{uuid4().hex[:8]}", question="q?")
        actor = Actor(
            type=ActorType.AGENT,
            display_name="Named",
            actor_metadata={"project_id": "x"},
        )
        session.add_all([account, project, actor])
        await session.flush()
        first = ProjectAgentMember(
            project_id=project.id,
            actor_id=actor.id,
            deployed_by_account_id=account.id,
            responsible_account_id=account.id,
            role=ProjectAgentRole.RESEARCHER,
            status=ProjectAgentStatus.ACTIVE,
        )
        session.add(first)
        await session.flush()
        session.add(
            ProjectAgentMember(
                project_id=project.id,
                actor_id=actor.id,
                role=ProjectAgentRole.RESEARCHER,
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

    async with session_factory() as session:
        with pytest.raises(ValueError, match="validator"):
            ProjectAgentStatus("validator")
        with pytest.raises(ValueError, match="validator"):
            ProjectAgentRole("validator")


async def test_roster_row_is_mutable_checkpoint_is_not(
    session_factory: async_sessionmaker,
) -> None:
    from app.models import AppendOnlyError
    from app.models.account import Account
    from app.models.project import Project

    async with session_factory() as session:
        account = Account(display_name="A", username=f"u-{uuid4().hex[:12]}")
        project = Project(title="P", slug=f"s-{uuid4().hex[:8]}", question="q?")
        actor = Actor(type=ActorType.AGENT, display_name="Named", actor_metadata={})
        session.add_all([account, project, actor])
        await session.flush()
        roster = ProjectAgentMember(
            project_id=project.id,
            actor_id=actor.id,
            role=ProjectAgentRole.RESEARCHER,
        )
        session.add(roster)
        await session.flush()
        roster.status = ProjectAgentStatus.REVOKED
        await session.flush()
        assert roster.status is ProjectAgentStatus.REVOKED

        checkpoint = Checkpoint(
            project_id=project.id,
            author_id=actor.id,
            sponsored_by_actor_id=None,
            summary="s",
        )
        session.add(checkpoint)
        await session.flush()
        checkpoint.summary = "nope"
        with pytest.raises(AppendOnlyError):
            await session.flush()


async def test_create_checkpoint_and_debit_leave_new_columns_null(
    client,
    session_factory: async_sessionmaker,
) -> None:
    from app.services.compute import record_compute_debit
    from tests.principals import create_owned_project, make_dev_principal

    actor_id = await make_dev_principal(client, display_name="Author")
    project_id = await create_owned_project(client, actor_id, f"cp-{uuid4().hex[:8]}")
    resp = await client.post(
        f"/api/v1/projects/{project_id}/checkpoints",
        json={"summary": "identity schema still dark"},
        headers={"X-Dev-Actor-Id": actor_id},
    )
    assert resp.status_code == 201, resp.text
    checkpoint_id = resp.json()["id"]

    async with session_factory() as session:
        checkpoint = await session.get(Checkpoint, checkpoint_id)
        assert checkpoint is not None
        assert checkpoint.sponsored_by_actor_id is None
        debit = await record_compute_debit(
            session,
            project_id=checkpoint.project_id,
            tokens_used=10,
            model="test-model",
            kind=ComputeDebitKind.PLANNING,
            notes="harness_session_turn; identity-schema-dark",
        )
        await session.commit()
        assert debit is not None
        assert debit.actor_id is None
        assert debit.tokens_used == 10


async def test_invalid_roster_enum_rejected_by_postgres(
    session_factory: async_sessionmaker,
) -> None:
    from app.models.project import Project

    async with session_factory() as session:
        project = Project(title="P", slug=f"s-{uuid4().hex[:8]}", question="q?")
        actor = Actor(type=ActorType.AGENT, display_name="Named", actor_metadata={})
        session.add_all([project, actor])
        await session.flush()
        await session.execute(
            text(
                """
                INSERT INTO project_agent_members (
                    id, project_id, actor_id, role, status, created_at, updated_at
                ) VALUES (
                    :id, :project, :actor, 'RESEARCHER', 'ACTIVE', now(), now()
                )
                """
            ),
            {"id": uuid4(), "project": project.id, "actor": actor.id},
        )
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(DBAPIError, match="VALIDATOR"):
            await session.execute(
                text(
                    """
                    INSERT INTO project_agent_members (
                        id, project_id, actor_id, role, status, created_at, updated_at
                    ) VALUES (
                        :id, :project, :actor, 'VALIDATOR', 'ACTIVE', now(), now()
                    )
                    """
                ),
                {"id": uuid4(), "project": project.id, "actor": actor.id},
            )
            await session.flush()
