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
    """Aggregate counts shown at a glance on the workspace header (0.3.4; +0.4.4)."""

    threads: int
    claims: int
    evidence: int
    checkpoints: int
    validations: int = 0
    branches: int = 0


class BranchStatusCounts(BaseModel):
    """Branches broken down by lifecycle status (0.4.4)."""

    open: int = 0
    dead_end: int = 0
    closed: int = 0


class ContradictionItem(BaseModel):
    """A contested claim: one carrying an unretracted contradicts/failed validation (0.4.4)."""

    claim_id: UUID
    thread_id: UUID | None
    statement: str


class ProjectOverview(ProjectRead):
    """Project detail enriched with aggregate ledger counts and integrity summaries."""

    counts: ProjectCounts
    branch_counts: BranchStatusCounts = Field(default_factory=BranchStatusCounts)
    contradictions: list[ContradictionItem] = Field(default_factory=list)
