"""research-git tags: named immutable pointers at checkpoints

Revision ID: 0016_research_git_merge_tag
Revises: 0015_compute_debits
Create Date: 2026-09-25

0.21.0 — research-git merge + tag. Additive, no data backfill:

- ``tag_kind`` enum (``MILESTONE`` / ``VALIDATED`` / ``RETRACTION``) — why a named
  pointer was pinned. Labels are StrEnum **member names**, this DB's convention.
- ``tags`` — append-only named pointer at a checkpoint. A colliding
  ``(project_id, name)`` is a conflict, never a silent retarget.
- ``uq_tags_project_name`` — unique on ``(project_id, name)``. Declared here *and*
  on the model so ``create_all`` matches.

Merge itself needs no table: it is a multi-parent ``Checkpoint`` (the
``checkpoint_parents`` join already exists) plus a ``merged`` branch status that
has been on ``branch_status`` since the baseline. ``created_at`` / ``updated_at``
carry no server default — the ORM (``TimestampMixin``) supplies them.

Additive and non-destructive; ``downgrade`` drops the unique constraint, indexes,
the table, and the enum.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0016_research_git_merge_tag"
down_revision: str | None = "0015_compute_debits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KIND_LABELS = ("MILESTONE", "VALIDATED", "RETRACTION")


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    bind = op.get_bind()

    postgresql.ENUM(*_KIND_LABELS, name="tag_kind").create(bind, checkfirst=True)

    op.create_table(
        "tags",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("checkpoint_id", _uuid(), nullable=False),
        sa.Column("author_id", _uuid(), nullable=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM(*_KIND_LABELS, name="tag_kind", create_type=False),
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["checkpoint_id"], ["checkpoints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["actors.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("project_id", "name", name="uq_tags_project_name"),
    )
    op.create_index("ix_tags_project_id", "tags", ["project_id"])
    op.create_index("ix_tags_checkpoint_id", "tags", ["checkpoint_id"])
    op.create_index("ix_tags_author_id", "tags", ["author_id"])


def downgrade() -> None:
    op.drop_index("ix_tags_author_id", table_name="tags")
    op.drop_index("ix_tags_checkpoint_id", table_name="tags")
    op.drop_index("ix_tags_project_id", table_name="tags")
    op.drop_table("tags")
    postgresql.ENUM(name="tag_kind").drop(op.get_bind(), checkfirst=True)
