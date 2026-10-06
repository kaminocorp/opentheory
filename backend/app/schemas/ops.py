"""Perpetual ops dashboard — derived ledger read (0.49.0 / 0.50.0).

Public GET. Mints nothing. Every number is on the append-only
``ComputeDebit`` / funding ledgers or is a setting this API process
can see. Anything else is labeled unknown.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ActorType
from app.schemas.funding import ProjectBudget

BudgetState = Literal["unfunded", "available", "exhausted"]
ProcessIntSource = Literal["default", "process_env", "invalid"]
HarnessRowKind = Literal["spend", "hold", "release"]
HoldStatus = Literal["open", "released"]
UnknownFlag = Literal["unknown"]


class OpsBudgetRead(BaseModel):
    """Project pot plus the honesty flag unfunded ≠ exhausted."""

    snapshot: ProjectBudget
    state: BudgetState
    note: str


class OpsDailyCapRead(BaseModel):
    """Today's harness token sum against the cap this API process sees."""

    utc_day: str
    cap: int | None
    cap_source: ProcessIntSource
    tokens_used_today: int
    remaining: int | None
    exhausted: bool | None
    hold_ttl_seconds: int | None
    hold_ttl_source: ProcessIntSource
    note: str


class OpsHoldRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hold_id: UUID | None
    status: HoldStatus
    tokens: int
    created_at: datetime
    released_at: datetime | None
    stale: bool | None
    note: str | None = None


class OpsTurnRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    tokens_used: int
    amount: Decimal
    notes: str | None
    kind: HarnessRowKind
    hold_id: UUID | None
    clamp: int | None = None
    overshoot: int | None = None
    price_known: bool | None = None
    pot_room: int | None = None
    actor_id: UUID | None = None
    actor_display_name: str | None = None
    actor_type: ActorType | None = None


class OpsLastTurnRead(BaseModel):
    """Newest billed harness spend, with the 0.50.0 clamp if notes carry it."""

    tokens_used: int
    clamp: int | None
    overshoot: int | None
    price_known: bool | None
    pot_room: int | None = None
    note: str
    actor_id: UUID | None = None
    actor_display_name: str | None = None
    actor_type: ActorType | None = None


class OpsActorSpendRead(BaseModel):
    """Billed harness spend grouped by ``ComputeDebit.actor_id`` (0.57.0 / 0.58.0)."""

    actor_id: UUID | None = None
    actor_display_name: str | None = None
    actor_type: ActorType | None = None
    tokens_used: int
    amount: Decimal
    turn_count: int
    token_budget_cap: int | None = None
    usd_budget_cap: Decimal | None = None
    token_cap_reached: bool | None = None
    usd_cap_reached: bool | None = None


class OpsRefusalsRead(BaseModel):
    recorded: Literal[False] = False
    note: str


class OpsLoopRead(BaseModel):
    enabled: bool
    source: Literal["settings.agent_loop_enabled"] = "settings.agent_loop_enabled"


class OpsUnknownProcessRead(BaseModel):
    enabled: UnknownFlag = "unknown"
    note: str


class OpsEnablementRead(BaseModel):
    loop: OpsLoopRead
    gateway: OpsUnknownProcessRead
    mcp_child: OpsUnknownProcessRead


class ProjectOpsRead(BaseModel):
    """Read-only operator snapshot. Same project → same derived facts."""

    project_id: UUID
    as_of: datetime
    notes_prefix: str
    budget: OpsBudgetRead
    daily_cap: OpsDailyCapRead
    holds: list[OpsHoldRead] = Field(default_factory=list)
    recent_turns: list[OpsTurnRead] = Field(default_factory=list)
    last_turn: OpsLastTurnRead | None = None
    spend_by_agent: list[OpsActorSpendRead] = Field(default_factory=list)
    refusals: OpsRefusalsRead
    enablement: OpsEnablementRead
