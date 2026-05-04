from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import ThreadStage, ThreadStatus


class Thread(IdMixin, TimestampMixin, Base):
    __tablename__ = "threads"

    project_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    stage: Mapped[ThreadStage] = mapped_column(
        Enum(ThreadStage, name="thread_stage"),
        default=ThreadStage.DECOMPOSE,
        nullable=False,
    )
    status: Mapped[ThreadStatus] = mapped_column(
        Enum(ThreadStatus, name="thread_status"),
        default=ThreadStatus.OPEN,
        nullable=False,
    )
    thread_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    project = relationship("Project", back_populates="threads")
    claims = relationship("Claim", back_populates="thread")
    artifacts = relationship("Artifact", back_populates="thread")
    evidence = relationship("Evidence", back_populates="thread")
    checkpoints = relationship("Checkpoint", back_populates="thread")
    branches = relationship("Branch", back_populates="thread")
