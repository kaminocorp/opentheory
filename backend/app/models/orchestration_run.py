"""OrchestrationRun — the human-visible trace of one project-level research loop (0.22.0).

One row per commissioned orchestration: which threads were selected, which were skipped
and why, which ``AgentRun`` each commissioned pass produced, and why the loop stopped
(budget exhausted, no raisable work, max-passes cap). Two deliberate design notes:

- **NOT append-only.** Like ``AgentRun``, this is a live mutable trace
  (``running`` → ``completed`` | ``failed``). The *ledger writes* a commissioned pass
  triggers stay append-only through ``run_agent_pass`` → ``run_instrument``. Do **not**
  wire this table into ``models/append_only.py``.

- **Contributor infrastructure, never a validator.** The row records what the loop
  *attempted*. It never writes a ``Validation`` or a ``FundingAllocation``. Funder ≠
  contributor ≠ validator stays structural.

Decision JSON shape (each entry in ``decisions``)::

    {"thread_id": str, "thread_title": str | None,
     "action": "commissioned" | "skipped",
     "reason": str | None,
     "agent_run_id": str | None, "agent_run_status": str | None,
     "tokens_used": int | None, "ran_count": int | None,
     "budget_remaining": str | None}

``status="skipped"`` reasons include ``no_open_claims``, ``no_raisable_claims``,
``thread_not_open``, ``pass_in_flight``, ``already_commissioned``,
``budget_exhausted``, ``max_passes``. A commissioned row's ``reason`` is the
sub-pass terminal (``completed``, ``failed``, ``budget_exhausted``).
"""

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import OrchestrationRunStatus


class OrchestrationRun(IdMixin, TimestampMixin, Base):
    __tablename__ = "orchestration_runs"

    project_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The commissioning human — known at commission, so NOT NULL. SET NULL preserves
    # the trace if the actor is later removed.
    triggered_by_actor_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("actors.id", ondelete="SET NULL"),
        nullable=False,
    )
    # One of AGENT_ROLE_FIELDS — the role each commissioned sub-pass runs as.
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[OrchestrationRunStatus] = mapped_column(
        Enum(OrchestrationRunStatus, name="orchestration_run_status"),
        default=OrchestrationRunStatus.RUNNING,
        nullable=False,
    )
    # Per-thread decisions (see the module docstring). Reassign on every update —
    # the column is plain JSON, so an in-place ``.append`` is invisible to SQLAlchemy.
    decisions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    # Why the loop stopped: budget_exhausted | no_open_work | max_passes | error.
    # Null while ``running``.
    stop_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    passes_commissioned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    passes_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    passes_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    passes_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Snapshot of ``project_budget.available`` at start / after the last decision.
    budget_available_start: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    budget_available_end: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    # The bound this run used (copied from settings so a later default change never
    # rewrites history).
    max_passes: Mapped[int] = mapped_column(Integer, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    project = relationship("Project", back_populates="orchestration_runs")
    triggered_by = relationship("Actor")
