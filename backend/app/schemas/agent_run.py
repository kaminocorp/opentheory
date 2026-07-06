"""Schemas for the ``AgentRun`` trace (0.12.0 reads; 0.12.3 adds the commission body).

``AgentRunSummary`` is the list-view row (no heavy JSON); ``AgentRunRead`` is the poll target — the
full trace including the ``plan`` and per-step ``steps``. Both are lenient reads
(``from_attributes=True``): the ``plan`` / ``steps`` JSON is passed through verbatim, never
re-validated on read (the write path already validated every step).

``AgentRunTrigger`` (0.12.3) is the only *write* schema here — the tiny body of the commission
``POST``. The *planner* schemas (``AgentPlan`` / ``PlannedRun``) that shape execution live with the
planner in ``app/agent/planner.py`` (0.12.1), not here.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import AgentRunStatus
from app.schemas.project import AGENT_ROLE_FIELDS


class AgentRunTrigger(BaseModel):
    """Body for ``POST /projects/{id}/threads/{thread_id}/agent-runs``: which role commissions it.

    ``role`` must be one of the four Research-crew roles (``AGENT_ROLE_FIELDS``), else ``422`` — the
    only *structural* gate on the commission. A role that is valid but has **no model assigned** is
    intentionally accepted here and becomes a recorded ``failed`` trace *inside* the pass
    (Decision #7), not a commission-time reject — so the human sees on the trace *why* nothing ran,
    rather than an opaque error at the button.
    """

    role: str = Field(description="One of the four Research-crew roles that commissions the pass.")

    @field_validator("role")
    @classmethod
    def _known_role(cls, value: str) -> str:
        if value not in AGENT_ROLE_FIELDS:
            raise ValueError(f"role must be one of: {', '.join(AGENT_ROLE_FIELDS)}")
        return value


class AgentRunSummary(BaseModel):
    """One agent-run row for the list view (newest first) — counts and status, no heavy JSON."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    thread_id: UUID
    branch_id: UUID | None
    agent_actor_id: UUID | None
    triggered_by_actor_id: UUID | None
    role: str
    model: str | None
    status: AgentRunStatus
    planned_count: int
    ran_count: int
    tokens_used: int
    error: str | None
    created_at: datetime
    updated_at: datetime


class AgentRunRead(AgentRunSummary):
    """The full trace (poll target): the summary plus the validated plan and per-step outcomes."""

    plan: dict[str, Any] = Field(default_factory=dict)
    steps: list[dict[str, Any]] = Field(default_factory=list)
