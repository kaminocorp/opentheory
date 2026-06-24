from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthError, VerifiedIdentity, verify_bearer_token
from app.core.config import settings
from app.core.roles import INTERNAL_ROLE, actor_is_internal
from app.db.session import get_db
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
    """Map a verified identity to exactly one ``Actor`` by ``external_id``, JIT-provisioning.

    Idempotent on the unique ``external_id``: a concurrent first-login for the same subject
    that loses the insert race is recovered by re-reading the row the winner committed.
    """
    result = await db.execute(select(Actor).where(Actor.external_id == identity.subject))
    actor = result.scalar_one_or_none()
    if actor is not None:
        return actor

    email = identity.email
    is_internal = bool(email) and email.lower() in settings.internal_actor_emails
    actor = Actor(
        type=ActorType.HUMAN,
        display_name=identity.display_name or identity.subject,
        external_id=identity.subject,
        actor_metadata={"email": email} if email else {},
        roles=[INTERNAL_ROLE] if is_internal else [],
    )
    db.add(actor)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        result = await db.execute(select(Actor).where(Actor.external_id == identity.subject))
        return result.scalar_one()
    await db.refresh(actor)
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

    actor = await db.get(Actor, actor_id)
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

    A verified token maps to exactly one ``Actor`` by ``external_id == sub``, JIT-provisioned
    on first login. The ``ActingActor`` *contract* (a resolved ``Actor``) is unchanged — only
    this resolution changed, so every downstream service is untouched.

    When ``auth_dev_header_enabled`` is set (local + tests), a request *without* a bearer token
    may instead carry ``X-Dev-Actor-Id`` (the 0.3.x stopgap), so the DB-backed suite and local
    dev work without an IdP. In production the flag is off and an unauthenticated write is 401.
    """
    token = _bearer_token(authorization)
    if token is not None:
        try:
            identity = verify_bearer_token(token)
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
