from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import ActingActor, DbSession
from app.models.thread import Thread
from app.schemas.thread import ThreadCreate, ThreadRead
from app.services import threads as thread_service

router = APIRouter()


@router.post(
    "/projects/{project_id}/threads",
    response_model=ThreadRead,
    status_code=status.HTTP_201_CREATED,
    tags=["threads"],
)
async def create_thread(
    project_id: UUID,
    payload: ThreadCreate,
    db: DbSession,
    actor: ActingActor,
) -> Thread:
    return await thread_service.create_thread(db, project_id, payload)


@router.get(
    "/projects/{project_id}/threads",
    response_model=list[ThreadRead],
    tags=["threads"],
)
async def list_threads(project_id: UUID, db: DbSession) -> list[Thread]:
    return await thread_service.list_threads(db, project_id)


@router.get("/threads/{thread_id}", response_model=ThreadRead, tags=["threads"])
async def get_thread(thread_id: UUID, db: DbSession) -> Thread:
    return await thread_service.get_thread(db, thread_id)
