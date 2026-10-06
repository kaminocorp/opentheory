"""agent actor identity: roster + session tokens + attribution columns

Revision ID: 0022_agent_actor_identity
Revises: 0021_concurrent_campaign_cycles
Create Date: 2026-10-06

0.53.0 — schema slice of the approved agent-actor identity design
(``docs/plans/agent-actor-identity.md``; owner overrides: no
``actors.agent_definition_id`` in v1, keep ``Research crew`` display
name, ``ProjectAgentRole = RESEARCHER`` only). Additive. Schema-on,
behavior-off: no resolver, no mint, no ``ensure_is_member`` change.

- ``project_agent_role`` / ``project_agent_status`` enums
- ``project_agent_members`` (mutable roster; not append-only)
- ``agent_session_tokens`` (hash at rest; no mint/verify in this slice)
- ``checkpoints.sponsored_by_actor_id`` nullable FK ``actors`` SET NULL
- ``compute_debits.actor_id`` nullable FK ``actors`` SET NULL
- Research-crew ``account_id`` backfill + ACTIVE RESEARCHER roster row
- ``ComputeDebit.actor_id`` backfill from ``AgentRun.agent_actor_id`` only
  (``harness_session_turn`` rows stay null)
- Drop ``uq_actors_one_agent_per_project``; add
  ``uq_actors_one_research_crew_per_project``

``actors.agent_definition_id`` is **not** added — deferred with the
``agent_definitions`` catalog table (owner 2026-10-06).

The whole revision is **one transaction** (plain ``op.create_index`` /
``op.drop_index``). ``CREATE INDEX CONCURRENTLY`` + ``autocommit_block``
are deliberately not used: an autocommit mid-migration leaves a
half-applied schema that a re-run cannot recover (``create_table`` is
not idempotent), and a failed CONCURRENTLY unique build can leave an
``INVALID`` index that ``if_not_exists`` would then skip — dropping the
old one-agent-per-project guard with no valid replacement. Prod at
review (2026-10-06, live Supabase read-only) is tiny: checkpoints 0,
compute_debits 0, actors 2, agent actors 0, alembic at 0021 — the
SHARE lock is negligible. A future large-table migration should
revisit concurrency and must check ``pg_index.indisvalid`` before
treating an existing index as done. Backfills are set-based and
idempotent (``WHERE … IS NULL``, ``ON CONFLICT DO NOTHING``).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0022_agent_actor_identity"
down_revision: str | None = "0021_concurrent_campaign_cycles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLE_LABELS = ("RESEARCHER",)
_STATUS_LABELS = ("ACTIVE", "SUSPENDED", "REVOKED")

_UUID_RE = (
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Enums (uppercase StrEnum member labels), created before the tables.
    postgresql.ENUM(*_ROLE_LABELS, name="project_agent_role").create(bind, checkfirst=True)
    postgresql.ENUM(*_STATUS_LABELS, name="project_agent_status").create(bind, checkfirst=True)

    # 2. Roster. FKs inline + unnamed (Postgres names them <table>_<col>_fkey).
    op.create_table(
        "project_agent_members",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("actor_id", _uuid(), nullable=False),
        sa.Column("deployed_by_account_id", _uuid(), nullable=True),
        sa.Column("responsible_account_id", _uuid(), nullable=True),
        sa.Column(
            "role",
            postgresql.ENUM(*_ROLE_LABELS, name="project_agent_role", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(*_STATUS_LABELS, name="project_agent_status", create_type=False),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("token_budget_cap", sa.Integer(), nullable=True),
        sa.Column("usd_budget_cap", sa.Numeric(12, 6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["deployed_by_account_id"], ["accounts.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["responsible_account_id"], ["accounts.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("project_id", "actor_id", name="uq_project_agent_member"),
    )
    op.create_index("ix_project_agent_members_project_id", "project_agent_members", ["project_id"])
    op.create_index("ix_project_agent_members_actor_id", "project_agent_members", ["actor_id"])
    op.create_index(
        "ix_project_agent_members_project_status",
        "project_agent_members",
        ["project_id", "status"],
    )
    op.create_index(
        "ix_project_agent_members_responsible",
        "project_agent_members",
        ["project_id", "responsible_account_id"],
    )

    # 3. Session tokens. Empty table — regular indexes are fine.
    op.create_table(
        "agent_session_tokens",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("actor_id", _uuid(), nullable=False),
        sa.Column("minted_by_account_id", _uuid(), nullable=True),
        sa.Column("minted_by_actor_id", _uuid(), nullable=True),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["minted_by_account_id"], ["accounts.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["minted_by_actor_id"], ["actors.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("token_hash", name="uq_agent_session_tokens_hash"),
    )
    op.create_index(
        "ix_agent_session_tokens_project_id", "agent_session_tokens", ["project_id"]
    )
    op.create_index(
        "ix_agent_session_tokens_lookup",
        "agent_session_tokens",
        ["actor_id", "project_id", "revoked_at", "expires_at"],
    )

    # 4–5. Nullable column adds on append-only tables (PG 11+ metadata-only)
    #      plus regular indexes — same transaction as the rest of the revision.
    op.add_column(
        "checkpoints",
        sa.Column(
            "sponsored_by_actor_id",
            _uuid(),
            sa.ForeignKey("actors.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_checkpoints_sponsored_by_actor_id",
        "checkpoints",
        ["sponsored_by_actor_id"],
    )

    op.add_column(
        "compute_debits",
        sa.Column(
            "actor_id",
            _uuid(),
            sa.ForeignKey("actors.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_compute_debits_actor_id",
        "compute_debits",
        ["actor_id"],
    )

    # 6. ``actors.agent_definition_id`` is deferred with the catalog table.

    # 7. Research-crew backfill: attach the project OWNER account, then roster.
    #    Invalid / missing project_id or a missing OWNER leaves account_id null
    #    and does not insert a roster row.
    op.execute(
        sa.text(
            """
            UPDATE actors AS a
            SET account_id = pm.account_id
            FROM project_members pm
            WHERE a.type = 'AGENT'
              AND a.display_name = 'Research crew'
              AND a.account_id IS NULL
              AND (a.actor_metadata->>'project_id') ~* :uuid_re
              AND pm.project_id = (a.actor_metadata->>'project_id')::uuid
              AND pm.role = 'OWNER'
            """
        ).bindparams(uuid_re=_UUID_RE)
    )
    op.execute(
        sa.text(
            """
            INSERT INTO project_agent_members (
                id,
                project_id,
                actor_id,
                deployed_by_account_id,
                responsible_account_id,
                role,
                status,
                token_budget_cap,
                usd_budget_cap,
                created_at,
                updated_at
            )
            SELECT
                gen_random_uuid(),
                (a.actor_metadata->>'project_id')::uuid,
                a.id,
                a.account_id,
                a.account_id,
                'RESEARCHER',
                'ACTIVE',
                NULL,
                NULL,
                now(),
                now()
            FROM actors a
            JOIN projects p ON p.id = (a.actor_metadata->>'project_id')::uuid
            WHERE a.type = 'AGENT'
              AND a.display_name = 'Research crew'
              AND a.account_id IS NOT NULL
              AND (a.actor_metadata->>'project_id') ~* :uuid_re
            ON CONFLICT ON CONSTRAINT uq_project_agent_member DO NOTHING
            """
        ).bindparams(uuid_re=_UUID_RE)
    )

    # 8. Dark-loop debit actors only. harness_session_turn rows stay null.
    #    Bulk Core UPDATE — the documented append-only caveat.
    op.execute(
        sa.text(
            """
            UPDATE compute_debits AS d
            SET actor_id = r.agent_actor_id
            FROM agent_runs r
            WHERE d.agent_run_id = r.id
              AND d.actor_id IS NULL
              AND r.agent_actor_id IS NOT NULL
            """
        )
    )

    # 9–10. Index surgery. Create the narrower unique first so there is no
    #       window where two Research-crew rows can land; then drop the old
    #       one-agent-per-project guard. Fails closed if two Research-crew
    #       rows already share a project_id (impossible under the old index).
    #       Same transaction as the rest of the revision — a failure rolls
    #       both the new unique and the drop back together.
    op.create_index(
        "uq_actors_one_research_crew_per_project",
        "actors",
        [sa.text("(actor_metadata ->> 'project_id')")],
        unique=True,
        postgresql_where=sa.text("type = 'AGENT' AND display_name = 'Research crew'"),
    )
    op.drop_index("uq_actors_one_agent_per_project", table_name="actors")


def downgrade() -> None:
    bind = op.get_bind()
    extras = bind.execute(
        sa.text(
            """
            SELECT actor_metadata ->> 'project_id' AS project_id, COUNT(*) AS n
            FROM actors
            WHERE type = 'AGENT'
              AND actor_metadata ->> 'project_id' IS NOT NULL
            GROUP BY 1
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()
    if extras:
        raise RuntimeError(
            "Refusing downgrade of 0022_agent_actor_identity: project(s) have "
            f"more than one type=agent Actor sharing actor_metadata.project_id: "
            f"{extras}. Remove extra agents before recreating "
            "uq_actors_one_agent_per_project."
        )

    # Recreate the stricter unique first, then drop the narrower one.
    op.create_index(
        "uq_actors_one_agent_per_project",
        "actors",
        [sa.text("(actor_metadata ->> 'project_id')")],
        unique=True,
        postgresql_where=sa.text("type = 'AGENT'"),
    )
    op.drop_index("uq_actors_one_research_crew_per_project", table_name="actors")

    op.execute(sa.text("UPDATE compute_debits SET actor_id = NULL"))
    op.drop_index("ix_compute_debits_actor_id", table_name="compute_debits")
    op.drop_column("compute_debits", "actor_id")

    op.drop_index(
        "ix_checkpoints_sponsored_by_actor_id", table_name="checkpoints"
    )
    op.drop_column("checkpoints", "sponsored_by_actor_id")

    op.drop_index("ix_agent_session_tokens_lookup", table_name="agent_session_tokens")
    op.drop_index("ix_agent_session_tokens_project_id", table_name="agent_session_tokens")
    op.drop_table("agent_session_tokens")

    op.drop_index(
        "ix_project_agent_members_responsible", table_name="project_agent_members"
    )
    op.drop_index(
        "ix_project_agent_members_project_status", table_name="project_agent_members"
    )
    op.drop_index("ix_project_agent_members_actor_id", table_name="project_agent_members")
    op.drop_index(
        "ix_project_agent_members_project_id", table_name="project_agent_members"
    )
    op.drop_table("project_agent_members")

    postgresql.ENUM(name="project_agent_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="project_agent_role").drop(bind, checkfirst=True)

    op.execute(
        sa.text(
            """
            UPDATE actors
            SET account_id = NULL
            WHERE type = 'AGENT'
              AND display_name = 'Research crew'
            """
        )
    )
