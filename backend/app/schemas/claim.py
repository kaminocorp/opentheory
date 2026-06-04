from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ClaimKind, ClaimStatus


class ClaimBase(BaseModel):
    kind: ClaimKind
    status: ClaimStatus = ClaimStatus.PROPOSED
    statement: str = Field(min_length=1)
    rationale: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    claim_metadata: dict[str, Any] = Field(default_factory=dict)


class ClaimCreate(ClaimBase):
    """Create payload. ``thread_id`` (and the derived ``project_id``) come from the path."""


class ClaimRead(ClaimBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    thread_id: UUID | None
    created_at: datetime
    updated_at: datetime
