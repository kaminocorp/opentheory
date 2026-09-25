"""Merge service — synthesize parallel lines through the checkpoint chokepoint (0.21.0).

A merge is a new checkpoint with **multiple parents** (the head of each source branch
plus the head of the target line). History is never rewritten: source branches are
marked ``merged`` (recorded, not deleted) and cannot receive further checkpoints.
``merged`` status is written *only* here — ``close_branch`` cannot claim a merge that
did not happen.

Composes with ``create_checkpoint``; this service owns no commit of its own. Source
status flips are pending in the session and committed atomically by the chokepoint.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actor import Actor
from app.models.branch import Branch
from app.models.checkpoint import Checkpoint
from app.models.claim import Claim
from app.models.enums import BranchStatus
from app.models.project import Project
from app.models.thread import Thread
from app.schemas.branch import BranchRead
from app.schemas.checkpoint import CheckpointCreate, CheckpointRefInput
from app.schemas.merge import MergeCreate, MergeRead
from app.services import checkpoints as checkpoint_service
from app.services import contributions


async def _latest_on_branch(db: AsyncSession, branch_id: UUID) -> Checkpoint | None:
    result = await db.execute(
        select(Checkpoint)
        .where(Checkpoint.branch_id == branch_id)
        .order_by(Checkpoint.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _latest_main_line(
    db: AsyncSession,
    project_id: UUID,
    thread_id: UUID | None,
) -> Checkpoint | None:
    """Newest main-line checkpoint, optionally scoped to a thread.

    When every source branch shares a thread we stay on that thread's main line so a
    merge in thread A cannot silently parent on thread B's tip. Project-wide otherwise.
    """
    stmt = select(Checkpoint).where(
        Checkpoint.project_id == project_id,
        Checkpoint.branch_id.is_(None),
    )
    if thread_id is not None:
        stmt = stmt.where(Checkpoint.thread_id == thread_id)
    stmt = stmt.order_by(Checkpoint.created_at.desc()).limit(1)
    return (await db.execute(stmt)).scalar_one_or_none()


async def _load_open_branch(
    db: AsyncSession,
    project_id: UUID,
    branch_id: UUID,
    *,
    label: str,
) -> Branch:
    branch = await db.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{label} branch {branch_id} not found",
        )
    if branch.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} branch {branch_id} belongs to a different project",
        )
    if branch.status != BranchStatus.OPEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} branch is not open (status: {branch.status.value})",
        )
    return branch


async def merge_branches(
    db: AsyncSession,
    project_id: UUID,
    payload: MergeCreate,
    actor: Actor,
) -> MergeRead:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    seen: set[UUID] = set()
    source_ids: list[UUID] = []
    for branch_id in payload.source_branch_ids:
        if branch_id in seen:
            continue
        seen.add(branch_id)
        source_ids.append(branch_id)
    if not source_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one source branch is required",
        )

    if payload.target_branch_id is not None and payload.target_branch_id in seen:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A source branch cannot be the merge target",
        )

    sources = [
        await _load_open_branch(db, project_id, branch_id, label="Source")
        for branch_id in source_ids
    ]

    target: Branch | None = None
    if payload.target_branch_id is not None:
        target = await _load_open_branch(
            db, project_id, payload.target_branch_id, label="Target"
        )

    thread_id = payload.thread_id
    if thread_id is not None:
        thread = await db.get(Thread, thread_id)
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
    else:
        source_threads = {branch.thread_id for branch in sources}
        if len(source_threads) == 1:
            thread_id = next(iter(source_threads))

    parents: list[Checkpoint] = []
    seen_parent_ids: set[UUID] = set()

    async def _add_parent(checkpoint: Checkpoint | None) -> None:
        if checkpoint is None or checkpoint.id in seen_parent_ids:
            return
        seen_parent_ids.add(checkpoint.id)
        parents.append(checkpoint)

    for branch in sources:
        head = await _latest_on_branch(db, branch.id)
        if head is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Source branch '{branch.name}' has no checkpoints to merge",
            )
        await _add_parent(head)

    if target is not None:
        await _add_parent(await _latest_on_branch(db, target.id))
    else:
        await _add_parent(await _latest_main_line(db, project_id, thread_id))

    if len(parents) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A merge requires at least two distinct parent checkpoints",
        )

    claim_ids: list[UUID] = []
    seen_claims: set[UUID] = set()
    for claim_id in payload.claim_ids:
        if claim_id in seen_claims:
            continue
        seen_claims.add(claim_id)
        claim = await db.get(Claim, claim_id)
        if claim is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Claim {claim_id} not found",
            )
        if claim.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Claim {claim_id} belongs to a different project",
            )
        claim_ids.append(claim_id)

    # Flip source status now; the change is pending and is committed by the chokepoint.
    for branch in sources:
        branch.status = BranchStatus.MERGED

    source_names = ", ".join(f"'{branch.name}'" for branch in sources)
    target_label = f"'{target.name}'" if target is not None else "the main line"
    summary = payload.summary or f"Merged {source_names} into {target_label}"
    rationale = (payload.rationale or "").strip() or None

    extra_refs = [
        CheckpointRefInput(target_type="branch", target_id=branch.id, role="merged")
        for branch in sources
    ]
    extra_refs.extend(
        CheckpointRefInput(target_type="claim", target_id=claim_id, role="merged")
        for claim_id in claim_ids
    )

    checkpoint = await checkpoint_service.create_checkpoint(
        db,
        project_id,
        CheckpointCreate(
            thread_id=thread_id,
            branch_id=target.id if target is not None else None,
            summary=summary,
            content={
                "resolution": payload.resolution.value,
                "rationale": rationale,
                "source_branch_ids": [str(branch.id) for branch in sources],
                "target_branch_id": str(target.id) if target is not None else None,
                "claim_ids": [str(claim_id) for claim_id in claim_ids],
            },
            notes=rationale,
            parent_ids=[parent.id for parent in parents],
        ),
        actor,
        extra_refs=extra_refs,
        contribution_action=contributions.ACTION_MERGE,
    )

    return MergeRead(
        checkpoint=checkpoint,
        source_branches=[BranchRead.model_validate(branch) for branch in sources],
        target_branch_id=target.id if target is not None else None,
        resolution=payload.resolution,
        parent_ids=checkpoint.parent_ids,
    )
