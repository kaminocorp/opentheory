from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ProjectRole, ProjectStatus
from app.schemas.account import AccountSummary
from app.schemas.funding import ProjectBudget

# Generous soft cap on the long-form background (0.8.1): roomy enough for a deep briefing, bounded
# so an unbounded body can't be posted. No hard DB cap (the column is TEXT).
_BACKGROUND_MAX = 50_000


class ProjectBase(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    slug: str = Field(min_length=1, max_length=160, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    question: str = Field(min_length=1)
    description: str | None = None
    # Long-form rich-text briefing, stored as Markdown (0.8.1); optional, also settable at create.
    background: str | None = Field(default=None, max_length=_BACKGROUND_MAX)
    status: ProjectStatus = ProjectStatus.DRAFT


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    """Partial metadata update (0.8.1) — every field optional, applied with
    ``model_dump(exclude_unset=True)`` so an omitted field is left untouched. ``slug`` is **not**
    here: it is the immutable URL id. Plain in-place mutation (Project is not append-only) — no
    checkpoint, no ledger event; ``updated_at`` bumps via the ORM ``onupdate``.
    """

    title: str | None = Field(default=None, min_length=1, max_length=240)
    question: str | None = Field(default=None, min_length=1)
    description: str | None = None
    background: str | None = Field(default=None, max_length=_BACKGROUND_MAX)
    status: ProjectStatus | None = None

    @field_validator("title", "question", "status")
    @classmethod
    def _reject_explicit_null(
        cls, value: str | ProjectStatus | None
    ) -> str | ProjectStatus | None:
        # These map to NOT NULL columns. A *missing* field never reaches a validator (Pydantic v2
        # skips defaults), so `None` here means the client sent an explicit JSON `null` — reject it
        # as a 422 rather than letting it become `setattr(project, field, None)` → a NOT NULL
        # violation surfacing as an unhandled 500 at commit. Omitting the field (partial update)
        # stays valid.
        if value is None:
            raise ValueError("field may not be null")
        return value


class MemberRoleUpdate(BaseModel):
    """Body for ``PATCH /projects/{id}/members/{account_id}`` (0.8.1): the new role.

    Setting ``OWNER`` transfers ownership (the service demotes the prior owner in the same txn).
    """

    role: ProjectRole


class ProjectMemberRead(BaseModel):
    """A project membership for the public member list (0.8.1).

    Carries only the privacy-safe ``AccountSummary`` (id + display_name + public ``@username``) —
    never the principal's email/roles/external_id — so the member list is safe to serve
    unauthenticated.
    """

    model_config = ConfigDict(from_attributes=True)

    account: AccountSummary
    role: ProjectRole
    created_at: datetime


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
    # Budget derived from the funding ledger (0.6.3): funded / spent / available + breakdowns.
    budget: ProjectBudget | None = None
