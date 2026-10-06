"""Project agent roster reads and lifecycle writes (0.57.0 / 0.58.0).

Members-only list. Deploy / suspend / revoke are OWNER or ADMIN.
Resume is OWNER only. Caps are lifetime per roster seat; null = none.
Never email, never token hash, never the compact JWT.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import ProjectAgentRole, ProjectAgentStatus
from app.schemas.account import AccountSummary


class AgentLiveTokenRead(BaseModel):
    """Metadata for a still-live session token. Bearer is never included."""

    model_config = ConfigDict(from_attributes=True)

    jti: UUID
    expires_at: datetime
    last_used_at: datetime | None = None


class AgentRosterRead(BaseModel):
    """One deployed agent on a project, including revoked rows."""

    model_config = ConfigDict(from_attributes=True)

    actor_id: UUID
    display_name: str
    status: ProjectAgentStatus
    role: ProjectAgentRole
    deployed_by: AccountSummary | None = None
    responsible: AccountSummary | None = None
    token_budget_cap: int | None = None
    usd_budget_cap: Decimal | None = None
    last_used_at: datetime | None = None
    tokens_used: int = 0
    amount: Decimal = Decimal("0")
    token_cap_reached: bool = False
    usd_cap_reached: bool = False
    live_tokens: list[AgentLiveTokenRead] = Field(default_factory=list)
    created_at: datetime


class AgentDeployRequest(BaseModel):
    """Deploy a named agent, or roster the migrated Research crew."""

    display_name: str = Field(min_length=1, max_length=200)
    token_budget_cap: int | None = Field(default=None, ge=1)
    usd_budget_cap: Decimal | None = Field(default=None, ge=0)
    reuse_research_crew: bool = False


class AgentRosterPatch(BaseModel):
    """Lifecycle and/or cap edit. ``active`` is resume (OWNER only)."""

    status: ProjectAgentStatus | None = None
    token_budget_cap: int | None = None
    usd_budget_cap: Decimal | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> AgentRosterPatch:
        if not self.model_fields_set:
            raise ValueError("nothing to update")
        if "token_budget_cap" in self.model_fields_set and self.token_budget_cap is not None:
            if self.token_budget_cap < 1:
                raise ValueError("token_budget_cap must be >= 1")
        if "usd_budget_cap" in self.model_fields_set and self.usd_budget_cap is not None:
            if self.usd_budget_cap < 0:
                raise ValueError("usd_budget_cap must be >= 0")
        return self
