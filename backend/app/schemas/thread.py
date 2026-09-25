from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ThreadStage, ThreadStatus
from app.schemas.claim import GroundingRollup


class ThreadBase(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    question: str = Field(min_length=1)
    stage: ThreadStage = ThreadStage.DECOMPOSE
    status: ThreadStatus = ThreadStatus.OPEN
    thread_metadata: dict[str, Any] = Field(default_factory=dict)


class ThreadCreate(ThreadBase):
    """Create payload. ``project_id`` is taken from the path, not the body."""


class ThreadRead(ThreadBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    created_at: datetime
    updated_at: datetime


class ThreadSummary(ThreadRead):
    """Thread plus its claim count (0.3.4) and grounding rollup (0.16.3)."""

    claim_count: int
    # Derived from each claim's ``ClaimGrounding.headline`` — same derivation as the claim row,
    # aggregated. Empty when the thread has no claims.
    grounding_rollup: GroundingRollup = Field(default_factory=GroundingRollup)
