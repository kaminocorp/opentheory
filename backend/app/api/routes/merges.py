from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import ActingActor, DbSession
from app.schemas.merge import MergeCreate, MergeRead
from app.services import merges as merge_service
from app.services.project_members import ensure_is_member

router = APIRouter()


@router.post(
    "/projects/{project_id}/merges",
    response_model=MergeRead,
    status_code=status.HTTP_201_CREATED,
    tags=["merges"],
)
async def merge_branches(
    project_id: UUID,
    payload: MergeCreate,
    db: DbSession,
    actor: ActingActor,
) -> MergeRead:
    await ensure_is_member(db, project_id, actor)
    return await merge_service.merge_branches(db, project_id, payload, actor)
