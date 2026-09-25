"""Schemas for the continuous research campaign (0.25.0 / 0.32.0).

``ResearchCampaignSummary`` is the list-view row; ``ResearchCampaignRead`` is the
poll target (summary + the per-cycle narrative). Both are lenient reads
(``from_attributes=True``): the cycles JSON is passed through, never re-validated
on read (the write path already shaped every entry).

``CampaignTrigger`` is the only *write* schema — the tiny body of the
commission ``POST``. ``role`` is the Research-crew role each cycle's
orchestration runs as. ``max_cycles`` is optional and clamped to the server
safety cap.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ResearchCampaignStatus
from app.schemas.project import AGENT_ROLE_FIELDS

CampaignStopReason = Literal[
    "budget_exhausted",
    "no_open_work",
    "max_cycles",
    "cancelled",
    "error_budget",
    "error",
]


class CampaignTrigger(BaseModel):
    """Body for ``POST /projects/{id}/campaigns``.

    Same structural gate as ``OrchestrationTrigger``: an unknown role is ``422``.
    A valid role with no model assigned is accepted here and becomes a recorded
    failed sub-pass *inside* a commissioned orchestration.
    """

    role: str = Field(description="One of the four Research-crew roles each cycle runs as.")
    max_cycles: int | None = Field(
        default=None,
        ge=1,
        le=64,
        description="Optional cycle cap for this campaign; clamped to the server safety cap.",
    )

    @field_validator("role")
    @classmethod
    def _known_role(cls, value: str) -> str:
        if value not in AGENT_ROLE_FIELDS:
            raise ValueError(f"role must be one of: {', '.join(AGENT_ROLE_FIELDS)}")
        return value


class ResearchCampaignSummary(BaseModel):
    """List-view row (newest first) — cycle counts, stop reason, budget remainder."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    triggered_by_actor_id: UUID | None
    role: str
    status: ResearchCampaignStatus
    stop_reason: str | None
    current_cycle: int
    cycles_completed: int
    consecutive_errors: int
    cancel_requested: bool
    budget_available_start: Decimal | None
    budget_available_end: Decimal | None
    max_cycles: int
    concurrency: int
    error_budget: int
    error: str | None
    created_at: datetime
    updated_at: datetime


class ResearchCampaignRead(ResearchCampaignSummary):
    """The poll target: the summary plus the per-cycle narrative."""

    cycles: list[dict[str, Any]] = Field(default_factory=list)
