"""project agent_models: per-role OpenRouter model roster

Revision ID: 0011_project_agent_models
Revises: 0010_project_invitations
Create Date: 2026-06-29

0.8.10 — assign an OpenRouter model to each research role (Research Lead / Thread Manager /
Researcher / Research Assistant). Adds a single ``agent_models`` JSON column on ``projects``: a map
keyed by role name → OpenRouter model id, with an unassigned role simply absent/``None``. This is
project **configuration**, not credit — it never touches Contribution/Validation/FundingAllocation
and mints no checkpoint.

Additive and non-destructive: the column is ``NOT NULL`` with a ``'{}'`` server default, so every
existing row gets an empty roster without a backfill pass. The role→id shape is validated in the
schema layer (``AgentModels`` / ``AgentModelsUpdate``) and against the curated catalog only on
write, so the roster can grow without a migration. Stored generic JSON for parity with the other
metadata maps (``account_metadata`` / ``actor_metadata``).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_project_agent_models"
down_revision: str | None = "0010_project_invitations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "agent_models",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "agent_models")
