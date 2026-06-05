"""Branch service — parallel lines of exploration, recorded through the checkpoint chokepoint.

A ``Branch`` is a line of exploration that forks from a checkpoint (competing hypothesis,
reproduction, dead-end). Per the 0.4.0 plan (sub-phase 0.4.2):

- ``create_branch`` forks from an in-project checkpoint, writes the ``Branch`` row (status
  ``open``), and mints the branch's first checkpoint — parented on the fork point, stamped
  with ``branch_id`` — with a ``create_branch`` contribution.
- ``close_branch`` transitions an open branch to ``dead_end`` (abandoned) or ``closed``
  (superseded), recording the reason. Abandonment is *recorded, never deleted*
  (primitives.md). ``merged`` is reserved for a later release.

A branch is the one sanctioned mutable ledger object (its ``status`` moves, like a git ref);
its lifecycle *events* are append-only because they are checkpoints. As with validations,
the checkpoint service remains the sole producer of checkpoints — this service composes
with it and owns no commit of its own.

Commit/ordering note: ``create_checkpoint`` refuses a ``branch_id`` that is not open, and it
commits internally. So the close checkpoint is recorded on the **main line** (``branch_id``
omitted) and merely *references* the branch (role ``closed``); the branch's status change is
left pending in the session and committed atomically by that same checkpoint write.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actor import Actor
from app.models.branch import Branch
from app.models.checkpoint import Checkpoint
from app.models.enums import BranchStatus
from app.models.project import Project
from app.models.thread import Thread
from app.schemas.branch import (
    BranchClose,
    BranchCreate,
    BranchDetail,
    BranchRead,
    BranchSummary,
)
from app.schemas.checkpoint import CheckpointCreate, CheckpointRefInput
from app.services import checkpoints as checkpoint_service
from app.services import contributions

_CLOSE_STATUS: dict[str, BranchStatus] = {
    "dead_end": BranchStatus.DEAD_END,
    "closed": BranchStatus.CLOSED,
}


async def create_branch(
    db: AsyncSession,
    project_id: UUID,
    payload: BranchCreate,
    actor: Actor,
) -> BranchRead:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    fork = await db.get(Checkpoint, payload.from_checkpoint_id)
    if fork is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fork checkpoint not found",
        )
    if fork.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fork checkpoint belongs to a different project",
        )

    if payload.thread_id is not None:
        thread = await db.get(Thread, payload.thread_id)
        if thread is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Thread not found",
            )
        if thread.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Thread belongs to a different project",
            )

    branch = Branch(
        project_id=project_id,
        thread_id=payload.thread_id,
        forked_from_checkpoint_id=payload.from_checkpoint_id,
        name=payload.name,
        reason=payload.reason,
        status=BranchStatus.OPEN,
    )
    db.add(branch)
    await db.flush()  # assign branch.id before the checkpoint references/stamps it

    # The branch's first checkpoint: parented on the fork point, recorded *on* the branch,
    # referencing the branch it opened. The chokepoint owns the single atomic commit.
    checkpoint_payload = CheckpointCreate(
        thread_id=payload.thread_id,
        branch_id=branch.id,
        summary=f"Forked branch '{payload.name}'",
        content={
            "branch_id": str(branch.id),
            "forked_from_checkpoint_id": str(payload.from_checkpoint_id),
            "reason": payload.reason,
        },
        parent_ids=[payload.from_checkpoint_id],
    )
    await checkpoint_service.create_checkpoint(
        db,
        project_id,
        checkpoint_payload,
        actor,
        extra_refs=[
            CheckpointRefInput(target_type="branch", target_id=branch.id, role="created")
        ],
        contribution_action=contributions.ACTION_CREATE_BRANCH,
    )

    return BranchRead.model_validate(branch)


async def close_branch(
    db: AsyncSession,
    branch_id: UUID,
    payload: BranchClose,
    actor: Actor,
) -> BranchRead:
    branch = await db.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Branch not found",
        )
    if branch.status != BranchStatus.OPEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Branch is not open (status: {branch.status.value})",
        )

    # Flip status now; the change is pending in the session and is committed atomically by
    # the checkpoint write below.
    branch.status = _CLOSE_STATUS[payload.outcome]

    # The close event is recorded on the main line (the branch is no longer open, so it
    # cannot carry branch_id); it references the branch with role "closed".
    checkpoint_payload = CheckpointCreate(
        thread_id=branch.thread_id,
        summary=f"Closed branch '{branch.name}' ({payload.outcome})",
        content={
            "branch_id": str(branch.id),
            "outcome": payload.outcome,
            "reason": payload.reason,
        },
    )
    await checkpoint_service.create_checkpoint(
        db,
        branch.project_id,
        checkpoint_payload,
        actor,
        extra_refs=[
            CheckpointRefInput(target_type="branch", target_id=branch.id, role="closed")
        ],
        contribution_action=contributions.ACTION_CLOSE_BRANCH,
    )

    return BranchRead.model_validate(branch)


async def list_branches(db: AsyncSession, project_id: UUID) -> list[BranchSummary]:
    # One grouped query yields each branch with its checkpoint count (0.4.4); outer join
    # so freshly forked branches with only their creation checkpoint (or none) still appear.
    result = await db.execute(
        select(Branch, func.count(Checkpoint.id))
        .outerjoin(Checkpoint, Checkpoint.branch_id == Branch.id)
        .where(Branch.project_id == project_id)
        .group_by(Branch.id)
        .order_by(Branch.created_at.desc())
    )
    return [
        BranchSummary(**BranchRead.model_validate(branch).model_dump(), checkpoint_count=count)
        for branch, count in result
    ]


async def get_branch(db: AsyncSession, branch_id: UUID) -> BranchDetail:
    branch = await db.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Branch not found",
        )
    checkpoints = await checkpoint_service.list_checkpoints_for_branch(db, branch_id)
    return BranchDetail(
        **BranchRead.model_validate(branch).model_dump(),
        checkpoints=checkpoints,
    )
