"""Semantic research-git diff — a derived read of what moved between two tips (0.29.0).

Not a blob dump and not an LLM summary. Same two resolved tips always serialize
the same structured delta. This is a *read model*: it mints nothing.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.claim import ClaimSignal, GroundingHeadline

RefKind = Literal["checkpoint", "branch", "tag", "main"]
ClaimChange = Literal["added", "removed", "status_changed"]
GroundingMovement = Literal["raised", "settled", "unchanged"]
InstrumentStatus = Literal["result", "refuted", "undecided"]


class ResolvedRef(BaseModel):
    """How a client-supplied ``from`` / ``to`` token resolved onto the ledger."""

    model_config = ConfigDict(from_attributes=True)

    input: str
    kind: RefKind
    checkpoint_id: UUID
    branch_id: UUID | None = None
    tag_id: UUID | None = None
    label: str


class ClaimDelta(BaseModel):
    """A claim that appeared, disappeared from a line, or whose validation signal moved.

    ``from_signal`` / ``to_signal`` are the derived display signal (0.4.4), not the
    stored ``Claim.status`` — the API never rewrites that field. ``None`` means the
    claim is not present at that tip.
    """

    claim_id: UUID
    statement: str
    change: ClaimChange
    from_signal: ClaimSignal | None = None
    to_signal: ClaimSignal | None = None


class GroundingMove(BaseModel):
    """One claim's evidence-axis headline at ``from`` vs ``to`` (0.16.x yield)."""

    claim_id: UUID
    statement: str
    from_headline: GroundingHeadline
    to_headline: GroundingHeadline
    movement: GroundingMovement


class InstrumentOutcome(BaseModel):
    """A toolbench result minted on a checkpoint in the directed interval ``from..to``."""

    checkpoint_id: UUID
    instrument: str
    status: InstrumentStatus
    claim_ids: list[UUID] = Field(default_factory=list)
    summary: str


class Ancestry(BaseModel):
    """Graph facts about the two tips — merge-base and exclusive sides.

    ``interval_checkpoint_ids`` is ``git log from..to``: ancestors of ``to`` that are
    not ancestors of ``from`` (includes ``to``, excludes ``from`` when ``from`` is an
    ancestor). Sorted by ``(created_at, id)`` for a stable payload.
    """

    from_is_ancestor_of_to: bool
    to_is_ancestor_of_from: bool
    diverged: bool
    merge_base_id: UUID | None = None
    interval_checkpoint_ids: list[UUID] = Field(default_factory=list)
    from_only_checkpoint_ids: list[UUID] = Field(default_factory=list)
    to_only_checkpoint_ids: list[UUID] = Field(default_factory=list)


class SemanticDiffRead(BaseModel):
    """Structured research-space delta between two resolved tips."""

    project_id: UUID
    from_ref: ResolvedRef
    to_ref: ResolvedRef
    empty: bool
    claims: list[ClaimDelta] = Field(default_factory=list)
    grounding: list[GroundingMove] = Field(default_factory=list)
    instruments: list[InstrumentOutcome] = Field(default_factory=list)
    ancestry: Ancestry

