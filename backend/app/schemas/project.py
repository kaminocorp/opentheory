from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ProjectStatus


class ProjectBase(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    slug: str = Field(min_length=1, max_length=160, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    question: str = Field(min_length=1)
    description: str | None = None
    status: ProjectStatus = ProjectStatus.DRAFT


class ProjectCreate(ProjectBase):
    pass


class ProjectRead(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class ProjectCounts(BaseModel):
    """Aggregate counts shown at a glance on the workspace header (0.3.4)."""

    threads: int
    claims: int
    evidence: int
    checkpoints: int


class ProjectOverview(ProjectRead):
    """Project detail enriched with aggregate ledger counts."""

    counts: ProjectCounts
