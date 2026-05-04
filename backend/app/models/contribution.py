from uuid import UUID

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin


class Contribution(IdMixin, TimestampMixin, Base):
    __tablename__ = "contributions"

    project_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("actors.id", ondelete="SET NULL"),
        index=True,
    )
    checkpoint_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("checkpoints.id", ondelete="SET NULL"),
        index=True,
    )
    funding_allocation_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("funding_allocations.id", ondelete="SET NULL"),
        index=True,
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), index=True)
    notes: Mapped[str | None] = mapped_column(Text)

    project = relationship("Project", back_populates="contributions")
    actor = relationship("Actor", back_populates="contributions")
    checkpoint = relationship("Checkpoint", back_populates="contributions")
    funding_allocation = relationship("FundingAllocation", back_populates="contributions")
