"""orchestration_runs: project-level multi-thread research loop traces

Revision ID: 0017_orchestration_runs
Revises: 0016_research_git_merge_tag
Create Date: 2026-09-25

0.22.0 — thin multi-thread orchestrator. Additive, no data backfill:

- ``orchestration_run_status`` enum (``RUNNING`` / ``COMPLETED`` / ``FAILED``) — the
  lifecycle of one project-level loop (mutable, *not* a ledger primitive; deliberately
  outside the append-only guards).
- ``orchestration_runs`` — one row per commissioned orchestration: the commissioning
  human, the Research-crew role each sub-pass runs as, the per-thread decision
  narrative, the stop reason, and the budget remainder. Ledger writes stay on the
  commissioned ``AgentRun`` rows through ``run_agent_pass``.

Enum-label case: this DB's named enums use the StrEnum **member names** as labels, so
the status labels are uppercase ``'RUNNING'`` etc. ``created_at`` / ``updated_at``
carry no server default — the ORM (``TimestampMixin``) supplies them.

Additive and non-destructive; ``downgrade`` drops the indexes, the table, and the enum.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0017_orchestration_runs"
down_revision: str | None = "0016_research_git_merge_tag"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_LABELS = ("RUNNING", "COMPLETED", "FAILED")


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    bind = op.get_bind()

    postgresql.ENUM(*_STATUS_LABELS, name="orchestration_run_status").create(
        bind, checkfirst=True
    )

    op.create_table(
        "orchestration_runs",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("triggered_by_actor_id", _uuid(), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(*_STATUS_LABELS, name="orchestration_run_status", create_type=False),
            nullable=False,
        ),
        sa.Column("decisions", sa.JSON(), nullable=False),
        sa.Column("stop_reason", sa.String(length=40), nullable=True),
        sa.Column("passes_commissioned", sa.Integer(), nullable=False),
        sa.Column("passes_completed", sa.Integer(), nullable=False),
        sa.Column("passes_failed", sa.Integer(), nullable=False),
        sa.Column("passes_skipped", sa.Integer(), nullable=False),
        sa.Column("budget_available_start", sa.Numeric(12, 6), nullable=True),
        sa.Column("budget_available_end", sa.Numeric(12, 6), nullable=True),
        sa.Column("max_passes", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["triggered_by_actor_id"], ["actors.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_orchestration_runs_project_id", "orchestration_runs", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_orchestration_runs_project_id", table_name="orchestration_runs")
    op.drop_table("orchestration_runs")
    postgresql.ENUM(name="orchestration_run_status").drop(op.get_bind(), checkfirst=True)
