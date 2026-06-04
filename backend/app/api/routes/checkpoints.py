from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import ActingActor, DbSession
from app.schemas.checkpoint import CheckpointCreate, CheckpointRead
from app.services import checkpoints as checkpoint_service

router = APIRouter()


@router.post(
    "/projects/{project_id}/checkpoints",
    response_model=CheckpointRead,
    status_code=status.HTTP_201_CREATED,
    tags=["checkpoints"],
)
async def create_checkpoint(
    project_id: UUID,
    payload: CheckpointCreate,
    db: DbSession,
    actor: ActingActor,
) -> CheckpointRead:
    return await checkpoint_service.create_checkpoint(db, project_id, payload, actor)


@router.get(
    "/projects/{project_id}/checkpoints",
    response_model=list[CheckpointRead],
    tags=["checkpoints"],
)
async def list_checkpoints(project_id: UUID, db: DbSession) -> list[CheckpointRead]:
    return await checkpoint_service.list_checkpoints(db, project_id)


@router.get(
    "/checkpoints/{checkpoint_id}",
    response_model=CheckpointRead,
    tags=["checkpoints"],
)
async def get_checkpoint(checkpoint_id: UUID, db: DbSession) -> CheckpointRead:
    return await checkpoint_service.get_checkpoint(db, checkpoint_id)
