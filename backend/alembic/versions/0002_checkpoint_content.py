"""checkpoint free-form content and optional stage

Revision ID: 0002_checkpoint_content
Revises: 0001_baseline
Create Date: 2026-06-04

0.3.2 makes the checkpoint primitive real. Two column-level changes on ``checkpoints``:

- Add ``content`` (JSON, NOT NULL): the free-form payload a user authors when creating a
  checkpoint. Added without a server default — the table is empty at this point in the
  chain (the baseline creates it with no rows), and the ORM supplies a ``{}`` default on
  insert, so no backfill is required.
- Make ``stage`` nullable: a research-flow stage is optional metadata, not platform law
  (see docs/primitives.md), so a human may record a checkpoint without one.

No other tables change. ``relation_kind``/``target_type``/``role`` remain plain VARCHAR.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_checkpoint_content"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Reference the existing thread_stage enum without re-issuing CREATE TYPE.
_THREAD_STAGE = postgresql.ENUM(
    "DECOMPOSE",
    "HYPOTHESIZE",
    "FORMALIZE",
    "DESIGN",
    "EXECUTE",
    "VALIDATE",
    "INTEGRATE",
    name="thread_stage",
    create_type=False,
)


def upgrade() -> None:
    op.add_column("checkpoints", sa.Column("content", sa.JSON(), nullable=False))
    op.alter_column(
        "checkpoints",
        "stage",
        existing_type=_THREAD_STAGE,
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "checkpoints",
        "stage",
        existing_type=_THREAD_STAGE,
        nullable=False,
    )
    op.drop_column("checkpoints", "content")
