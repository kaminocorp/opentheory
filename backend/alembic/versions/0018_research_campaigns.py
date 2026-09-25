"""research_campaigns: continuous research loop traces

Revision ID: 0018_research_campaigns
Revises: 0017_orchestration_runs
Create Date: 2026-09-25

0.25.0 — continuous research under budget. Additive, no data backfill:

- ``research_campaign_status`` enum (``RUNNING`` / ``COMPLETED`` / ``FAILED``) —
  the lifecycle of one continuous campaign (mutable, *not* a ledger primitive;
  deliberately outside the append-only guards).
- ``research_campaigns`` — one row per commissioned campaign: the commissioning
  human, the Research-crew role each cycle runs as, the per-cycle narrative
  (linked ``OrchestrationRun`` ids), the stop reason, and the budget remainder.
  Ledger writes stay on the commissioned orchestration → agent-pass path.

Enum-label case: this DB's named enums use the StrEnum **member names** as labels, so
the status labels are uppercase ``'RUNNING'`` etc. ``created_at`` / ``updated_at``
carry no server default — the ORM (``TimestampMixin``) supplies them.

Additive and non-destructive; ``downgrade`` drops the indexes, the table, and the enum.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0018_research_campaigns"
down_revision: str | None = "0017_orchestration_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_LABELS = ("RUNNING", "COMPLETED", "FAILED")


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    bind = op.get_bind()

    postgresql.ENUM(*_STATUS_LABELS, name="research_campaign_status").create(
        bind, checkfirst=True
    )

    op.create_table(
        "research_campaigns",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("triggered_by_actor_id", _uuid(), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(*_STATUS_LABELS, name="research_campaign_status", create_type=False),
            nullable=False,
        ),
        sa.Column("cycles", sa.JSON(), nullable=False),
        sa.Column("stop_reason", sa.String(length=40), nullable=True),
        sa.Column("current_cycle", sa.Integer(), nullable=False),
        sa.Column("cycles_completed", sa.Integer(), nullable=False),
        sa.Column("consecutive_errors", sa.Integer(), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("budget_available_start", sa.Numeric(12, 6), nullable=True),
        sa.Column("budget_available_end", sa.Numeric(12, 6), nullable=True),
        sa.Column("max_cycles", sa.Integer(), nullable=False),
        sa.Column("error_budget", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["triggered_by_actor_id"], ["actors.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_research_campaigns_project_id", "research_campaigns", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_research_campaigns_project_id", table_name="research_campaigns")
    op.drop_table("research_campaigns")
    postgresql.ENUM(name="research_campaign_status").drop(op.get_bind(), checkfirst=True)
