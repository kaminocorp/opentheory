from fastapi import APIRouter

from app.schemas.health import HealthRead

router = APIRouter()


@router.get("/health", response_model=HealthRead)
async def health() -> HealthRead:
    return HealthRead(status="ok")
