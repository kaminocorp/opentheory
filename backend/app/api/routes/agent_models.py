from fastapi import APIRouter

from app.core.openrouter_models import OPENROUTER_MODELS
from app.schemas.project import ModelOptionRead

router = APIRouter()


@router.get("/agent-models/catalog", response_model=list[ModelOptionRead])
async def get_agent_model_catalog() -> list[ModelOptionRead]:
    """The curated OpenRouter model catalog that populates the role-assignment dropdowns.

    Public (no auth): it is static reference data with no project scope, and the assignment UI is
    visible to anyone viewing a project. Order is display order; ``provider`` groups the dropdown.
    The same list backs write validation (``PUT /projects/{id}/agent-models``), so the menu can
    never offer an id a save would reject.
    """
    return [
        ModelOptionRead.model_validate(model, from_attributes=True) for model in OPENROUTER_MODELS
    ]
