from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import ActingActor, DbSession
from app.schemas.funding import FundingCreate, FundingRead, ProjectBudget
from app.services import funding as funding_service

router = APIRouter()


@router.post(
    "/projects/{project_id}/funding",
    response_model=FundingRead,
    status_code=status.HTTP_201_CREATED,
    tags=["funding"],
)
async def create_funding(
    project_id: UUID,
    payload: FundingCreate,
    db: DbSession,
    actor: ActingActor,
) -> FundingRead:
    # Requires authentication (ActingActor). Native funding additionally requires the
    # `internal` role, enforced in the service since it depends on payload.source.
    return await funding_service.create_funding(db, project_id, payload, actor)


@router.get(
    "/projects/{project_id}/funding",
    response_model=list[FundingRead],
    tags=["funding"],
)
async def list_funding(project_id: UUID, db: DbSession) -> list[FundingRead]:
    return await funding_service.list_funding(db, project_id)


@router.get(
    "/projects/{project_id}/budget",
    response_model=ProjectBudget,
    tags=["funding"],
)
async def get_project_budget(project_id: UUID, db: DbSession) -> ProjectBudget:
    return await funding_service.project_budget(db, project_id)


@router.get(
    "/funding/{funding_id}",
    response_model=FundingRead,
    tags=["funding"],
)
async def get_funding(funding_id: UUID, db: DbSession) -> FundingRead:
    return await funding_service.get_funding(db, funding_id)
