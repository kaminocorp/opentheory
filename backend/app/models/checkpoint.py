from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Column, Enum, ForeignKey, Table, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import ThreadStage

checkpoint_parent = Table(
    "checkpoint_parents",
    Base.metadata,
    Column("checkpoint_id", PgUUID(as_uuid=True), ForeignKey("checkpoints.id"), primary_key=True),
    Column("parent_id", PgUUID(as_uuid=True), ForeignKey("checkpoints.id"), primary_key=True),
)


class Checkpoint(IdMixin, TimestampMixin, Base):
    __tablename__ = "checkpoints"

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
    author_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("actors.id", ondelete="SET NULL"),
        index=True,
    )
    stage: Mapped[ThreadStage] = mapped_column(
        Enum(ThreadStage, name="thread_stage"),
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    outputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    tool_invocations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    project = relationship("Project", back_populates="checkpoints")
    thread = relationship("Thread", back_populates="checkpoints")
    author = relationship("Actor", back_populates="checkpoints")
    parents = relationship(
        "Checkpoint",
        secondary=checkpoint_parent,
        primaryjoin="Checkpoint.id == checkpoint_parents.c.checkpoint_id",
        secondaryjoin="Checkpoint.id == checkpoint_parents.c.parent_id",
    )
    validations = relationship("Validation", back_populates="checkpoint")
    contributions = relationship("Contribution", back_populates="checkpoint")
    refs = relationship(
        "CheckpointRef",
        back_populates="checkpoint",
        cascade="all, delete-orphan",
    )
