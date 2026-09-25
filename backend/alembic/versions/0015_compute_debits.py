"""compute_debits: project-scoped agent spend ledger

Revision ID: 0015_compute_debits
Revises: 0014_agent_run_grounding_yield
Create Date: 2026-09-25

0.19.0 — project-budget metering (historically sketched as deferred ``0.12.5``). Additive,
no data backfill:

- ``compute_debit_kind`` enum (``PLANNING`` / ``EXECUTION``) — the accounting category of
  one debit. v1 writes ``PLANNING`` (the single planning-call tokens).
- ``compute_debits`` — append-only spend against a project's funded budget. ``spent`` on
  the funding read model is Σ these rows. The agent is a contributor, never a funder:
  this table is deliberately **not** ``funding_allocations`` (a negative allocation would
  shrink ``funded`` and attribute money to an Account).
- ``uq_compute_debits_one_per_agent_run`` — partial unique on ``agent_run_id`` so a pass
  cannot be billed twice. Declared here *and* on the model so ``create_all`` matches.

Enum-label case: this DB's named enums use the StrEnum **member names** as labels, so
the kind labels are uppercase ``'PLANNING'`` / ``'EXECUTION'``. ``created_at`` /
``updated_at`` carry no server default — the ORM (``TimestampMixin``) supplies them.

Additive and non-destructive; ``downgrade`` drops the index, the table, and the enum.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0015_compute_debits"
down_revision: str | None = "0014_agent_run_grounding_yield"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KIND_LABELS = ("PLANNING", "EXECUTION")


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    bind = op.get_bind()

    postgresql.ENUM(*_KIND_LABELS, name="compute_debit_kind").create(bind, checkfirst=True)

    op.create_table(
        "compute_debits",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("agent_run_id", _uuid(), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 6), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("rate_per_1k", sa.Numeric(12, 6), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM(*_KIND_LABELS, name="compute_debit_kind", create_type=False),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_compute_debits_project_id", "compute_debits", ["project_id"])
    op.create_index("ix_compute_debits_agent_run_id", "compute_debits", ["agent_run_id"])
    op.create_index(
        "uq_compute_debits_one_per_agent_run",
        "compute_debits",
        ["agent_run_id"],
        unique=True,
        postgresql_where=sa.text("agent_run_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_compute_debits_one_per_agent_run", table_name="compute_debits")
    op.drop_index("ix_compute_debits_agent_run_id", table_name="compute_debits")
    op.drop_index("ix_compute_debits_project_id", table_name="compute_debits")
    op.drop_table("compute_debits")
    postgresql.ENUM(name="compute_debit_kind").drop(op.get_bind(), checkfirst=True)
