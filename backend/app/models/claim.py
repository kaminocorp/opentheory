from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Enum, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import ClaimKind, ClaimStatus


class Claim(IdMixin, TimestampMixin, Base):
    __tablename__ = "claims"

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
    kind: Mapped[ClaimKind] = mapped_column(Enum(ClaimKind, name="claim_kind"), nullable=False)
    status: Mapped[ClaimStatus] = mapped_column(
        Enum(ClaimStatus, name="claim_status"),
        default=ClaimStatus.PROPOSED,
        nullable=False,
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    claim_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    project = relationship("Project", back_populates="claims")
    thread = relationship("Thread", back_populates="claims")
    validations = relationship("Validation", back_populates="claim")
    evidence_links = relationship(
        "ClaimEvidenceLink",
        back_populates="claim",
        cascade="all, delete-orphan",
    )
