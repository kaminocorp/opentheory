from uuid import UUID

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import BranchStatus


class Branch(IdMixin, TimestampMixin, Base):
    __tablename__ = "branches"

    project_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    thread_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("threads.id", ondelete="SET NULL"),
        index=True,
    )
    forked_from_checkpoint_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("checkpoints.id", ondelete="SET NULL"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[BranchStatus] = mapped_column(
        Enum(BranchStatus, name="branch_status"),
        default=BranchStatus.OPEN,
        nullable=False,
    )

    project = relationship("Project", back_populates="branches")
    thread = relationship("Thread", back_populates="branches")
    # The checkpoint this branch forked from (via branches.forked_from_checkpoint_id).
    # Pinned because checkpoints.branch_id (0.4.2) adds a second FK between the two tables.
    forked_from_checkpoint = relationship(
        "Checkpoint",
        foreign_keys="Branch.forked_from_checkpoint_id",
    )
    # The checkpoints recorded on this branch (via checkpoints.branch_id).
    checkpoints = relationship(
        "Checkpoint",
        back_populates="branch",
        foreign_keys="Checkpoint.branch_id",
    )
    validations = relationship("Validation", back_populates="branch")
