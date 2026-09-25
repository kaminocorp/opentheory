from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actor import Actor
from app.models.claim import Claim
from app.models.project import Project
from app.models.thread import Thread
from app.schemas.thread import ThreadCreate, ThreadRead, ThreadSummary
from app.services import contributions
from app.services.grounding import rollup_by_thread, rollup_for_claim_ids


async def create_thread(
    db: AsyncSession, project_id: UUID, payload: ThreadCreate, actor: Actor
) -> Thread:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    thread = Thread(project_id=project_id, **payload.model_dump())
    db.add(thread)
    await db.flush()  # assign thread.id before recording the contribution
    contributions.record_contribution(
        db,
        project_id=project_id,
        actor=actor,
        action=contributions.ACTION_CREATE_THREAD,
        target_type="thread",
        target_id=thread.id,
    )
    await db.commit()
    await db.refresh(thread)
    return thread


async def list_threads(db: AsyncSession, project_id: UUID) -> list[ThreadSummary]:
    # One grouped query yields each thread with its claim count (0.3.4); outer join so
    # threads with zero claims still appear. The grounding rollup (0.16.3) is a second
    # batched pass over the same claim ids — never one query per thread.
    result = await db.execute(
        select(Thread, func.count(Claim.id))
        .outerjoin(Claim, Claim.thread_id == Thread.id)
        .where(Thread.project_id == project_id)
        .group_by(Thread.id)
        .order_by(Thread.created_at.desc())
    )
    rows = list(result)
    claim_ids_by_thread: dict[UUID, list[UUID]] = {thread.id: [] for thread, _count in rows}
    if claim_ids_by_thread:
        claims = await db.execute(
            select(Claim.id, Claim.thread_id).where(Claim.thread_id.in_(claim_ids_by_thread))
        )
        for claim_id, thread_id in claims:
            claim_ids_by_thread[thread_id].append(claim_id)
    rollups = await rollup_by_thread(db, claim_ids_by_thread)
    return [
        ThreadSummary(
            **ThreadRead.model_validate(thread).model_dump(),
            claim_count=count,
            grounding_rollup=rollups[thread.id],
        )
        for thread, count in rows
    ]


async def get_thread(db: AsyncSession, thread_id: UUID) -> Thread:
    thread = await db.get(Thread, thread_id)
    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found",
        )
    return thread


async def get_thread_summary(db: AsyncSession, thread_id: UUID) -> ThreadSummary:
    """The thread read model: identity plus claim count and grounding rollup (0.16.3)."""
    thread = await get_thread(db, thread_id)
    result = await db.execute(select(Claim.id).where(Claim.thread_id == thread_id))
    claim_ids = list(result.scalars())
    return ThreadSummary(
        **ThreadRead.model_validate(thread).model_dump(),
        claim_count=len(claim_ids),
        grounding_rollup=await rollup_for_claim_ids(db, claim_ids),
    )
