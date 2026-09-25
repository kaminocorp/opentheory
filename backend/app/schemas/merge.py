from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.models.enums import MergeResolution
from app.schemas.branch import BranchRead
from app.schemas.checkpoint import CheckpointRead

_MAX_SOURCE_BRANCHES = 16


class MergeCreate(BaseModel):
    """Synthesize one or more open branches onto a target line (0.21.0).

    ``source_branch_ids`` are the lines being combined (must be open, in-project).
    ``target_branch_id`` is the line that receives the merge checkpoint; ``None`` is
    the project main line. ``resolution=resolved`` requires a non-empty ``rationale``
    — a conflict cannot be papered over silently. ``claim_ids`` optionally names the
    claims being unified (recorded as refs; claim rows are not rewritten).
    """

    source_branch_ids: list[UUID] = Field(min_length=1, max_length=_MAX_SOURCE_BRANCHES)
    target_branch_id: UUID | None = None
    resolution: MergeResolution
    rationale: str | None = None
    claim_ids: list[UUID] = Field(default_factory=list)
    summary: str | None = None
    thread_id: UUID | None = None

    @model_validator(mode="after")
    def _resolved_needs_rationale(self) -> "MergeCreate":
        if self.resolution == MergeResolution.RESOLVED and not (self.rationale or "").strip():
            raise ValueError("rationale is required when resolution is resolved")
        return self


class MergeRead(BaseModel):
    """The merge checkpoint plus the source branches now marked ``merged``."""

    checkpoint: CheckpointRead
    source_branches: list[BranchRead]
    target_branch_id: UUID | None
    resolution: MergeResolution
    parent_ids: list[UUID]
