from fastapi import APIRouter

from app.api.deps import ActingActor
from app.models.actor import Actor
from app.schemas.actor import ActorRead

router = APIRouter()


@router.get("/me", response_model=ActorRead, tags=["auth"])
async def get_me(actor: ActingActor) -> Actor:
    """The resolved acting actor (incl. roles), driving the frontend identity menu (0.6.1).

    Depends on ``ActingActor``, so hitting it provisions the actor on first authenticated
    call and rejects an unauthenticated caller with ``401``.
    """
    return actor
