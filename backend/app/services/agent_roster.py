"""Agent roster helpers (0.54.0) — compose with membership and OWNER transfer.

``project_agent_members`` is access control, not credit. These helpers
``db.add`` and never commit, so they share the caller's transaction
(same pattern as ``record_contribution``). Resume does not un-revoke
tokens; the new OWNER mints a fresh one in a later slice.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actor import Actor
from app.models.agent_session_token import AgentSessionToken
from app.models.enums import ProjectAgentStatus
from app.models.project_agent_member import ProjectAgentMember
from app.services.agent_actors import AGENT_ACTOR_DISPLAY_NAME, find_research_crew_actor


async def get_roster_row(
    db: AsyncSession, project_id: UUID, actor_id: UUID
) -> ProjectAgentMember | None:
    result = await db.execute(
        select(ProjectAgentMember).where(
            ProjectAgentMember.project_id == project_id,
            ProjectAgentMember.actor_id == actor_id,
        )
    )
    return result.scalar_one_or_none()


async def revoke_live_tokens_for_actors(
    db: AsyncSession,
    project_id: UUID,
    actor_ids: set[UUID],
    *,
    now: datetime | None = None,
) -> None:
    """Set ``revoked_at`` on every still-live token for ``actor_ids`` on this project.

    In-place (tokens are mutable). Does not commit. A later slice mints; this
    slice only needs revoke so a transfer cannot leave a 30-day bearer live.
    """
    if not actor_ids:
        return
    stamped = now if now is not None else datetime.now(UTC)
    result = await db.execute(
        select(AgentSessionToken).where(
            AgentSessionToken.project_id == project_id,
            AgentSessionToken.actor_id.in_(actor_ids),
            AgentSessionToken.revoked_at.is_(None),
        )
    )
    for token in result.scalars():
        token.revoked_at = stamped
        db.add(token)


async def suspend_agents_on_owner_transfer(
    db: AsyncSession,
    project_id: UUID,
    outgoing_account_id: UUID,
) -> None:
    """Suspend outgoing-responsible agents + Research crew; revoke their tokens.

    Does **not** rewrite ``Actor.account_id`` or ``deployed_by_account_id``.
    ADMIN-deployed rows whose ``responsible_account_id`` is not the outgoing
    owner stay ``ACTIVE`` (their tokens stay live). Already-``REVOKED`` rows
    stay revoked. Does not commit.
    """
    crew = await find_research_crew_actor(db, project_id)
    result = await db.execute(
        select(ProjectAgentMember).where(ProjectAgentMember.project_id == project_id)
    )
    rows = list(result.scalars())

    to_revoke: set[UUID] = set()
    for row in rows:
        is_crew = crew is not None and row.actor_id == crew.id
        is_outgoing = row.responsible_account_id == outgoing_account_id
        if not (is_crew or is_outgoing):
            continue
        to_revoke.add(row.actor_id)
        if row.status == ProjectAgentStatus.ACTIVE:
            row.status = ProjectAgentStatus.SUSPENDED
            db.add(row)

    # Research crew with no roster row is left unrostered (still 403).
    if crew is not None:
        to_revoke.add(crew.id)

    await revoke_live_tokens_for_actors(db, project_id, to_revoke)


async def resume_project_agent(
    db: AsyncSession,
    project_id: UUID,
    actor_id: UUID,
    acting: Actor,
) -> ProjectAgentMember:
    """OWNER-only resume: ``ACTIVE`` + ``responsible_account_id`` = acting account.

    Does not rewrite ``Actor.account_id`` or ``deployed_by_account_id``.
    Does not un-revoke tokens. Does not commit. Lazy-imports the manage
    gate so this module and ``project_members`` do not cycle at import time.
    """
    from fastapi import HTTPException, status

    from app.services.project_members import ensure_can_manage

    await ensure_can_manage(db, project_id, acting, require_owner=True)
    row = await get_roster_row(db, project_id, actor_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    row.status = ProjectAgentStatus.ACTIVE
    row.responsible_account_id = acting.account_id
    db.add(row)
    return row


# Re-export so callers can pin the display-name constant without importing agent_actors.
__all__ = [
    "AGENT_ACTOR_DISPLAY_NAME",
    "get_roster_row",
    "resume_project_agent",
    "revoke_live_tokens_for_actors",
    "suspend_agents_on_owner_transfer",
]
