"""toolbench provenance: evidence<->artifact links + assumptions columns

Revision ID: 0012_toolbench_provenance
Revises: 0011_project_agent_models
Create Date: 2026-07-01

0.9.1 — the provenance spine for the maths toolbench (Phase 1 of
``docs/executing/toolbench-provenance-and-first-instruments.md``). Two additive changes so the
ledger can hold a tool-produced result with full provenance:

1. ``evidence_artifact_links`` — a typed many-to-many join (mirroring ``claim_evidence_links``) so
   an ``Evidence`` row can be *derived from* / *attach* one or more ``Artifact`` rows. ``role`` is a
   plain VARCHAR validated in the service layer (``derived_from`` / ``attachment``); Postgres-enum
   promotion is deferred until the vocabulary stabilises.
2. ``evidence.assumptions`` + ``artifacts.assumptions`` — a dedicated JSON column (not buried in
   ``*_metadata``) carrying the assumption set a result was computed under, so it is honestly
   surfaced on the evidence card. ``NOT NULL`` with a ``'{}'`` server default, so every existing row
   backfills to an empty assumption set without a data pass (the ``0011`` agent_models pattern).

**No change to ``checkpoints.tool_invocations``** — the column already exists as free-form JSON
(baseline 0.1.0). The blame tuple is *promoted* to a validated shape in the schema/service layer
(``schemas/tool_invocation.py`` strict-write, lenient raw-JSON read), not in the DB — so its
immutability rides for free on the append-only ``Checkpoint`` (plan Decision 2). No dedicated
``tool_invocations`` / ``instruments`` / ``engines`` tables (Decisions 2-4).

Additive and non-destructive; ``downgrade`` drops the two columns and the join table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0012_toolbench_provenance"
down_revision: str | None = "0011_project_agent_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _timestamps() -> list[sa.Column]:
    # Populated by the ORM (``TimestampMixin`` client-side defaults), as with every other table in
    # the baseline — no server default here.
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "evidence_artifact_links",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("evidence_id", _uuid(), nullable=False),
        sa.Column("artifact_id", _uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "evidence_id", "artifact_id", "role", name="uq_evidence_artifact_role"
        ),
    )
    op.create_index(
        "ix_evidence_artifact_links_evidence_id", "evidence_artifact_links", ["evidence_id"]
    )
    op.create_index(
        "ix_evidence_artifact_links_artifact_id", "evidence_artifact_links", ["artifact_id"]
    )

    # NOT NULL + server default so existing rows backfill to an empty assumption set (0011 pattern).
    op.add_column(
        "evidence",
        sa.Column("assumptions", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        "artifacts",
        sa.Column("assumptions", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("artifacts", "assumptions")
    op.drop_column("evidence", "assumptions")
    op.drop_index("ix_evidence_artifact_links_artifact_id", table_name="evidence_artifact_links")
    op.drop_index("ix_evidence_artifact_links_evidence_id", table_name="evidence_artifact_links")
    op.drop_table("evidence_artifact_links")
