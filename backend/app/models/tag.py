"""Tag — an immutable named pointer at a checkpoint (0.21.0).

A lightweight annotation, not a rewrite: the tagged checkpoint is unchanged, and a
correction is a *new* tag (or a ``retraction`` kind), never an edit. Name uniqueness
is per-project so ``v1`` cannot silently overwrite ``v1``.
"""

from uuid import UUID

from sqlalchemy import Enum, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import TagKind


class Tag(IdMixin, TimestampMixin, Base):
    __tablename__ = "tags"
    # Honesty: a second write with the same project+name is a conflict, never a retarget.
    # Mirrored by migration 0016 so create_all and Alembic stay in lockstep.
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_tags_project_name"),)

    project_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    checkpoint_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("checkpoints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("actors.id", ondelete="SET NULL"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    kind: Mapped[TagKind] = mapped_column(
        Enum(TagKind, name="tag_kind"),
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text)

    project = relationship("Project", back_populates="tags")
    checkpoint = relationship("Checkpoint", foreign_keys=[checkpoint_id])
    author = relationship("Actor")
