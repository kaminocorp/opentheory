"""agent runs: thin-agent-loop trace table + one-agent-per-project index

Revision ID: 0013_agent_runs
Revises: 0012_toolbench_provenance
Create Date: 2026-07-06

0.12.0 — foundations for the thin agent loop (``docs/executing/thin-agent-loop-0.12.md``). Additive,
no data backfill:

- ``agent_run_status`` enum (``RUNNING`` / ``COMPLETED`` / ``FAILED``) — the lifecycle of a single
  live trace row (mutable, *not* a ledger primitive; deliberately outside the append-only guards).
- ``agent_runs`` — one row per commissioned pass: the commissioning human, the (lazily-resolved)
  agent Actor, the resolved role + model, the validated plan, and the per-step trace. ``branch_id``
  / ``agent_actor_id`` / ``model`` are nullable because they are stamped *inside* the background
  pass (Decision #7), not known when the row is minted ``running`` at commission.
- ``uq_actors_one_agent_per_project`` — a partial **functional** unique index on
  ``actors (actor_metadata ->> 'project_id') WHERE type = 'AGENT'``. This is the durable guard for
  agent-actor idempotency (``services/agent_actors.py``); it is *also* declared on the ``Actor``
  model's ``__table_args__`` so the test harness's ``Base.metadata.create_all`` builds exactly what
  this migration installs — keeping create_all and Alembic in lockstep (the 0006 pattern).

Enum-label case: this DB's named enums use the StrEnum **member names** as labels, so the status
labels are uppercase ``'RUNNING'`` etc. (consistent with ``actor_type``'s ``'HUMAN'`` /
``invitation_status``'s ``'PENDING'``). ``created_at`` / ``updated_at`` carry no server default —
the ORM (``TimestampMixin``) supplies them, as with every other table.

Additive and non-destructive; ``downgrade`` drops the index, the table, and the enum.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013_agent_runs"
down_revision: str | None = "0012_toolbench_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AGENT_RUN_STATUS_LABELS = ("RUNNING", "COMPLETED", "FAILED")


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    bind = op.get_bind()

    # 1. The run-status enum (uppercase StrEnum member labels), created before the table.
    postgresql.ENUM(*_AGENT_RUN_STATUS_LABELS, name="agent_run_status").create(
        bind, checkfirst=True
    )

    # 2. The trace table. FKs inline + unnamed (Postgres names them <table>_<col>_fkey), matching
    #    the baseline idiom. `status` reuses the enum just created (create_type=False).
    op.create_table(
        "agent_runs",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("thread_id", _uuid(), nullable=False),
        sa.Column("branch_id", _uuid(), nullable=True),
        sa.Column("agent_actor_id", _uuid(), nullable=True),
        sa.Column("triggered_by_actor_id", _uuid(), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                *_AGENT_RUN_STATUS_LABELS, name="agent_run_status", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("planned_count", sa.Integer(), nullable=False),
        sa.Column("ran_count", sa.Integer(), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["agent_actor_id"], ["actors.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["triggered_by_actor_id"], ["actors.id"], ondelete="SET NULL"),
    )
    # Per-FK lookup indexes (the model declares index=True on project_id and thread_id only).
    op.create_index("ix_agent_runs_project_id", "agent_runs", ["project_id"])
    op.create_index("ix_agent_runs_thread_id", "agent_runs", ["thread_id"])

    # 3. One agent Actor per project — a partial FUNCTIONAL unique index (mirrors the Actor model's
    #    __table_args__). Idempotency for services/agent_actors.py.
    op.create_index(
        "uq_actors_one_agent_per_project",
        "actors",
        [sa.text("(actor_metadata ->> 'project_id')")],
        unique=True,
        postgresql_where=sa.text("type = 'AGENT'"),
    )


def downgrade() -> None:
    op.drop_index("uq_actors_one_agent_per_project", table_name="actors")
    op.drop_index("ix_agent_runs_thread_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_project_id", table_name="agent_runs")
    op.drop_table("agent_runs")
    postgresql.ENUM(name="agent_run_status").drop(op.get_bind(), checkfirst=True)
