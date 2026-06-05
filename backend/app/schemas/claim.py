from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ClaimKind, ClaimStatus
from app.schemas.validation import ValidationRead

# Derived display signal for a claim (0.4.4, plan Decision #5). Computed from validation
# history; it does NOT mutate the stored ``Claim.status`` — confidence stays explainable.
#   contested  — has an unretracted contradicts/failed validation
#   validated  — has a passing validation and is not contested
#   none       — no decisive signal yet
ClaimSignal = Literal["none", "contested", "validated"]


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
    # Enriched (0.4.4): the claim's validation history (oldest first) and the derived
    # signal. Constructed explicitly in the service — never via from_attributes on the
    # ORM (which would lazy-load the ``Claim.validations`` relationship).
    validations: list[ValidationRead] = Field(default_factory=list)
    signal: ClaimSignal = "none"
