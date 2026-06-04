from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.thread import Thread
from app.schemas.thread import ThreadCreate


async def create_thread(db: AsyncSession, project_id: UUID, payload: ThreadCreate) -> Thread:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    thread = Thread(project_id=project_id, **payload.model_dump())
    db.add(thread)
    await db.commit()
    await db.refresh(thread)
    return thread


async def list_threads(db: AsyncSession, project_id: UUID) -> list[Thread]:
    result = await db.execute(
        select(Thread)
        .where(Thread.project_id == project_id)
        .order_by(Thread.created_at.desc())
    )
    return list(result.scalars())


async def get_thread(db: AsyncSession, thread_id: UUID) -> Thread:
    thread = await db.get(Thread, thread_id)
    if thread is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found",
        )
    return thread
