"""OWNER-minted agent session tokens (0.55.0).

Compact JWT shown once at mint. Hash at rest. Resolver verifies signature,
``typ=agent_session``, claims, hash, expiry, ``revoked_at``, and ACTIVE roster
on every call, then stamps ``last_used_at``. No self-renew. Fail closed when
``AGENT_SESSION_JWT_SECRET`` is missing. Does not commit (caller's transaction)
except the optional last-used stamp flush — the caller still owns commit.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.models.actor import Actor
from app.models.agent_session_token import AgentSessionToken
from app.models.enums import ActorType, ProjectAgentStatus
from app.models.project_agent_member import ProjectAgentMember
from app.services.agent_roster import get_roster_row
from app.services.project_members import ensure_can_manage

ISS = "opentheory"
AUD = "harness"
TYP = "agent_session"
ALG = "HS256"
DEFAULT_TTL_SECONDS = 2_592_000  # 30 days
IAT_FUTURE_SKEW_SECONDS = 60
SECRET_MISSING_DETAIL = "Agent session signing key is not configured"

# Stashed on the resolved Actor so create_checkpoint can snapshot the sponsor
# without changing ActingActor's type. Never a client field.
SPONSOR_ATTR = "_agent_session_sponsored_by_id"
TOKEN_PROJECT_ATTR = "_agent_session_project_id"
TOKEN_JTI_ATTR = "_agent_session_jti"


def hash_compact_jwt(compact: str) -> bytes:
    return hashlib.sha256(compact.encode("utf-8")).digest()


def agent_session_secret() -> str | None:
    secret = (settings.agent_session_jwt_secret or "").strip()
    return secret or None


def require_agent_session_secret() -> str:
    secret = agent_session_secret()
    if secret is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=SECRET_MISSING_DETAIL,
        )
    return secret


def looks_like_agent_session(token: str) -> bool:
    """True when header or payload claims ``typ=agent_session`` (unverified peek)."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.exceptions.DecodeError:
        return False
    if header.get("typ") == TYP:
        return True
    try:
        claims = jwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_aud": False,
                "verify_exp": False,
                "verify_iss": False,
            },
        )
    except jwt.exceptions.DecodeError:
        return False
    return claims.get("typ") == TYP


def bind_agent_session(actor: Actor, row: AgentSessionToken) -> Actor:
    """Attach sponsor / project / jti onto ``actor`` for this request."""
    setattr(actor, SPONSOR_ATTR, row.minted_by_actor_id)
    setattr(actor, TOKEN_PROJECT_ATTR, row.project_id)
    setattr(actor, TOKEN_JTI_ATTR, row.id)
    return actor


def sponsored_by_of(actor: Actor) -> UUID | None:
    return getattr(actor, SPONSOR_ATTR, None)


def token_project_of(actor: Actor) -> UUID | None:
    return getattr(actor, TOKEN_PROJECT_ATTR, None)


def token_jti_of(actor: Actor) -> UUID | None:
    return getattr(actor, TOKEN_JTI_ATTR, None)


def _clamp_ttl(ttl_seconds: int | None) -> int:
    max_ttl = settings.agent_session_max_ttl_seconds
    if max_ttl < 1:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent session max TTL is not configured",
        )
    requested = min(DEFAULT_TTL_SECONDS, max_ttl) if ttl_seconds is None else ttl_seconds
    if requested < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="ttl_seconds must be at least 1",
        )
    if requested > max_ttl:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="ttl_seconds exceeds OPENTHEORY_AGENT_SESSION_MAX_TTL_SECONDS",
        )
    return requested


def encode_agent_session(
    *,
    jti: UUID,
    actor_id: UUID,
    project_id: UUID,
    minted_by_account_id: UUID,
    minted_by_actor_id: UUID,
    expires_at: datetime,
    issued_at: datetime,
    secret: str,
) -> str:
    payload: dict[str, Any] = {
        "iss": ISS,
        "aud": AUD,
        "typ": TYP,
        "sub": str(actor_id),
        "proj": str(project_id),
        "jti": str(jti),
        "mby": str(minted_by_account_id),
        "mba": str(minted_by_actor_id),
        "iat": issued_at,
        "exp": expires_at,
    }
    return jwt.encode(payload, secret, algorithm=ALG, headers={"typ": TYP})


async def mint_agent_session_token(
    db: AsyncSession,
    project_id: UUID,
    actor_id: UUID,
    acting: Actor,
    *,
    ttl_seconds: int | None = None,
) -> tuple[AgentSessionToken, str]:
    """OWNER-only mint. Returns ``(row, compact JWT)``. Does not commit."""
    secret = require_agent_session_secret()
    await ensure_can_manage(db, project_id, acting, require_owner=True)
    if acting.account_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires an account-backed principal",
        )
    row = await get_roster_row(db, project_id, actor_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if row.status != ProjectAgentStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent roster is not active",
        )
    ttl = _clamp_ttl(ttl_seconds)
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=ttl)
    jti = uuid4()
    compact = encode_agent_session(
        jti=jti,
        actor_id=actor_id,
        project_id=project_id,
        minted_by_account_id=acting.account_id,
        minted_by_actor_id=acting.id,
        expires_at=expires_at,
        issued_at=now,
        secret=secret,
    )
    token = AgentSessionToken(
        id=jti,
        project_id=project_id,
        actor_id=actor_id,
        minted_by_account_id=acting.account_id,
        minted_by_actor_id=acting.id,
        token_hash=hash_compact_jwt(compact),
        expires_at=expires_at,
    )
    db.add(token)
    return token, compact


async def rotate_agent_session_token(
    db: AsyncSession,
    project_id: UUID,
    actor_id: UUID,
    jti: UUID,
    acting: Actor,
    *,
    ttl_seconds: int | None = None,
) -> tuple[AgentSessionToken, str]:
    """OWNER-only: revoke ``jti``, mint a new token. Does not commit."""
    await ensure_can_manage(db, project_id, acting, require_owner=True)
    existing = await db.get(AgentSessionToken, jti)
    if (
        existing is None
        or existing.project_id != project_id
        or existing.actor_id != actor_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    if existing.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Token is already revoked",
        )
    existing.revoked_at = datetime.now(UTC)
    db.add(existing)
    return await mint_agent_session_token(
        db, project_id, actor_id, acting, ttl_seconds=ttl_seconds
    )


async def revoke_agent_session_token(
    db: AsyncSession,
    project_id: UUID,
    actor_id: UUID,
    jti: UUID,
    acting: Actor,
) -> AgentSessionToken:
    """OWNER-only revoke of one token. Idempotent if already revoked. Does not commit."""
    await ensure_can_manage(db, project_id, acting, require_owner=True)
    existing = await db.get(AgentSessionToken, jti)
    if (
        existing is None
        or existing.project_id != project_id
        or existing.actor_id != actor_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    if existing.revoked_at is None:
        existing.revoked_at = datetime.now(UTC)
        db.add(existing)
    return existing


def _uuid_claim(claims: dict[str, Any], name: str) -> UUID:
    raw = claims.get(name)
    try:
        return UUID(str(raw))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def resolve_agent_session_token(db: AsyncSession, compact: str) -> Actor:
    """Verify an agent session JWT and return the agent Actor. Never a human.

    Fail closed: missing secret, bad signature, wrong typ, hash mismatch,
    expired, revoked, or non-ACTIVE roster → 401/403.
    """
    if not looks_like_agent_session(compact):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    secret = agent_session_secret()
    if secret is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = jwt.decode(
            compact,
            secret,
            algorithms=[ALG],
            audience=AUD,
            issuer=ISS,
            options={"require": ["sub", "proj", "jti", "mby", "mba", "typ", "exp", "iat"]},
        )
    except jwt.exceptions.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if claims.get("typ") != TYP:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    now = datetime.now(UTC)
    iat_raw = claims.get("iat")
    if iat_raw is not None:
        if isinstance(iat_raw, datetime):
            iat_dt = iat_raw if iat_raw.tzinfo else iat_raw.replace(tzinfo=UTC)
        else:
            iat_dt = datetime.fromtimestamp(int(iat_raw), UTC)
        if iat_dt > now + timedelta(seconds=IAT_FUTURE_SKEW_SECONDS):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired authentication token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    jti = _uuid_claim(claims, "jti")
    sub = _uuid_claim(claims, "sub")
    proj = _uuid_claim(claims, "proj")
    token_hash = hash_compact_jwt(compact)

    result = await db.execute(
        select(AgentSessionToken).where(AgentSessionToken.id == jti)
    )
    row = result.scalar_one_or_none()
    if (
        row is None
        or row.token_hash != token_hash
        or row.actor_id != sub
        or row.project_id != proj
        or row.revoked_at is not None
        or row.expires_at <= now
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    actor_result = await db.execute(
        select(Actor).options(joinedload(Actor.account)).where(Actor.id == row.actor_id)
    )
    actor = actor_result.scalar_one_or_none()
    if actor is None or actor.type != ActorType.AGENT:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    roster = await db.execute(
        select(ProjectAgentMember).where(
            ProjectAgentMember.project_id == row.project_id,
            ProjectAgentMember.actor_id == row.actor_id,
        )
    )
    seat = roster.scalar_one_or_none()
    if seat is None or seat.status != ProjectAgentStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a project member",
        )

    row.last_used_at = now
    db.add(row)
    return bind_agent_session(actor, row)
