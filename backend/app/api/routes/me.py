from fastapi import APIRouter

from app.api.deps import ActingActor
from app.models.actor import Actor
from app.schemas.actor import MeRead

router = APIRouter()


@router.get("/me", response_model=MeRead, tags=["auth"])
async def get_me(actor: ActingActor) -> Actor:
    """The resolved acting actor plus its owning account, driving the frontend identity menu.

    Returns ``MeRead`` — the actor fields plus a nested ``account`` (roles/email), eager-loaded by
    ``_resolve_or_provision``. ``/me`` is authenticated, so a caller only ever sees their **own**
    principal's PII. Depends on ``ActingActor``, so hitting it provisions the account + actor on
    first authenticated call and rejects an unauthenticated caller with ``401``.
    """
    return actor
