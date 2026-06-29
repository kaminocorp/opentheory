"""Project services.

`create_project` (0.8.1) is the project write path: in **one transaction** it inserts the project,
records the creator's account as the ``OWNER`` ``ProjectMember``, and auto-records a
``create_project`` ``Contribution`` (intellectual origination — the *only* metadata action that is a
contribution; later edits are not). It mirrors the checkpoint/funding chokepoint discipline: the
contribution helper ``add``s without committing, so the whole flow is one atomic ``commit``.

`get_project_overview` returns the project detail enriched with aggregate ledger counts (0.3.4) and,
from 0.4.4, branch-status counts, a validation count, and a contradictions summary (claims carrying
an unretracted contradicting validation).
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actor import Actor
from app.models.branch import Branch
from app.models.checkpoint import Checkpoint
from app.models.claim import Claim
from app.models.enums import BranchStatus, ProjectRole
from app.models.evidence import Evidence
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.thread import Thread
from app.models.validation import Validation
from app.schemas.project import (
    BranchStatusCounts,
    ContradictionItem,
    ProjectCounts,
    ProjectCreate,
    ProjectOverview,
    ProjectRead,
)
from app.services import claims as claim_service
from app.services import contributions
from app.services import funding as funding_service
from app.services import validations as validation_service


async def create_project(db: AsyncSession, payload: ProjectCreate, actor: Actor) -> Project:
    """Create a project, attribute ownership, and record the creation — atomically.

    The creator's **account** (the principal that can *own*, 0.7.0) becomes the project ``OWNER``,
    and the acting **actor** is credited with a ``create_project`` ``Contribution`` (the *act* is
    the actor's; ownership is the account's — mirroring the funding act-vs-money split). Both are
    written in the same transaction as the project, so a project can never exist without its owner +
    creation record.

    Account-less actors (``system`` / dev-bootstrap via ``X-Dev-Actor-Id``) have no principal that
    can own, so they create an **ownerless** project with **no** contribution — a dev/test-only path
    that mirrors legacy projects whose owner is added by hand in Supabase. Every real authenticated
    principal is provisioned *with* an account (``api/deps.py``), so production creations are always
    owned and attributed.
    """
    project = Project(**payload.model_dump())
    db.add(project)
    try:
        await db.flush()  # assign project.id before the owner row + contribution reference it
    except IntegrityError as exc:
        # The only user-facing uniqueness on a project is its ``slug`` (the immutable URL id). A
        # collision surfaces on this INSERT — translate it into a clean ``409`` rather than letting
        # the raw constraint violation bubble up as a ``500``.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A project with this slug already exists",
        ) from exc

    if actor.account_id is not None:
        db.add(
            ProjectMember(
                project_id=project.id,
                account_id=actor.account_id,
                role=ProjectRole.OWNER,
                invited_by_account_id=actor.account_id,  # the owner self-references on create
            )
        )
        # Originating a project is intellectual origination → a contribution (Decision: create =
        # contribution). Recorded through the shared helper, which `add`s without committing so this
        # whole flow is one atomic transaction (the chokepoint pattern).
        contributions.record_contribution(
            db,
            project_id=project.id,
            actor=actor,
            action=contributions.ACTION_CREATE_PROJECT,
            target_type="project",
            target_id=project.id,
        )

    await db.commit()
    await db.refresh(project)
    return project


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
        budget=await funding_service.project_budget(db, project_id),
    )
