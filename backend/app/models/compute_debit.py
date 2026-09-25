"""ComputeDebit — append-only project compute spend (0.19.0).

Agent passes debit the project's funded budget from recorded ``AgentRun.tokens_used``.
This is **not** a ``FundingAllocation``: the agent is a contributor, never a funder.
Funding grants budget (attributed to an ``Account``); this ledger records what the
loop spent against that budget. ``project_budget.spent`` is Σ these rows.

One debit per pass (partial unique on ``agent_run_id``). A planner call that spent
tokens and then failed still records the debit — the provider billed it. A refused
start (available already ≤ 0) writes nothing: no tokens moved.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin
from app.models.enums import ComputeDebitKind


class ComputeDebit(IdMixin, TimestampMixin, Base):
    __tablename__ = "compute_debits"
    # One debit per pass: two concurrent finalize paths cannot double-bill the same AgentRun.
    # Mirrored by migration 0015 so create_all and Alembic stay in lockstep.
    __table_args__ = (
        Index(
            "uq_compute_debits_one_per_agent_run",
            "agent_run_id",
            unique=True,
            postgresql_where=text("agent_run_id IS NOT NULL"),
        ),
    )

    project_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The pass that incurred the spend. SET NULL keeps the debit if a trace is later removed;
    # the unique index (migration + ``__table_args__``) is partial on non-null so a debit
    # without a run (not used in v1) would still be legal.
    agent_run_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False)
    # Sub-cent precision: a short planning call at the default rate is well below $0.01.
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Snapshot of the per-1k rate used so a later rate change never rewrites history.
    rate_per_1k: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    kind: Mapped[ComputeDebitKind] = mapped_column(
        Enum(ComputeDebitKind, name="compute_debit_kind"),
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text)

    project = relationship("Project", back_populates="compute_debits")
    agent_run = relationship("AgentRun")
