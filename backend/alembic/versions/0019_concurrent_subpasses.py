"""orchestration concurrency + compute reservation holds

Revision ID: 0019_concurrent_subpasses
Revises: 0018_research_campaigns
Create Date: 2026-09-25

0.27.0 — concurrent sub-passes under the project budget. Additive, no data
backfill beyond column defaults:

- ``orchestration_runs.concurrency`` — the bound this run used (copied from
  settings at commission so a later default change never rewrites history).
- ``orchestration_runs.cancel_requested`` — honoured between waves; in-flight
  passes finish. Campaign Stop also sets this on the current orchestration.
- ``agent_runs.reserved_amount`` — a mutable hold against
  ``project_budget.available`` while a pass is in flight. Not a ``ComputeDebit``
  (those stay append-only and debit-after-tokens). Released when the debit is
  recorded or the pass finalizes without spending.

Server defaults backfill existing rows (concurrency=2, cancel_requested=false,
reserved_amount null). Additive and non-destructive.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0019_concurrent_subpasses"
down_revision: str | None = "0018_research_campaigns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "orchestration_runs",
        sa.Column("concurrency", sa.Integer(), nullable=False, server_default="2"),
    )
    op.add_column(
        "orchestration_runs",
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "agent_runs",
        sa.Column("reserved_amount", sa.Numeric(12, 6), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "reserved_amount")
    op.drop_column("orchestration_runs", "cancel_requested")
    op.drop_column("orchestration_runs", "concurrency")
