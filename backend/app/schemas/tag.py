from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import TagKind
from app.schemas.checkpoint import ActorSummary


class TagCreate(BaseModel):
    """Pin a named, immutable pointer at an existing in-project checkpoint.

    ``project_id`` comes from the path; ``author_id`` from the acting actor.
    ``name`` is unique per project — a collision is ``409``, never a silent retarget.
    """

    checkpoint_id: UUID
    name: str = Field(min_length=1, max_length=80)
    kind: TagKind
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped


class TagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    checkpoint_id: UUID
    author_id: UUID | None
    author: ActorSummary | None = None
    name: str
    kind: TagKind
    notes: str | None
    recording_checkpoint_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
