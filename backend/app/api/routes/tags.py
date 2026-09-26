from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import ActingActor, DbSession
from app.schemas.tag import TagCreate, TagRead
from app.services import tags as tag_service
from app.services.project_members import ensure_is_member

router = APIRouter()


@router.post(
    "/projects/{project_id}/tags",
    response_model=TagRead,
    status_code=status.HTTP_201_CREATED,
    tags=["tags"],
)
async def create_tag(
    project_id: UUID,
    payload: TagCreate,
    db: DbSession,
    actor: ActingActor,
) -> TagRead:
    await ensure_is_member(db, project_id, actor)
    return await tag_service.create_tag(db, project_id, payload, actor)


@router.get(
    "/projects/{project_id}/tags",
    response_model=list[TagRead],
    tags=["tags"],
)
async def list_tags(project_id: UUID, db: DbSession) -> list[TagRead]:
    return await tag_service.list_tags(db, project_id)


@router.get("/tags/{tag_id}", response_model=TagRead, tags=["tags"])
async def get_tag(tag_id: UUID, db: DbSession) -> TagRead:
    return await tag_service.get_tag(db, tag_id)
