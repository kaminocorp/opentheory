from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.api.deps import ActingActor, DbSession
from app.models.actor import Actor
from app.schemas.account import AccountUpdate
from app.schemas.actor import MeRead

router = APIRouter()


@router.get("/me", response_model=MeRead, tags=["auth"])
async def get_me(actor: ActingActor) -> Actor:
    """The resolved acting actor plus its owning account, driving the frontend identity menu.

    Returns ``MeRead`` — the actor fields plus a nested ``account`` (roles/email/username),
    eager-loaded by ``_resolve_or_provision``. ``/me`` is authenticated, so a caller only ever sees
    their **own** principal's PII. Depends on ``ActingActor``, so hitting it provisions the account
    + actor on first authenticated call and rejects an unauthenticated caller with ``401``.
    """
    return actor


@router.patch("/me", response_model=MeRead, tags=["auth"])
async def update_me(payload: AccountUpdate, actor: ActingActor, db: DbSession) -> Actor:
    """Edit the caller's **own** principal — currently just the public ``@username`` (0.8.3).

    Authorization is implicit: the handle is written to ``actor.account``, i.e. *this* caller's
    account, so a principal can never rename anyone else. ``AccountUpdate`` already normalized +
    pattern/reserved-validated the value (``422`` on bad input); here we only enforce the DB
    uniqueness, translating the ``uq_accounts_username`` violation into a clean ``409``. A rare
    account-less actor (a ``system``/dev actor with no principal) has no handle to edit → ``403``.
    """
    account = actor.account
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires an account-backed principal",
        )

    if payload.username == account.username:
        return actor  # no-op rename — avoid a needless write / spurious 409 against oneself

    account.username = payload.username
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That username is already taken",
        ) from exc
    # `expire_on_commit=False` keeps `actor` + its eager-loaded `account` (now with the new handle
    # and a bumped `updated_at`) populated, so we can serialize MeRead without a relationship
    # lazy-load.
    return actor
