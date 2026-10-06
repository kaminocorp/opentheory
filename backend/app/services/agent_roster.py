"""Agent roster helpers (0.54.0 / 0.57.0) — membership, transfer, Crew reads.

``project_agent_members`` is access control, not credit. Write helpers
``db.add`` and never commit, so they share the caller's transaction
(same pattern as ``record_contribution``). Resume does not un-revoke
tokens; the OWNER mints a fresh one.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.actor import Actor
from app.models.agent_session_token import AgentSessionToken
from app.models.compute_debit import ComputeDebit
from app.models.enums import ActorType, ProjectAgentRole, ProjectAgentStatus
from app.models.project_agent_member import ProjectAgentMember
from app.schemas.account import AccountSummary
from app.schemas.agent_roster import (
    AgentDeployRequest,
    AgentLiveTokenRead,
    AgentRosterPatch,
    AgentRosterRead,
)
from app.services.agent_actors import (
    AGENT_ACTOR_DISPLAY_NAME,
    find_research_crew_actor,
    get_or_create_project_agent_actor,
)
from app.services.harness_meter import is_daily_cap_adjustment


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
    """OWNER-only resume of a ``SUSPENDED`` row.

    ``REVOKED`` is terminal — deploy a new agent, do not flip this row.
    ``ACTIVE`` is ``409`` (already running). Sets ``responsible_account_id``
    to the acting owner's Account. Does not rewrite ``Actor.account_id`` or
    ``deployed_by_account_id``. Does not un-revoke tokens. Does not commit.
    Lazy-imports the manage gate so this module and ``project_members`` do
    not cycle at import time.
    """
    from fastapi import HTTPException, status

    from app.services.project_members import ensure_can_manage

    await ensure_can_manage(db, project_id, acting, require_owner=True)
    row = await get_roster_row(db, project_id, actor_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if row.status == ProjectAgentStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="agent is already active",
        )
    if row.status == ProjectAgentStatus.REVOKED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="agent is revoked; deploy a new agent",
        )
    if row.status != ProjectAgentStatus.SUSPENDED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="agent is already active",
        )
    row.status = ProjectAgentStatus.ACTIVE
    row.responsible_account_id = acting.account_id
    db.add(row)
    return row


def _account_summary(account: Account | None) -> AccountSummary | None:
    if account is None:
        return None
    return AccountSummary.model_validate(account)


async def _billed_spend_by_actor(
    db: AsyncSession, project_id: UUID, actor_ids: set[UUID]
) -> dict[UUID, tuple[int, Decimal]]:
    """Σ billed ``ComputeDebit`` per actor (holds/releases excluded)."""
    if not actor_ids:
        return {}
    result = await db.execute(
        select(
            ComputeDebit.actor_id,
            ComputeDebit.tokens_used,
            ComputeDebit.amount,
            ComputeDebit.notes,
        ).where(
            ComputeDebit.project_id == project_id,
            ComputeDebit.actor_id.in_(actor_ids),
        )
    )
    totals: dict[UUID, tuple[int, Decimal]] = {}
    for actor_id, tokens_used, amount, notes in result:
        if actor_id is None or tokens_used <= 0:
            continue
        if is_daily_cap_adjustment(notes):
            continue
        used, spent = totals.get(actor_id, (0, Decimal("0")))
        totals[actor_id] = (used + int(tokens_used), spent + Decimal(amount))
    return totals


async def _last_used_by_actor(
    db: AsyncSession, project_id: UUID, actor_ids: set[UUID]
) -> dict[UUID, datetime]:
    if not actor_ids:
        return {}
    result = await db.execute(
        select(AgentSessionToken.actor_id, AgentSessionToken.last_used_at).where(
            AgentSessionToken.project_id == project_id,
            AgentSessionToken.actor_id.in_(actor_ids),
            AgentSessionToken.last_used_at.is_not(None),
        )
    )
    latest: dict[UUID, datetime] = {}
    for actor_id, used in result:
        if used is None:
            continue
        previous = latest.get(actor_id)
        if previous is None or used > previous:
            latest[actor_id] = used
    return latest


async def _live_tokens_by_actor(
    db: AsyncSession, project_id: UUID, actor_ids: set[UUID]
) -> dict[UUID, list[AgentSessionToken]]:
    if not actor_ids:
        return {}
    result = await db.execute(
        select(AgentSessionToken)
        .where(
            AgentSessionToken.project_id == project_id,
            AgentSessionToken.actor_id.in_(actor_ids),
            AgentSessionToken.revoked_at.is_(None),
        )
        .order_by(AgentSessionToken.created_at.desc())
    )
    grouped: dict[UUID, list[AgentSessionToken]] = {}
    for token in result.scalars():
        grouped.setdefault(token.actor_id, []).append(token)
    return grouped


async def list_project_agents(
    db: AsyncSession, project_id: UUID, acting: Actor
) -> list[AgentRosterRead]:
    """Members-only roster, including revoked rows. Never token hash or email."""
    from app.services.project_members import ensure_is_member

    await ensure_is_member(db, project_id, acting)

    rows_result = await db.execute(
        select(ProjectAgentMember, Actor)
        .join(Actor, Actor.id == ProjectAgentMember.actor_id)
        .where(ProjectAgentMember.project_id == project_id)
        .order_by(ProjectAgentMember.created_at.asc(), ProjectAgentMember.id.asc())
    )
    pairs = list(rows_result.all())
    if not pairs:
        return []

    account_ids = {
        account_id
        for row, _actor in pairs
        for account_id in (row.deployed_by_account_id, row.responsible_account_id)
        if account_id is not None
    }
    accounts: dict[UUID, Account] = {}
    if account_ids:
        account_rows = await db.execute(select(Account).where(Account.id.in_(account_ids)))
        accounts = {row.id: row for row in account_rows.scalars()}

    actor_ids = {actor.id for _row, actor in pairs}
    spend = await _billed_spend_by_actor(db, project_id, actor_ids)
    live = await _live_tokens_by_actor(db, project_id, actor_ids)
    last_used_at = await _last_used_by_actor(db, project_id, actor_ids)

    out: list[AgentRosterRead] = []
    for row, actor in pairs:
        tokens = live.get(actor.id, [])
        last_used = last_used_at.get(actor.id)
        tokens_used, amount = spend.get(actor.id, (0, Decimal("0")))
        out.append(
            AgentRosterRead(
                actor_id=actor.id,
                display_name=actor.display_name,
                status=row.status,
                role=row.role,
                deployed_by=_account_summary(accounts.get(row.deployed_by_account_id))
                if row.deployed_by_account_id
                else None,
                responsible=_account_summary(accounts.get(row.responsible_account_id))
                if row.responsible_account_id
                else None,
                token_budget_cap=row.token_budget_cap,
                usd_budget_cap=row.usd_budget_cap,
                last_used_at=last_used,
                tokens_used=tokens_used,
                amount=amount,
                live_tokens=[
                    AgentLiveTokenRead(
                        jti=token.id,
                        expires_at=token.expires_at,
                        last_used_at=token.last_used_at,
                    )
                    for token in tokens
                ],
                created_at=row.created_at,
            )
        )
    return out


async def deploy_project_agent(
    db: AsyncSession,
    project_id: UUID,
    acting: Actor,
    payload: AgentDeployRequest,
) -> AgentRosterRead:
    """OWNER / ADMIN deploy. One transaction with the caller. 409 on unique conflict."""
    from fastapi import HTTPException, status

    from app.services.project_members import ensure_can_manage

    await ensure_can_manage(db, project_id, acting)
    if acting.account_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acting actor has no account",
        )

    reuse = payload.reuse_research_crew or payload.display_name == AGENT_ACTOR_DISPLAY_NAME
    if reuse:
        existing = await find_research_crew_actor(db, project_id)
        if existing is not None:
            seat = await get_roster_row(db, project_id, existing.id)
            if seat is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="agent is already deployed",
                )
        actor = await get_or_create_project_agent_actor(db, project_id)
        row = await get_roster_row(db, project_id, actor.id)
        if row is None:
            row = ProjectAgentMember(
                project_id=project_id,
                actor_id=actor.id,
                deployed_by_account_id=acting.account_id,
                responsible_account_id=acting.account_id,
                role=ProjectAgentRole.RESEARCHER,
                status=ProjectAgentStatus.ACTIVE,
                token_budget_cap=payload.token_budget_cap,
                usd_budget_cap=payload.usd_budget_cap,
            )
            db.add(row)
        else:
            row.deployed_by_account_id = acting.account_id
            row.responsible_account_id = acting.account_id
            row.token_budget_cap = payload.token_budget_cap
            row.usd_budget_cap = payload.usd_budget_cap
            db.add(row)
        await db.flush()
        listed = await list_project_agents(db, project_id, acting)
        for item in listed:
            if item.actor_id == actor.id:
                return item
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="deployed agent missing from roster read",
        )

    actor = Actor(
        type=ActorType.AGENT,
        display_name=payload.display_name.strip(),
        account_id=acting.account_id,
        actor_metadata={"project_id": str(project_id)},
    )
    db.add(actor)
    await db.flush()
    row = ProjectAgentMember(
        project_id=project_id,
        actor_id=actor.id,
        deployed_by_account_id=acting.account_id,
        responsible_account_id=acting.account_id,
        role=ProjectAgentRole.RESEARCHER,
        status=ProjectAgentStatus.ACTIVE,
        token_budget_cap=payload.token_budget_cap,
        usd_budget_cap=payload.usd_budget_cap,
    )
    db.add(row)
    await db.flush()
    listed = await list_project_agents(db, project_id, acting)
    for item in listed:
        if item.actor_id == actor.id:
            return item
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="deployed agent missing from roster read",
    )


async def patch_project_agent(
    db: AsyncSession,
    project_id: UUID,
    actor_id: UUID,
    acting: Actor,
    payload: AgentRosterPatch,
) -> AgentRosterRead:
    """Suspend / revoke (OWNER / ADMIN) or resume (OWNER). Same-transaction token revoke."""
    from fastapi import HTTPException, status

    from app.services.project_members import ensure_can_manage

    if payload.status == ProjectAgentStatus.ACTIVE:
        await resume_project_agent(db, project_id, actor_id, acting)
        listed = await list_project_agents(db, project_id, acting)
        for item in listed:
            if item.actor_id == actor_id:
                return item
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    await ensure_can_manage(db, project_id, acting)
    row = await get_roster_row(db, project_id, actor_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if row.status == ProjectAgentStatus.REVOKED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="agent is revoked; deploy a new agent",
        )
    if payload.status == row.status:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"agent is already {row.status.value}",
        )
    if payload.status not in {ProjectAgentStatus.SUSPENDED, ProjectAgentStatus.REVOKED}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="status must be active, suspended, or revoked",
        )
    row.status = payload.status
    db.add(row)
    await revoke_live_tokens_for_actors(db, project_id, {actor_id})
    listed = await list_project_agents(db, project_id, acting)
    for item in listed:
        if item.actor_id == actor_id:
            return item
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")


# Re-export so callers can pin the display-name constant without importing agent_actors.
__all__ = [
    "AGENT_ACTOR_DISPLAY_NAME",
    "deploy_project_agent",
    "get_roster_row",
    "list_project_agents",
    "patch_project_agent",
    "resume_project_agent",
    "revoke_live_tokens_for_actors",
    "suspend_agents_on_owner_transfer",
]
