"""Funding service — the ``FundingAllocation`` write path (0.6.3).

A funding event is **contribution-only** (Decision #3): it writes a ``FundingAllocation`` row
and one ``fund`` ``Contribution`` (with ``funding_allocation_id`` set, ``checkpoint_id=None``)
in a single transaction the service owns — it does **not** mint a research checkpoint. The
research checkpoint DAG stays research-only; funding is deliberately separate from the research
ledger (funding implies no correctness, authorship, or validation).

Source-aware (Decision #4): ``native`` = Kamino comps budget against the platform's own compute,
created **only** by an actor holding the ``internal`` role (``403`` otherwise), born ``settled``
(Decision #5); ``stripe`` = external paid funding, modeled and born ``pending`` (no real
settlement here). Budget = Σ settled allocations; ``spent`` is 0 until agents meter compute
(0.7.0, Decision #6).

``FundingAllocation`` is append-only (``models/append_only.py``); a status lifecycle is modeled
as new rows, never edits — so this service only ever *creates* allocations.
"""

from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.roles import actor_is_internal
from app.models.actor import Actor
from app.models.enums import FundingSource, FundingStatus
from app.models.funding import FundingAllocation
from app.models.project import Project
from app.schemas.checkpoint import ActorSummary
from app.schemas.funding import FundingCreate, FundingRead, ProjectBudget
from app.services import contributions

# Default accounting unit for the budget totals when there is nothing settled to infer it from.
_DEFAULT_CURRENCY = "USD"


def _to_read(allocation: FundingAllocation, actor: ActorSummary | None) -> FundingRead:
    return FundingRead(
        id=allocation.id,
        project_id=allocation.project_id,
        actor_id=allocation.actor_id,
        actor=actor,
        amount=allocation.amount,
        currency=allocation.currency,
        kind=allocation.kind,
        source=allocation.source,
        status=allocation.status,
        notes=allocation.notes,
        created_at=allocation.created_at,
        updated_at=allocation.updated_at,
    )


async def _enrich(db: AsyncSession, allocations: list[FundingAllocation]) -> list[FundingRead]:
    """Resolve funder actors for a set of allocations (one query, no N+1)."""
    if not allocations:
        return []
    actor_ids = {a.actor_id for a in allocations if a.actor_id is not None}
    actors: dict[UUID, ActorSummary] = {}
    if actor_ids:
        rows = await db.execute(select(Actor).where(Actor.id.in_(actor_ids)))
        actors = {actor.id: ActorSummary.model_validate(actor) for actor in rows.scalars()}
    return [
        _to_read(a, actors.get(a.actor_id) if a.actor_id else None) for a in allocations
    ]


async def create_funding(
    db: AsyncSession, project_id: UUID, payload: FundingCreate, actor: Actor
) -> FundingRead:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # Stripe funding has no real settlement path yet (Checkout/webhooks land in 0.7.0). The model
    # and enum stay so 0.7.0 can activate it, but the *create* path accepts only native today —
    # otherwise any authenticated actor could write arbitrary `pending` allocations into the
    # public funding history (0.6.2 hardening). Native remains internal-gated below.
    if payload.source != FundingSource.NATIVE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Only native funding is available in this release; Stripe lands in 0.7.0",
        )

    # Native funding (Kamino comps budget) is gated to internal actors (Decision #4).
    if payload.source == FundingSource.NATIVE and not actor_is_internal(actor):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Native funding requires the `internal` role",
        )

    # Born in terminal status (Decision #5): native settles immediately (no money moves);
    # stripe is modeled as pending (no real settlement lands in this release).
    born_status = (
        FundingStatus.SETTLED if payload.source == FundingSource.NATIVE else FundingStatus.PENDING
    )

    allocation = FundingAllocation(
        project_id=project_id,
        actor_id=actor.id,
        amount=payload.amount,
        currency=payload.currency,
        kind=payload.kind,
        source=payload.source,
        status=born_status,
        notes=payload.notes,
    )
    db.add(allocation)
    await db.flush()  # assign allocation.id before recording the contribution

    # Contribution-only: a `fund` contribution links the allocation, NOT a checkpoint
    # (Decision #3). The service owns the single commit so the row + contribution are atomic.
    contributions.record_contribution(
        db,
        project_id=project_id,
        actor=actor,
        action=contributions.ACTION_FUND,
        target_type="funding_allocation",
        target_id=allocation.id,
        funding_allocation_id=allocation.id,
        checkpoint_id=None,
    )
    await db.commit()
    await db.refresh(allocation)
    return (await _enrich(db, [allocation]))[0]


async def list_funding(db: AsyncSession, project_id: UUID) -> list[FundingRead]:
    result = await db.execute(
        select(FundingAllocation)
        .where(FundingAllocation.project_id == project_id)
        .order_by(FundingAllocation.created_at.desc())
    )
    return await _enrich(db, list(result.scalars()))


async def get_funding(db: AsyncSession, funding_id: UUID) -> FundingRead:
    allocation = await db.get(FundingAllocation, funding_id)
    if allocation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Funding allocation not found",
        )
    return (await _enrich(db, [allocation]))[0]


async def project_budget(db: AsyncSession, project_id: UUID) -> ProjectBudget:
    """Derive the project budget from the funding ledger (one query, Python aggregation).

    ``funded`` = Σ settled allocations; ``spent`` = 0 (no compute metering until 0.7.0);
    ``available`` = funded − spent. Breakdowns: settled totals by source, and totals by status
    across all allocations. Amounts are summed in a single accounting unit.
    """
    # Ordered oldest→newest so the inferred accounting unit is deterministically the *most recent*
    # settled allocation's currency (last write wins), not whatever order the rows came back in.
    result = await db.execute(
        select(FundingAllocation)
        .where(FundingAllocation.project_id == project_id)
        .order_by(FundingAllocation.created_at)
    )
    allocations = list(result.scalars())

    funded = Decimal("0")
    by_source: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    by_status: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    currency = _DEFAULT_CURRENCY
    for a in allocations:
        by_status[a.status.value] += a.amount
        if a.status == FundingStatus.SETTLED:
            funded += a.amount
            by_source[a.source.value] += a.amount
            currency = a.currency  # infer the accounting unit from settled funding

    spent = Decimal("0")  # Decision #6: no debit ledger until agents land
    return ProjectBudget(
        project_id=project_id,
        currency=currency,
        funded=funded,
        spent=spent,
        available=funded - spent,
        by_source=dict(by_source),
        by_status=dict(by_status),
    )
