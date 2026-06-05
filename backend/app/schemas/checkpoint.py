from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ActorType, ThreadStage

# Allowed checkpoint-ref target types and role length. Stored as plain VARCHAR and
# validated in the service layer (CHECKPOINT_TARGET_TYPES); promotion to a Postgres
# enum is deferred until the vocabulary stabilises (see plan cross-cutting "Enums").


class ActorSummary(BaseModel):
    """Minimal actor identity for provenance display (0.3.4)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    display_name: str
    type: ActorType


class CheckpointRefInput(BaseModel):
    """A single reference from a checkpoint to a primitive it acted on."""

    target_type: str = Field(min_length=1, max_length=20)
    target_id: UUID
    role: str = Field(min_length=1, max_length=40)


class CheckpointRefRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    target_type: str
    target_id: UUID
    role: str
    # Human label for the referenced primitive (claim statement, evidence/thread title,
    # artifact name), resolved server-side in 0.3.4. None if the target is gone.
    label: str | None = None


class CheckpointCreate(BaseModel):
    """Create payload. ``project_id`` comes from the path; ``author_id`` from the header.

    ``content`` is free-form JSON authored by the user. ``stage`` is optional metadata.
    ``parent_ids`` link earlier checkpoints; ``refs`` record the primitives this
    checkpoint acted on.
    """

    thread_id: UUID | None = None
    # The branch this checkpoint is recorded on (0.4.2). None = the project main line; a
    # value must reference an open branch in this project (validated in the service layer).
    branch_id: UUID | None = None
    summary: str = Field(min_length=1)
    stage: ThreadStage | None = None
    content: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None
    parent_ids: list[UUID] = Field(default_factory=list)
    refs: list[CheckpointRefInput] = Field(default_factory=list)


class CheckpointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    thread_id: UUID | None
    branch_id: UUID | None
    author_id: UUID | None
    # Enriched provenance (0.3.4): the creating actor and the kind of contribution this
    # checkpoint recorded. None if the author actor was removed.
    author: ActorSummary | None = None
    contribution_kind: str | None = None
    stage: ThreadStage | None
    summary: str
    content: dict[str, Any]
    notes: str | None
    parent_ids: list[UUID]
    refs: list[CheckpointRefRead]
    created_at: datetime
    updated_at: datetime
