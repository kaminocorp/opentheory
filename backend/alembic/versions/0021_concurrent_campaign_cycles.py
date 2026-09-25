"""research_campaigns.concurrency — bounded concurrent cycles

Revision ID: 0021_concurrent_campaign_cycles
Revises: 0020_compute_debit_live_rates
Create Date: 2026-09-25

0.32.0 — concurrent campaign cycles under the project budget. Additive, no
data rewrite:

- ``research_campaigns.concurrency`` — how many 0.22.0 orchestrations this
  campaign may run at once (copied from settings at commission so a later
  default change never rewrites history). ``1`` is the sequential fallback
  shipped in ``0.25.0``.

Server default backfills existing rows to ``1``. Additive and non-destructive.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021_concurrent_campaign_cycles"
down_revision: str | None = "0020_compute_debit_live_rates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_campaigns",
        sa.Column("concurrency", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("research_campaigns", "concurrency")
