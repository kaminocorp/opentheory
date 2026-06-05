from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import ActingActor, DbSession
from app.schemas.validation import ValidationCreate, ValidationRead
from app.services import validations as validation_service

router = APIRouter()


@router.post(
    "/projects/{project_id}/validations",
    response_model=ValidationRead,
    status_code=status.HTTP_201_CREATED,
    tags=["validations"],
)
async def create_validation(
    project_id: UUID,
    payload: ValidationCreate,
    db: DbSession,
    actor: ActingActor,
) -> ValidationRead:
    return await validation_service.create_validation(db, project_id, payload, actor)


@router.get(
    "/projects/{project_id}/validations",
    response_model=list[ValidationRead],
    tags=["validations"],
)
async def list_validations(project_id: UUID, db: DbSession) -> list[ValidationRead]:
    return await validation_service.list_validations(db, project_id)


@router.get(
    "/claims/{claim_id}/validations",
    response_model=list[ValidationRead],
    tags=["validations"],
)
async def list_claim_validations(claim_id: UUID, db: DbSession) -> list[ValidationRead]:
    return await validation_service.list_validations_for_claim(db, claim_id)


@router.get(
    "/validations/{validation_id}",
    response_model=ValidationRead,
    tags=["validations"],
)
async def get_validation(validation_id: UUID, db: DbSession) -> ValidationRead:
    return await validation_service.get_validation(db, validation_id)
