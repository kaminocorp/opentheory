"""agent definition catalog + actors.agent_definition_id

Revision ID: 0024_agent_definitions
Revises: 0023_lock_public_api_rls
Create Date: 2026-10-06

0.59.0 — slice G of the approved agent-actor identity design
(``docs/plans/agent-actor-identity.md``). Adds the versioned
``agent_definitions`` catalog (owned by an Account, unique
``(family_id, version)``) **and** ``actors.agent_definition_id``
(nullable FK) in the same revision. Additive. The pointer is
deploy-time; same-Actor retarget is rejected in the ORM.

Rebases after ``0023_lock_public_api_rls`` (0.58.1). After
``create_table`` this revision runs ``LOCK_PUBLIC_TABLES_SQL``
so the new public table is ENABLE+FORCE RLS in the same
transaction. No policies. No GRANT to anon/authenticated.

The whole revision is **one transaction** (plain ``op.create_index`` /
``op.drop_index``). No ``CREATE INDEX CONCURRENTLY`` / autocommit.
Live prod at review is still at 0021; this revision chains after
0023 and must not assume 0022 is already applied on Fly.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.db.rls_lock import LOCK_PUBLIC_TABLES_SQL

revision: str = "0024_agent_definitions"
down_revision: str | None = "0023_lock_public_api_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "agent_definitions",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("account_id", _uuid(), nullable=True),
        sa.Column("family_id", _uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("config_fingerprint", sa.Text(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("family_id", "version", name="uq_agent_definitions_family_version"),
    )
    op.create_index(
        "ix_agent_definitions_account_id", "agent_definitions", ["account_id"]
    )
    op.create_index(
        "ix_agent_definitions_family_id", "agent_definitions", ["family_id"]
    )

    op.add_column(
        "actors",
        sa.Column(
            "agent_definition_id",
            _uuid(),
            sa.ForeignKey("agent_definitions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_actors_agent_definition_id", "actors", ["agent_definition_id"]
    )
    op.execute(sa.text(LOCK_PUBLIC_TABLES_SQL))


def downgrade() -> None:
    op.drop_index("ix_actors_agent_definition_id", table_name="actors")
    op.drop_column("actors", "agent_definition_id")
    op.drop_index("ix_agent_definitions_family_id", table_name="agent_definitions")
    op.drop_index("ix_agent_definitions_account_id", table_name="agent_definitions")
    op.drop_table("agent_definitions")
