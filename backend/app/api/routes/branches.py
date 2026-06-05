from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import ActingActor, DbSession
from app.schemas.branch import (
    BranchClose,
    BranchCreate,
    BranchDetail,
    BranchRead,
    BranchSummary,
)
from app.services import branches as branch_service

router = APIRouter()


@router.post(
    "/projects/{project_id}/branches",
    response_model=BranchRead,
    status_code=status.HTTP_201_CREATED,
    tags=["branches"],
)
async def create_branch(
    project_id: UUID,
    payload: BranchCreate,
    db: DbSession,
    actor: ActingActor,
) -> BranchRead:
    return await branch_service.create_branch(db, project_id, payload, actor)


@router.get(
    "/projects/{project_id}/branches",
    response_model=list[BranchSummary],
    tags=["branches"],
)
async def list_branches(project_id: UUID, db: DbSession) -> list[BranchSummary]:
    return await branch_service.list_branches(db, project_id)


@router.get("/branches/{branch_id}", response_model=BranchDetail, tags=["branches"])
async def get_branch(branch_id: UUID, db: DbSession) -> BranchDetail:
    return await branch_service.get_branch(db, branch_id)


@router.post(
    "/branches/{branch_id}/close",
    response_model=BranchRead,
    tags=["branches"],
)
async def close_branch(
    branch_id: UUID,
    payload: BranchClose,
    db: DbSession,
    actor: ActingActor,
) -> BranchRead:
    return await branch_service.close_branch(db, branch_id, payload, actor)
