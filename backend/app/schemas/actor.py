from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ActorType


class ActorBase(BaseModel):
    type: ActorType
    display_name: str = Field(min_length=1, max_length=200)
    external_id: str | None = Field(default=None, max_length=255)
    actor_metadata: dict[str, Any] = Field(default_factory=dict)


class ActorCreate(ActorBase):
    pass


class ActorRead(ActorBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
