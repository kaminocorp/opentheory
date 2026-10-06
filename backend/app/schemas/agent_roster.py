"""Project agent roster reads and lifecycle writes (0.57.0).

Members-only list. Deploy / suspend / revoke are OWNER or ADMIN.
Resume is OWNER only. Caps are stored, not enforced (slice F).
Never email, never token hash, never the compact JWT.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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
    live_tokens: list[AgentLiveTokenRead] = Field(default_factory=list)
    created_at: datetime


class AgentDeployRequest(BaseModel):
    """Deploy a named agent, or roster the migrated Research crew."""

    display_name: str = Field(min_length=1, max_length=200)
    token_budget_cap: int | None = Field(default=None, ge=1)
    usd_budget_cap: Decimal | None = Field(default=None, ge=0)
    reuse_research_crew: bool = False


class AgentRosterPatch(BaseModel):
    """Lifecycle change. ``active`` is resume (OWNER only)."""

    status: ProjectAgentStatus
