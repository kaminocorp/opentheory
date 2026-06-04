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
    # threads with zero claims still appear.
    result = await db.execute(
        select(Thread, func.count(Claim.id))
        .outerjoin(Claim, Claim.thread_id == Thread.id)
        .where(Thread.project_id == project_id)
        .group_by(Thread.id)
        .order_by(Thread.created_at.desc())
    )
    return [
        ThreadSummary(**ThreadRead.model_validate(thread).model_dump(), claim_count=count)
        for thread, count in result
    ]


async def get_thread(db: AsyncSession, thread_id: UUID) -> Thread:
    thread = await db.get(Thread, thread_id)
    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found",
        )
    return thread
