import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager, joinedload

from app.core.auth import AuthError, VerifiedIdentity, verify_bearer_token
from app.core.config import settings
from app.core.roles import INTERNAL_ROLE, actor_is_internal
from app.db.session import get_db
from app.models.account import Account
from app.models.actor import Actor
from app.models.enums import ActorType

DbSession = Annotated[AsyncSession, Depends(get_db)]


def _bearer_token(authorization: str | None) -> str | None:
    """Extract the token from an ``Authorization: Bearer <token>`` header, else None."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


async def _resolve_or_provision(db: AsyncSession, identity: VerifiedIdentity) -> Actor:
    """Map a verified identity to its primary ``human`` ``Actor`` via the owning ``Account``.

    The auth *principal* is the ``Account`` (Account-owns-Actor): ``external_id`` (the JWT ``sub``)
    and ``roles`` live there now. We resolve by joining the Account on ``external_id == sub`` and
    selecting its ``human`` actor, eager-loading ``account`` (``contains_eager``) so role/money
    checks (``require_internal``, funding) read ``actor.account`` synchronously — no async
    lazy-load. On first login we create the Account **and** its one primary human Actor in a single
    transaction (one ``commit``, so neither can orphan). Idempotent on the unique
    ``accounts.external_id``: a concurrent first-login that loses the insert race re-reads the
    winner's Account → primary Actor.
    """
    stmt = (
        select(Actor)
        .join(Account, Actor.account_id == Account.id)
        .options(contains_eager(Actor.account))
        .where(Account.external_id == identity.subject, Actor.type == ActorType.HUMAN)
    )
    actor = (await db.execute(stmt)).scalar_one_or_none()
    if actor is not None:
        return actor

    email = identity.email
    is_internal = bool(email) and email.lower() in settings.internal_actor_emails
    account = Account(
        external_id=identity.subject,
        display_name=identity.display_name or identity.subject,
        email=email,
        roles=[INTERNAL_ROLE] if is_internal else [],
    )
    actor = Actor(
        type=ActorType.HUMAN,
        display_name=identity.display_name or identity.subject,
        account=account,  # ORM sets actor.account_id on flush; account stays loaded on the actor
        actor_metadata={"email": email} if email else {},
    )
    db.add(account)
    db.add(actor)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return (await db.execute(stmt)).scalar_one()
    # No db.refresh: id/timestamps are Python-side defaults and `expire_on_commit=False` keeps the
    # in-memory graph (incl. actor.account) populated, so refreshing would only risk expiring the
    # eager-loaded account into an async lazy-load.
    return actor


async def _resolve_dev_actor(db: AsyncSession, x_dev_actor_id: str | None) -> Actor:
    """The 0.3.x ``X-Dev-Actor-Id`` path, preserved behind the dev flag (same status codes).

    Missing header -> 400, malformed (not a UUID) -> 400, unknown actor id -> 404.
    """
    if x_dev_actor_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Dev-Actor-Id header is required",
        )
    try:
        actor_id = UUID(x_dev_actor_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Dev-Actor-Id must be a valid UUID",
        ) from exc

    # Eager-load `account` (a dev actor may be linked to a bootstrap Account for funding tests):
    # role/`/me` checks read `actor.account` synchronously, and a bare lazy-load would raise
    # MissingGreenlet under async. An account-less dev actor short-circuits to None (many-to-one
    # with a NULL FK never queries), so this is safe either way.
    result = await db.execute(
        select(Actor).options(joinedload(Actor.account)).where(Actor.id == actor_id)
    )
    actor = result.scalar_one_or_none()
    if actor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Acting actor not found",
        )
    return actor


async def get_acting_actor(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
    x_dev_actor_id: Annotated[str | None, Header()] = None,
) -> Actor:
    """Resolve the acting actor from a verified bearer JWT (0.6.0).

    A verified token maps to its owning ``Account`` by ``Account.external_id == sub`` and returns
    that account's primary ``human`` ``Actor``, JIT-provisioning both on first login (0.7.0
    Account-owns-Actor). The ``ActingActor`` *contract* (a resolved ``Actor``) is unchanged — only
    this resolution changed, so every downstream service is untouched.

    When ``auth_dev_header_enabled`` is set (local + tests), a request *without* a bearer token
    may instead carry ``X-Dev-Actor-Id`` (the 0.3.x stopgap), so the DB-backed suite and local
    dev work without an IdP. In production the flag is off and an unauthenticated write is 401.
    """
    token = _bearer_token(authorization)
    if token is not None:
        try:
            # verify_bearer_token is synchronous and, on a JWKS cache miss/rotation, does a
            # blocking network fetch. Run it off the event loop so one cold verification can't
            # stall other in-flight requests on this single-worker machine. (Steady state is an
            # in-memory cache hit thanks to the lifespan prewarm, so the thread hop is cheap.)
            identity = await asyncio.to_thread(verify_bearer_token, token)
        except AuthError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        return await _resolve_or_provision(db, identity)

    if settings.auth_dev_header_enabled:
        return await _resolve_dev_actor(db, x_dev_actor_id)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


ActingActor = Annotated[Actor, Depends(get_acting_actor)]


def require_internal(actor: ActingActor) -> Actor:
    """Authz dependency: the acting actor must hold the ``internal`` (Kamino) role -> 403.

    Returned so a handler can both gate on and use the actor. Native funding gates *in the
    service* (only ``source=native`` requires it, Decision #4); this is the route-level reuse
    hook for later validator/agent permissions.
    """
    if not actor_is_internal(actor):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires the `internal` role",
        )
    return actor


InternalActor = Annotated[Actor, Depends(require_internal)]
