from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import BranchStatus
from app.schemas.checkpoint import CheckpointRead


class BranchCreate(BaseModel):
    """Fork a new line of exploration from an existing checkpoint.

    ``project_id`` comes from the path; ``actor_id`` from the ``X-Dev-Actor-Id`` header.
    ``from_checkpoint_id`` is the fork point (validated in-project in the service layer).
    ``thread_id`` optionally scopes the branch to a thread.
    """

    from_checkpoint_id: UUID
    name: str = Field(min_length=1, max_length=160)
    reason: str | None = None
    thread_id: UUID | None = None


class BranchClose(BaseModel):
    """Close a branch. ``outcome`` is the terminal status; ``reason`` is preserved.

    Only the two *closing* outcomes are accepted (``dead_end`` = abandoned, ``closed`` =
    superseded). ``merged`` is reserved for a future release and is not a close outcome.
    """

    outcome: Literal["dead_end", "closed"]
    reason: str | None = None


class BranchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    thread_id: UUID | None
    forked_from_checkpoint_id: UUID | None
    name: str
    reason: str | None
    status: BranchStatus
    created_at: datetime
    updated_at: datetime


class BranchSummary(BranchRead):
    """Branch list row carrying the count of checkpoints recorded on it (0.4.4)."""

    checkpoint_count: int = 0


class BranchDetail(BranchRead):
    """Branch detail read: the branch plus the checkpoints recorded on it (newest first)."""

    checkpoints: list[CheckpointRead] = Field(default_factory=list)
