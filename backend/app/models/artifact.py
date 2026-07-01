from typing import Any
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin


class Artifact(IdMixin, TimestampMixin, Base):
    __tablename__ = "artifacts"

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
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    uri: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    artifact_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    # The assumption set the artifact was produced *under* (0.9.1); see ``Evidence.assumptions``.
    # A dedicated column (not buried in ``artifact_metadata``) so provenance is honestly surfaced.
    # Free-form object in v1; defaults to ``{}`` (no assumptions recorded).
    assumptions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    project = relationship("Project", back_populates="artifacts")
    thread = relationship("Thread", back_populates="artifacts")
    validations = relationship("Validation", back_populates="artifact")
    # Evidence rows derived from / attaching this artifact (0.9.1), via evidence_artifact_links.
    evidence_links = relationship(
        "EvidenceArtifactLink",
        back_populates="artifact",
        cascade="all, delete-orphan",
    )
