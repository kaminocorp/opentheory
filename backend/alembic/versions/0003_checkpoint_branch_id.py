"""checkpoint branch_id (which line a checkpoint sits on)

Revision ID: 0003_checkpoint_branch_id
Revises: 0002_checkpoint_content
Create Date: 2026-06-05

0.4.2 activates branches. A single column-level change on ``checkpoints``:

- Add ``branch_id`` (UUID, NULL) with an FK to ``branches.id`` ``ON DELETE SET NULL`` and
  an index. ``NULL`` means the checkpoint is on the project's main line (plan Decision #2);
  a non-null value places it on a Branch. Nullable + no default, so it is a no-op backfill
  on the empty baseline table and existing checkpoints simply become main-line.

This introduces a second FK between ``checkpoints`` and ``branches`` (the baseline already
has ``branches.forked_from_checkpoint_id`` -> ``checkpoints.id``). The cycle is fine to add
here because both tables already exist; ``op.add_column`` with an inline FK emits a plain
``ALTER TABLE ... ADD CONSTRAINT`` after the fact. No enum or other table changes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_checkpoint_branch_id"
down_revision: str | None = "0002_checkpoint_content"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "checkpoints",
        sa.Column(
            "branch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("branches.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_checkpoints_branch_id", "checkpoints", ["branch_id"])


def downgrade() -> None:
    op.drop_index("ix_checkpoints_branch_id", table_name="checkpoints")
    op.drop_column("checkpoints", "branch_id")
