from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ActorType
from app.schemas.account import AccountRead


class ActorBase(BaseModel):
    type: ActorType
    display_name: str = Field(min_length=1, max_length=200)
    actor_metadata: dict[str, Any] = Field(default_factory=dict)


class ActorCreate(ActorBase):
    # Dev/test bootstrap (behind auth_dev_header_enabled). Real actors are JIT-provisioned with
    # their Account on first sign-in (api/deps.py); external_id + roles moved to AccountCreate.
    # `account_id` optionally links a bootstrap actor to an Account made via POST /accounts.
    account_id: UUID | None = None


class ActorRead(ActorBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class MeRead(ActorRead):
    """The ``/me`` response: the resolved acting ``Actor`` plus its owning ``Account``
    (eager-loaded in ``api/deps.py``). ``/me`` is authenticated, so the caller sees the full
    ``AccountRead`` (email/roles) for **their own** principal only — never anyone else's."""

    account: AccountRead | None = None
