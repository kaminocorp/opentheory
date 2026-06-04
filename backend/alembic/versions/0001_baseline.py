"""baseline schema: all 0.1.0 models plus 0.3.1 join tables

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-04

Single baseline migration for 0.3.0. Covers every model scaffolded in 0.1.0 plus the
two join tables introduced in 0.3.1 (``claim_evidence_links`` and ``checkpoint_refs``).

Notes:
- The named enum types use the SQLAlchemy default labels, which are the *member names*
  of the Python ``StrEnum`` classes (e.g. ``DRAFT``, ``HUMAN``) because the models do
  not set ``values_callable``. These labels must match exactly what the ORM emits.
- ``thread_stage`` is shared by ``threads`` and ``checkpoints``; it is created once here
  with ``create_type=False`` on the column usages to avoid a duplicate ``CREATE TYPE``.
- ``relation_kind`` / ``target_type`` / ``role`` are deliberately plain ``VARCHAR`` and
  validated in the service layer, not Postgres enums.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# --- named enum types -------------------------------------------------------------

ENUMS: dict[str, tuple[str, ...]] = {
    "actor_type": ("HUMAN", "AGENT", "SYSTEM"),
    "project_status": ("DRAFT", "ACTIVE", "PAUSED", "ARCHIVED"),
    "thread_stage": (
        "DECOMPOSE",
        "HYPOTHESIZE",
        "FORMALIZE",
        "DESIGN",
        "EXECUTE",
        "VALIDATE",
        "INTEGRATE",
    ),
    "thread_status": ("OPEN", "ACTIVE", "BLOCKED", "DEAD_END", "CLOSED"),
    "claim_kind": (
        "HYPOTHESIS",
        "ASSUMPTION",
        "CONSTRAINT",
        "OBSERVATION",
        "OBJECTION",
        "RESULT",
        "RETRACTION",
    ),
    "claim_status": ("PROPOSED", "SUPPORTED", "CHALLENGED", "VALIDATED", "RETRACTED"),
    "branch_status": ("OPEN", "MERGED", "CLOSED", "DEAD_END"),
    "validation_outcome": (
        "PASSED",
        "FAILED",
        "INCONCLUSIVE",
        "NEEDS_REPRODUCTION",
        "CONTRADICTS",
        "RETRACT",
    ),
    "funding_kind": ("TOP_UP", "GRANT", "REFUND", "ADJUSTMENT"),
    "funding_status": ("PENDING", "SETTLED", "FAILED", "REFUNDED"),
}


def _enum(name: str) -> postgresql.ENUM:
    """Reference an already-created enum type without re-issuing CREATE TYPE."""
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    for name, labels in ENUMS.items():
        postgresql.ENUM(*labels, name=name).create(bind, checkfirst=True)

    op.create_table(
        "projects",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", _enum("project_status"), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_projects_title", "projects", ["title"])
    # slug is unique=True + index=True on the model -> a single unique index (no
    # separate unique constraint), matching what metadata.create_all emits.
    op.create_index("ix_projects_slug", "projects", ["slug"], unique=True)

    op.create_table(
        "actors",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("type", _enum("actor_type"), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("actor_metadata", sa.JSON(), nullable=False),
        *_timestamps(),
        # unnamed to match the model's column-level unique=True (Postgres will name it
        # actors_external_id_key), keeping future autogenerate diffs empty.
        sa.UniqueConstraint("external_id"),
    )

    op.create_table(
        "threads",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("stage", _enum("thread_stage"), nullable=False),
        sa.Column("status", _enum("thread_status"), nullable=False),
        sa.Column("thread_metadata", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_threads_project_id", "threads", ["project_id"])

    op.create_table(
        "claims",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("thread_id", _uuid(), nullable=True),
        sa.Column("kind", _enum("claim_kind"), nullable=False),
        sa.Column("status", _enum("claim_status"), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("claim_metadata", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_claims_project_id", "claims", ["project_id"])
    op.create_index("ix_claims_thread_id", "claims", ["thread_id"])

    op.create_table(
        "evidence",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("thread_id", _uuid(), nullable=True),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("uri", sa.Text(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("citation", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("evidence_metadata", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_evidence_project_id", "evidence", ["project_id"])
    op.create_index("ix_evidence_thread_id", "evidence", ["thread_id"])
    op.create_index("ix_evidence_content_hash", "evidence", ["content_hash"])

    op.create_table(
        "artifacts",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("thread_id", _uuid(), nullable=True),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("uri", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("artifact_metadata", sa.JSON(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_artifacts_project_id", "artifacts", ["project_id"])
    op.create_index("ix_artifacts_thread_id", "artifacts", ["thread_id"])
    op.create_index("ix_artifacts_content_hash", "artifacts", ["content_hash"])

    op.create_table(
        "checkpoints",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("thread_id", _uuid(), nullable=True),
        sa.Column("author_id", _uuid(), nullable=True),
        sa.Column("stage", _enum("thread_stage"), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("outputs", sa.JSON(), nullable=False),
        sa.Column("tool_invocations", sa.JSON(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["author_id"], ["actors.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_checkpoints_project_id", "checkpoints", ["project_id"])
    op.create_index("ix_checkpoints_thread_id", "checkpoints", ["thread_id"])
    op.create_index("ix_checkpoints_author_id", "checkpoints", ["author_id"])

    op.create_table(
        "checkpoint_parents",
        sa.Column("checkpoint_id", _uuid(), primary_key=True),
        sa.Column("parent_id", _uuid(), primary_key=True),
        sa.ForeignKeyConstraint(["checkpoint_id"], ["checkpoints.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["checkpoints.id"]),
    )

    op.create_table(
        "branches",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("thread_id", _uuid(), nullable=True),
        sa.Column("forked_from_checkpoint_id", _uuid(), nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", _enum("branch_status"), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["forked_from_checkpoint_id"], ["checkpoints.id"], ondelete="SET NULL"
        ),
    )
    op.create_index("ix_branches_project_id", "branches", ["project_id"])
    op.create_index("ix_branches_thread_id", "branches", ["thread_id"])
    op.create_index(
        "ix_branches_forked_from_checkpoint_id", "branches", ["forked_from_checkpoint_id"]
    )

    op.create_table(
        "funding_allocations",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("actor_id", _uuid(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("kind", _enum("funding_kind"), nullable=False),
        sa.Column("status", _enum("funding_status"), nullable=False),
        sa.Column("payment_reference", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_funding_allocations_project_id", "funding_allocations", ["project_id"])
    op.create_index("ix_funding_allocations_actor_id", "funding_allocations", ["actor_id"])
    op.create_index(
        "ix_funding_allocations_payment_reference",
        "funding_allocations",
        ["payment_reference"],
    )

    op.create_table(
        "contributions",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("actor_id", _uuid(), nullable=True),
        sa.Column("checkpoint_id", _uuid(), nullable=True),
        sa.Column("funding_allocation_id", _uuid(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", _uuid(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["checkpoint_id"], ["checkpoints.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["funding_allocation_id"], ["funding_allocations.id"], ondelete="SET NULL"
        ),
    )
    op.create_index("ix_contributions_project_id", "contributions", ["project_id"])
    op.create_index("ix_contributions_actor_id", "contributions", ["actor_id"])
    op.create_index("ix_contributions_checkpoint_id", "contributions", ["checkpoint_id"])
    op.create_index(
        "ix_contributions_funding_allocation_id", "contributions", ["funding_allocation_id"]
    )
    op.create_index("ix_contributions_target_id", "contributions", ["target_id"])

    op.create_table(
        "validations",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("actor_id", _uuid(), nullable=True),
        sa.Column("claim_id", _uuid(), nullable=True),
        sa.Column("artifact_id", _uuid(), nullable=True),
        sa.Column("checkpoint_id", _uuid(), nullable=True),
        sa.Column("branch_id", _uuid(), nullable=True),
        sa.Column("outcome", _enum("validation_outcome"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["actors.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["checkpoint_id"], ["checkpoints.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_validations_project_id", "validations", ["project_id"])
    op.create_index("ix_validations_actor_id", "validations", ["actor_id"])
    op.create_index("ix_validations_claim_id", "validations", ["claim_id"])
    op.create_index("ix_validations_artifact_id", "validations", ["artifact_id"])
    op.create_index("ix_validations_checkpoint_id", "validations", ["checkpoint_id"])
    op.create_index("ix_validations_branch_id", "validations", ["branch_id"])

    op.create_table(
        "claim_evidence_links",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("claim_id", _uuid(), nullable=False),
        sa.Column("evidence_id", _uuid(), nullable=False),
        sa.Column("relation_kind", sa.String(length=20), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "claim_id", "evidence_id", "relation_kind", name="uq_claim_evidence_relation"
        ),
    )
    op.create_index("ix_claim_evidence_links_claim_id", "claim_evidence_links", ["claim_id"])
    op.create_index(
        "ix_claim_evidence_links_evidence_id", "claim_evidence_links", ["evidence_id"]
    )

    op.create_table(
        "checkpoint_refs",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("checkpoint_id", _uuid(), nullable=False),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("target_id", _uuid(), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["checkpoint_id"], ["checkpoints.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_checkpoint_refs_checkpoint_id", "checkpoint_refs", ["checkpoint_id"])
    op.create_index("ix_checkpoint_refs_target_id", "checkpoint_refs", ["target_id"])


def downgrade() -> None:
    op.drop_table("checkpoint_refs")
    op.drop_table("claim_evidence_links")
    op.drop_table("validations")
    op.drop_table("contributions")
    op.drop_table("funding_allocations")
    op.drop_table("branches")
    op.drop_table("checkpoint_parents")
    op.drop_table("checkpoints")
    op.drop_table("artifacts")
    op.drop_table("evidence")
    op.drop_table("claims")
    op.drop_table("threads")
    op.drop_table("actors")
    op.drop_table("projects")

    bind = op.get_bind()
    for name in ENUMS:
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
