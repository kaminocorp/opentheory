"""Project compute metering (0.19.0) — tokens → cost → an append-only ``ComputeDebit``.

Closes funding Decision #6 (historically sketched as deferred ``0.12.5``). The agent is a
**contributor**: this service never writes a ``FundingAllocation`` and never records a
``fund`` contribution. Spend is a separate ledger so funder ≠ contributor stays structural.

Helper writers ``db.add`` / ``flush`` and **never commit** — the orchestrator owns the
trace transaction this debit rides in.
"""

from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.openrouter_models import OPENROUTER_MODELS
from app.models.compute_debit import ComputeDebit
from app.models.enums import ComputeDebitKind

# Sub-cent quantum matching ``ComputeDebit.amount`` Numeric(12, 6).
_AMOUNT_QUANTUM = Decimal("0.000001")

# Stable error / skip reason the orchestrator and tests assert against.
BUDGET_EXHAUSTED = "project budget exhausted"
BUDGET_EXHAUSTED_REASON = "budget_exhausted"


def tokens_to_cost(tokens_used: int, rate_per_1k: Decimal) -> Decimal:
    """``tokens × rate / 1000``, quantized to the debit column.

    Zero or negative tokens cost nothing (and the writer will skip the row). The rate is
    taken as given — callers snapshot it from :func:`rate_for_model`.
    """
    if tokens_used <= 0 or rate_per_1k <= 0:
        return Decimal("0")
    raw = (Decimal(tokens_used) * rate_per_1k) / Decimal(1000)
    return raw.quantize(_AMOUNT_QUANTUM, rounding=ROUND_HALF_UP)


def rate_for_model(model: str | None) -> Decimal:
    """Per-1k USD rate for a model id, falling back to the settings default.

    A catalog entry may carry ``usd_per_1k``; most do not, on purpose — the operator
    default is one number (``agent_token_rate_usd_per_1k``), and a per-model override
    is metadata, not a second settings surface.
    """
    if model:
        for option in OPENROUTER_MODELS:
            if option.id == model and option.usd_per_1k is not None:
                return option.usd_per_1k
    return settings.agent_token_rate_usd_per_1k


class ProjectBudgetPolicy:
    """The ``BudgetPolicy`` implementer (0.19.0): keep going while this pass is still under budget.

    ``available`` is the project's remainder **before this pass's debit**. ``check``
    returns ``False`` once recorded tokens consume that remainder. No per-thread
    figure is ever consulted — the ceiling is the project. A future orchestrator
    can construct one of these per subagent with a slice of the same project pot.
    """

    def __init__(self, available: Decimal, *, rate_per_1k: Decimal) -> None:
        self.available = available
        self.rate_per_1k = rate_per_1k

    def check(self, *, tokens_used: int, ran_count: int) -> bool:
        del ran_count  # the ceiling is token spend, not run count (runs have their own safety cap)
        if self.available <= 0:
            return False
        return tokens_to_cost(tokens_used, self.rate_per_1k) < self.available


async def record_compute_debit(
    db: AsyncSession,
    *,
    project_id: UUID,
    agent_run_id: UUID,
    tokens_used: int,
    model: str | None,
    kind: ComputeDebitKind = ComputeDebitKind.PLANNING,
    notes: str | None = None,
) -> ComputeDebit | None:
    """Idempotently record this pass's spend. ``None`` when there is nothing to bill.

    Re-recording the same ``agent_run_id`` returns the existing row (the unique index
    is the durable guard; this read is the happy-path short-circuit). Does not commit.
    """
    if tokens_used <= 0:
        return None

    existing = await db.execute(
        select(ComputeDebit).where(ComputeDebit.agent_run_id == agent_run_id)
    )
    already = existing.scalar_one_or_none()
    if already is not None:
        return already

    rate = rate_for_model(model)
    amount = tokens_to_cost(tokens_used, rate)
    if amount <= 0:
        return None

    debit = ComputeDebit(
        project_id=project_id,
        agent_run_id=agent_run_id,
        tokens_used=tokens_used,
        amount=amount,
        currency="USD",
        model=model,
        rate_per_1k=rate,
        kind=kind,
        notes=notes,
    )
    db.add(debit)
    await db.flush()
    return debit


async def project_compute_spent(db: AsyncSession, project_id: UUID) -> Decimal:
    """Σ compute debits for the project (the number ``project_budget.spent`` uses)."""
    result = await db.execute(
        select(ComputeDebit.amount).where(ComputeDebit.project_id == project_id)
    )
    total = Decimal("0")
    for (amount,) in result.all():
        total += Decimal(amount)
    return total
