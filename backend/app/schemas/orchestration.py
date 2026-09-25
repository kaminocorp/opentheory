"""Schemas for the project-level orchestration trace (0.22.0).

``OrchestrationRunSummary`` is the list-view row; ``OrchestrationRunRead`` is the
poll target (summary + the per-thread ``decisions``). Both are lenient reads
(``from_attributes=True``): the decisions JSON is passed through, never re-validated
on read (the write path already shaped every entry).

``OrchestrationTrigger`` is the only *write* schema — the tiny body of the
commission ``POST``. ``role`` is the Research-crew role each sub-pass runs as.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import OrchestrationRunStatus
from app.schemas.project import AGENT_ROLE_FIELDS

OrchestrationStopReason = Literal[
    "budget_exhausted", "no_open_work", "max_passes", "cancelled", "error"
]
OrchestrationDecisionAction = Literal["commissioned", "skipped"]


class OrchestrationTrigger(BaseModel):
    """Body for ``POST /projects/{id}/orchestrations``: which role commissions each pass.

    Same structural gate as ``AgentRunTrigger``: an unknown role is ``422``. A valid
    role with no model assigned is accepted here and becomes a recorded ``failed``
    sub-pass *inside* the loop — the human sees why on the decision row.
    """

    role: str = Field(description="One of the four Research-crew roles each sub-pass runs as.")

    @field_validator("role")
    @classmethod
    def _known_role(cls, value: str) -> str:
        if value not in AGENT_ROLE_FIELDS:
            raise ValueError(f"role must be one of: {', '.join(AGENT_ROLE_FIELDS)}")
        return value


class OrchestrationDecision(BaseModel):
    """One thread's fate inside an orchestration — commissioned or skipped, and why."""

    thread_id: UUID
    thread_title: str | None = None
    action: OrchestrationDecisionAction
    reason: str | None = None
    agent_run_id: UUID | None = None
    agent_run_status: str | None = None
    tokens_used: int | None = None
    ran_count: int | None = None
    budget_remaining: Decimal | None = None
    wave: int | None = None
    parallel_with: list[UUID] = Field(default_factory=list)


class OrchestrationRunSummary(BaseModel):
    """List-view row (newest first) — counts, stop reason, budget remainder. No decisions."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    triggered_by_actor_id: UUID | None
    role: str
    status: OrchestrationRunStatus
    stop_reason: str | None
    passes_commissioned: int
    passes_completed: int
    passes_failed: int
    passes_skipped: int
    budget_available_start: Decimal | None
    budget_available_end: Decimal | None
    max_passes: int
    concurrency: int = 1
    cancel_requested: bool = False
    error: str | None
    created_at: datetime
    updated_at: datetime


class OrchestrationRunRead(OrchestrationRunSummary):
    """The poll target: the summary plus the per-thread decision narrative."""

    decisions: list[dict[str, Any]] = Field(default_factory=list)
