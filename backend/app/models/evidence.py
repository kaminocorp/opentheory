from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin


class Evidence(IdMixin, TimestampMixin, Base):
    __tablename__ = "evidence"

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
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    uri: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    citation: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    evidence_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    # The assumption set a tool result was computed *under* (0.9.1) — SymPy-style keys such as
    # ``positive`` / ``integer`` / ``nonzero``, or a flagship ``angle=90``. A dedicated column (not
    # buried in ``evidence_metadata``) so it is honestly surfaced on the evidence card: an
    # unconditional claim recorded without its assumptions is a lie the append-only ledger can never
    # edit out. Captured at write-time; free-form object in v1; defaults to ``{}`` (no assumptions).
    assumptions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    project = relationship("Project", back_populates="evidence")
    thread = relationship("Thread", back_populates="evidence")
    claim_links = relationship(
        "ClaimEvidenceLink",
        back_populates="evidence",
        cascade="all, delete-orphan",
    )
    # Artifacts this evidence was derived from / attaches (0.9.1), via evidence_artifact_links.
    artifact_links = relationship(
        "EvidenceArtifactLink",
        back_populates="evidence",
        cascade="all, delete-orphan",
    )
