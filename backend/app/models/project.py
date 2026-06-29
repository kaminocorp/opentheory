from sqlalchemy import Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import ProjectStatus


class Project(IdMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    title: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(160), nullable=False, unique=True, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Deep, optional long-form briefing (0.8.1). Markdown serialized to plaintext TEXT (not JSONB):
    # embeddable, full-text-searchable, diffable, and editor-agnostic — best for future agent FTS /
    # embedding search over the project's richest prose field. Generous soft cap in the schema.
    background: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status"),
        default=ProjectStatus.DRAFT,
        nullable=False,
    )

    threads = relationship("Thread", back_populates="project", cascade="all, delete-orphan")
    claims = relationship("Claim", back_populates="project", cascade="all, delete-orphan")
    artifacts = relationship("Artifact", back_populates="project", cascade="all, delete-orphan")
    evidence = relationship("Evidence", back_populates="project", cascade="all, delete-orphan")
    checkpoints = relationship("Checkpoint", back_populates="project", cascade="all, delete-orphan")
    branches = relationship("Branch", back_populates="project", cascade="all, delete-orphan")
    validations = relationship("Validation", back_populates="project", cascade="all, delete-orphan")
    contributions = relationship(
        "Contribution",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    funding_allocations = relationship(
        "FundingAllocation",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    # Project-level membership / authorization (0.8.1). Cascade-delete on project removal (a
    # membership has no meaning without its project); ProjectMember is not append-only, so an ORM
    # delete is permitted (unlike the ledger relationships above).
    members = relationship(
        "ProjectMember",
        back_populates="project",
        cascade="all, delete-orphan",
    )
