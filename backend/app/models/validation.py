from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import ValidationOutcome


class Validation(IdMixin, TimestampMixin, Base):
    __tablename__ = "validations"

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
    claim_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="SET NULL"),
        index=True,
    )
    artifact_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("artifacts.id", ondelete="SET NULL"),
        index=True,
    )
    checkpoint_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("checkpoints.id", ondelete="SET NULL"),
        index=True,
    )
    branch_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="SET NULL"),
        index=True,
    )
    outcome: Mapped[ValidationOutcome] = mapped_column(
        Enum(ValidationOutcome, name="validation_outcome"),
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text)

    project = relationship("Project", back_populates="validations")
    actor = relationship("Actor", back_populates="validations")
    claim = relationship("Claim", back_populates="validations")
    artifact = relationship("Artifact", back_populates="validations")
    checkpoint = relationship("Checkpoint", back_populates="validations")
    branch = relationship("Branch", back_populates="validations")
