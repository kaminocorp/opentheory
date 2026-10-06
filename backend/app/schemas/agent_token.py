from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentTokenMintRequest(BaseModel):
    """Optional shorter-than-max TTL. Default is 30 days, capped by settings."""

    ttl_seconds: int | None = Field(default=None, ge=1)


class AgentTokenMintRead(BaseModel):
    """Compact JWT is returned once. Hash stays at rest."""

    model_config = ConfigDict(from_attributes=True)

    token: str
    jti: UUID
    expires_at: datetime
