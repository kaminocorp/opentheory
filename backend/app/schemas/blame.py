"""Semantic research-git blame — a derived read of who produced a claim (0.36.0).

Not an instrument and not a write. Same claim always serializes the same ordered
chain of checkpoints, actors, and tool invocations that produced or evidence-grounded
it. This is a *read model*: it mints nothing.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ActorType, ThreadStage
from app.schemas.claim import ClaimSignal, GroundingHeadline
from app.schemas.diff import InstrumentStatus


class BlameActor(BaseModel):
    """Author of a checkpoint on the claim's chain — an Actor, never an Account."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    display_name: str
    type: ActorType


class BlameInstrument(BaseModel):
    """A well-formed tool-invocation on a chain checkpoint.

    Status stays ``result | refuted | undecided``. Blame lists these; it does not
    invent a fourth outcome and it is not itself an instrument.
    """

    instrument: str
    status: InstrumentStatus
    instrument_version: str | None = None
    engine: str | None = None
    engine_version: str | None = None


class BlameAgentRun(BaseModel):
    """Optional pass that landed this checkpoint (joined from ``AgentRun.steps``)."""

    id: UUID
    role: str
    model: str | None = None
    status: str


class BlameStep(BaseModel):
    """One checkpoint that touched the claim, in ledger order.

    ``roles`` are how it touched the claim (checkpoint-ref roles, plus ``instrument``
    when a well-formed blame tuple is present). ``signal_after`` / ``grounding_after``
    are reconstructed from this checkpoint's ancestor closure — the same tip math
    as semantic diff (0.29.0). Movement flags compare that snapshot to the state
    just before this commit (ancestors minus self).
    """

    checkpoint_id: UUID
    created_at: datetime
    summary: str
    stage: ThreadStage | None = None
    branch_id: UUID | None = None
    parent_ids: list[UUID] = Field(default_factory=list)
    author: BlameActor | None = None
    contribution_kind: str | None = None
    roles: list[str] = Field(default_factory=list)
    instruments: list[BlameInstrument] = Field(default_factory=list)
    agent_run: BlameAgentRun | None = None
    signal_after: ClaimSignal
    grounding_after: GroundingHeadline
    signal_moved: bool = False
    grounding_moved: bool = False
    from_signal: ClaimSignal | None = None
    from_grounding: GroundingHeadline | None = None


class ClaimBlameRead(BaseModel):
    """Ordered production / grounding chain for one claim in a project."""

    project_id: UUID
    claim_id: UUID
    statement: str
    thread_id: UUID | None = None
    empty: bool
    current_signal: ClaimSignal
    current_grounding: GroundingHeadline
    chain: list[BlameStep] = Field(default_factory=list)
    checkpoint_ids: list[UUID] = Field(default_factory=list)
