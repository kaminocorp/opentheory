"""AgentRun — the human-visible trace of one thin-agent pass (0.12.x).

One row per commissioned pass: who triggered it, which agent Actor authored the work, the resolved
role + model, the validated plan, and the per-step outcome (what landed on the ledger, what failed,
what was dropped as unrunnable). Two deliberate design notes:

- **NOT append-only.** ``AgentRun`` is a live, mutable trace (``running`` → ``completed`` |
  ``failed``), so it is intentionally absent from ``models/append_only.py``. The *ledger writes* a
  pass triggers (checkpoints, evidence) are append-only through the chokepoint; the trace that
  narrates them is not a ledger primitive and must be updatable as steps complete. Do **not** wire
  it into the append-only guards "for consistency".

- **Provenance index for agent branches (Decision #2).** A ``Branch`` row carries no author, so
  *"which branches are agent branches?"* is answered by joining ``agent_runs`` → ``branches`` on
  ``branch_id`` (``branches.status = 'open'``). The trace table earns this second job for free.

Nullability follows the settled background-execution model (Decision #7): the row is minted
``running`` at commission time (request session) when only the commissioning human
(``triggered_by_actor_id``) and ``role`` are known. The agent Actor and the resolved ``model`` are
looked up *inside* the background pass and stamped then — so ``agent_actor_id`` and ``model`` are
**nullable** (a pass that fails before resolving them, e.g. an unassigned role, keeps them null).

Step JSON shape (each entry in ``steps``)::

    {"index": int, "instrument": str, "inputs": dict,
     "claim_id": str | None, "relation_kind": str | None, "rationale": str,
     "status": "landed" | "failed" | "dropped_invalid",
     "checkpoint_id": str | None, "evidence_id": str | None,
     "outcome": str | None, "error": str | None, "reason": str | None}
"""

from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import AgentRunStatus


class AgentRun(IdMixin, TimestampMixin, Base):
    __tablename__ = "agent_runs"

    project_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The commissioned thread. CASCADE with its project (a pass has no meaning without its thread).
    thread_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("threads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The agent line this pass worked on; NULL = the main-line fallback (thread had no checkpoint to
    # fork from). SET NULL on branch delete keeps the trace while detaching it.
    branch_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="SET NULL"),
        nullable=True,
    )
    # The authoring agent Actor — nullable because it is resolved *inside* the pass (Decision #7),
    # not known when the row is minted at commission. SET NULL so removing an actor never deletes
    # the trace.
    agent_actor_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("actors.id", ondelete="SET NULL"),
        nullable=True,
    )
    # The commissioning human — known at commission, so NOT NULL. SET NULL preserves the trace if
    # the actor is later removed.
    triggered_by_actor_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("actors.id", ondelete="SET NULL"),
        nullable=False,
    )
    # One of AGENT_ROLE_FIELDS (research_lead / thread_manager / researcher / research_assistant) —
    # a plain string (validated in the schema/route layer), like Contribution.action.
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    # The resolved OpenRouter model id — nullable until resolved from project.agent_models[role]
    # inside the pass (null when the role is unassigned → failed trace).
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[AgentRunStatus] = mapped_column(
        Enum(AgentRunStatus, name="agent_run_status"),
        default=AgentRunStatus.RUNNING,
        nullable=False,
    )
    # The raw validated AgentPlan (the model's proposed runs after two-stage validation).
    plan: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    # Per-step trace (see the module docstring for the shape) — the live, human-readable narrative.
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    # Steps the model proposed (the raw proposal size — differs from the runnable count when steps
    # are dropped as unrunnable or truncated to the safety cap).
    planned_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Steps that reached run_instrument (landed or failed at execution).
    ran_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Planning-call token usage (future: cumulative across an iterative loop).
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 0.16.1 — what the pass *bought*: the before/after grounding rung of every open claim it could
    # have moved (see app/schemas/agent_run.py::PassYield for the shape). Measured point-in-time at
    # both ends of the pass rather than derived on read, so a human raising a rung later is never
    # credited to the agent. Empty ``{}`` on a pass that failed before executing anything.
    grounding_yield: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    # Pass-level failure reason (unassigned role, planner error, unexpected exception) — null on
    # the success path.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    project = relationship("Project")
    thread = relationship("Thread")
    branch = relationship("Branch")
    agent_actor = relationship("Actor", foreign_keys=[agent_actor_id])
    triggered_by = relationship("Actor", foreign_keys=[triggered_by_actor_id])
