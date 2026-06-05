"""Project read services.

`get_project_overview` returns the project detail enriched with aggregate ledger counts
(0.3.4) and, from 0.4.4, branch-status counts, a validation count, and a contradictions
summary (claims carrying an unretracted contradicting validation). Reads only; the project
create/list paths remain inline in the route.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.branch import Branch
from app.models.checkpoint import Checkpoint
from app.models.claim import Claim
from app.models.enums import BranchStatus
from app.models.evidence import Evidence
from app.models.project import Project
from app.models.thread import Thread
from app.models.validation import Validation
from app.schemas.project import (
    BranchStatusCounts,
    ContradictionItem,
    ProjectCounts,
    ProjectOverview,
    ProjectRead,
)
from app.services import claims as claim_service
from app.services import validations as validation_service


async def _count(db: AsyncSession, model: type, project_id: UUID) -> int:
    result = await db.execute(
        select(func.count()).select_from(model).where(model.project_id == project_id)
    )
    return int(result.scalar_one())


async def _branch_counts(db: AsyncSession, project_id: UUID) -> tuple[BranchStatusCounts, int]:
    """Branches grouped by status, plus the total (one grouped query)."""
    result = await db.execute(
        select(Branch.status, func.count())
        .where(Branch.project_id == project_id)
        .group_by(Branch.status)
    )
    by_status = {status_value: int(count) for status_value, count in result}
    counts = BranchStatusCounts(
        open=by_status.get(BranchStatus.OPEN, 0),
        dead_end=by_status.get(BranchStatus.DEAD_END, 0),
        closed=by_status.get(BranchStatus.CLOSED, 0),
    )
    return counts, sum(by_status.values())


async def _contradictions(db: AsyncSession, project_id: UUID) -> list[ContradictionItem]:
    """Claims whose derived signal is ``contested`` (unretracted contradicts/failed).

    Batched: one query for the project's claims, one (inside the validations service) for
    all their validations — then the shared ``compute_signal`` decides. No N+1.
    """
    result = await db.execute(
        select(Claim).where(Claim.project_id == project_id).order_by(Claim.created_at.desc())
    )
    claims = list(result.scalars())
    by_claim = await validation_service.validations_by_claim(db, [c.id for c in claims])
    return [
        ContradictionItem(claim_id=claim.id, thread_id=claim.thread_id, statement=claim.statement)
        for claim in claims
        if claim_service.compute_signal(by_claim.get(claim.id, [])) == "contested"
    ]


async def get_project_overview(db: AsyncSession, project_id: UUID) -> ProjectOverview:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    branch_counts, branch_total = await _branch_counts(db, project_id)
    counts = ProjectCounts(
        threads=await _count(db, Thread, project_id),
        claims=await _count(db, Claim, project_id),
        evidence=await _count(db, Evidence, project_id),
        checkpoints=await _count(db, Checkpoint, project_id),
        validations=await _count(db, Validation, project_id),
        branches=branch_total,
    )
    return ProjectOverview(
        **ProjectRead.model_validate(project).model_dump(),
        counts=counts,
        branch_counts=branch_counts,
        contradictions=await _contradictions(db, project_id),
    )
