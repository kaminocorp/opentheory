from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin


class ClaimEvidenceLink(IdMixin, TimestampMixin, Base):
    """Many-to-many tie between a claim and a piece of evidence.

    A single evidence row can back multiple claims, and the same claim/evidence
    pair can be recorded under different ``relation_kind`` values. ``relation_kind``
    is stored as a plain string and validated in the service layer (allowed values:
    ``support``, ``weaken``, ``context``); promotion to a Postgres enum is deferred
    until the vocabulary stabilises.
    """

    __tablename__ = "claim_evidence_links"
    __table_args__ = (
        UniqueConstraint(
            "claim_id",
            "evidence_id",
            "relation_kind",
            name="uq_claim_evidence_relation",
        ),
    )

    claim_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("evidence.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relation_kind: Mapped[str] = mapped_column(String(20), nullable=False)

    claim = relationship("Claim", back_populates="evidence_links")
    evidence = relationship("Evidence", back_populates="claim_links")


class CheckpointRef(IdMixin, TimestampMixin, Base):
    """Polymorphic reference from a checkpoint to a referenced primitive.

    Introduced in 0.3.1 (consumed in 0.3.2) so the checkpoint service can record one
    row per referenced claim/evidence/artifact/thread without a follow-up migration.
    ``target_type``/``role`` are plain strings validated in the service layer; there is
    deliberately no foreign key on ``target_id`` because it is polymorphic.
    """

    __tablename__ = "checkpoint_refs"

    checkpoint_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("checkpoints.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(40), nullable=False)

    checkpoint = relationship("Checkpoint", back_populates="refs")
