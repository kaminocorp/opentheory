from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ValidationOutcome
from app.schemas.checkpoint import ActorSummary


class ValidationCreate(BaseModel):
    """Create payload for a validation.

    ``project_id`` comes from the path and ``actor_id`` from the ``X-Dev-Actor-Id``
    header. The target is polymorphic: ``target_type`` is one of ``claim`` /
    ``checkpoint`` / ``branch`` / ``artifact`` (validated in the service layer against
    ``VALIDATION_TARGET_TYPES``) and ``target_id`` is the row it assesses. The service
    maps the pair onto the matching typed FK column on ``Validation``.
    """

    target_type: str = Field(min_length=1, max_length=20)
    target_id: UUID
    outcome: ValidationOutcome
    notes: str | None = None


class ValidationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    actor_id: UUID | None
    # The acting actor, resolved for provenance display (mirrors CheckpointRead).
    actor: ActorSummary | None = None
    # Target derived from whichever typed FK is set; None only if the target was removed.
    target_type: str | None
    target_id: UUID | None
    outcome: ValidationOutcome
    notes: str | None
    # The checkpoint this validation was recorded through (Decision #1): resolved from
    # the ``recorded``-role checkpoint_refs row, not the ``Validation.checkpoint_id``
    # column (which, when set, is instead the *target* checkpoint being validated).
    recording_checkpoint_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
