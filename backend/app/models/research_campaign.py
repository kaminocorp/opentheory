"""ResearchCampaign — the persistent outer loop over 0.22.0 orchestrations (0.25.0).

One row per commissioned continuous run: which orchestration each cycle produced,
why the campaign stopped (budget, no raisable work, max cycles, cancel, error
budget), and how much project budget remained. Two deliberate design notes:

- **NOT append-only.** Like ``AgentRun`` / ``OrchestrationRun``, this is a live
  mutable trace (``running`` → ``completed`` | ``failed``). The *ledger writes*
  a commissioned cycle triggers stay append-only through
  ``run_orchestration`` → ``run_agent_pass`` → ``run_instrument``. Do **not**
  wire this table into ``models/append_only.py``.

- **Contributor infrastructure, never a validator.** The row records what the
  loop *attempted*. It never writes a ``Validation`` or a ``FundingAllocation``,
  and it never auto-merges. Funder ≠ contributor ≠ validator stays structural.

Cycle JSON shape (each entry in ``cycles``)::

    {"cycle": int,
     "orchestration_id": str | None,
     "orchestration_status": str | None,
     "stop_reason": str | None,
     "passes_commissioned": int | None,
     "passes_completed": int | None,
     "passes_failed": int | None,
     "budget_remaining": str | None,
     "error": str | None}

Campaign ``stop_reason`` values: ``budget_exhausted``, ``no_open_work``,
``max_cycles``, ``cancelled``, ``error_budget``, ``error``. Null while
``running``.
"""

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import ResearchCampaignStatus


class ResearchCampaign(IdMixin, TimestampMixin, Base):
    __tablename__ = "research_campaigns"

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
    # One of AGENT_ROLE_FIELDS — the role each commissioned orchestration runs as.
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[ResearchCampaignStatus] = mapped_column(
        Enum(ResearchCampaignStatus, name="research_campaign_status"),
        default=ResearchCampaignStatus.RUNNING,
        nullable=False,
    )
    # Per-cycle narrative (see the module docstring). Reassign on every update —
    # the column is plain JSON, so an in-place ``.append`` is invisible to SQLAlchemy.
    cycles: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    # Why the campaign stopped. Null while ``running``.
    stop_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # 0 until the first cycle starts; then 1-based.
    current_cycle: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cycles_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consecutive_errors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Human-requested stop; the loop honours it between cycles (current cycle finishes).
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Snapshot of ``project_budget.available`` at start / after the last cycle.
    budget_available_start: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    budget_available_end: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    # Bounds this run used (copied from settings so a later default change never
    # rewrites history).
    max_cycles: Mapped[int] = mapped_column(Integer, nullable=False)
    error_budget: Mapped[int] = mapped_column(Integer, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    project = relationship("Project", back_populates="research_campaigns")
    triggered_by = relationship("Actor")
