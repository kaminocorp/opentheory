"""agent_runs.grounding_yield: what a pass bought, beside what it spent

Revision ID: 0014_agent_run_grounding_yield
Revises: 0013_agent_runs
Create Date: 2026-08-01

0.16.1 — the trace already recorded a pass's *spend* (``planned_count`` / ``ran_count`` /
``tokens_used``) and nothing about its *result*. This adds one JSON column holding the before/after
grounding rung of every open claim the pass could have moved, plus the two counts derived from it
(``measured`` / ``moved``) — see ``app/schemas/agent_run.py::PassYield`` for the shape.

Why a stored column rather than a read-time derivation: the ``after`` rung must be captured *inside*
the pass. Deriving it on read would credit the agent for a rung a human raised an hour later, which
is exactly the attribution confusion the funder/contributor/validator separation exists to prevent.

Additive and non-destructive: ``NOT NULL`` with a ``'{}'`` server default, so every existing
``agent_runs`` row reads as an empty measure (``measured: 0, moved: 0``) with no backfill. Nothing
about the yield is authoritative ledger state — the checkpoints a pass landed remain the append-only
record; this is the mutable trace's narrative, like ``plan`` and ``steps`` beside it.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_agent_run_grounding_yield"
down_revision: str | None = "0013_agent_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column(
            "grounding_yield",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "grounding_yield")
