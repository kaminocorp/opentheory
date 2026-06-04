from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ThreadStage, ThreadStatus


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
