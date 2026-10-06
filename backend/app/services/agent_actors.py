"""Agent-actor provisioning (0.12.0) — the first production creation path for ``Actor(type=agent)``.

Decision #3: **one ``Research crew`` agent Actor per project** (``display_name="Research crew"``),
created lazily on the first pass. It is *not* a ``ProjectMember`` — the commissioning human's
membership is the authorization (route gate), and ``run_instrument`` / ``create_checkpoint``
attribute to whatever Actor they are handed. The agent is an *authored identity*, not a
governance principal — mirroring the funder-vs-contributor separation.

``0.53.0`` narrowed the durable uniqueness guard: a partial unique index on
``actor_metadata->>'project_id'`` scoped to ``type = 'AGENT' AND display_name = 'Research crew'``
(declared on the ``Actor`` model, mirrored by migration 0022). Named harness agents are
unconstrained here. Two concurrent first passes still cannot mint two Research-crew
actors — the loser hits the constraint, and this service refetches the winner.

``0.54.0`` ensures an ACTIVE RESEARCHER roster row when the project exists
(missing project — the UUID-only test path — stays unrostered). An existing
``SUSPENDED`` / ``REVOKED`` row is left alone so OWNER-transfer stays sticky.
When the project has an OWNER and the Actor is still account-less, the owner's
Account is attached (new harness agents are never minted account-less). Like
the other write helpers, it composes with the caller's transaction: it
``flush``es but **never commits**.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actor import Actor
from app.models.enums import ActorType, ProjectAgentRole, ProjectAgentStatus, ProjectRole
from app.models.project import Project
from app.models.project_agent_member import ProjectAgentMember
from app.models.project_member import ProjectMember

# The single display name every project's agent Actor carries (Decision #3 — role + model are
# recorded per-pass on the AgentRun, not baked into separate identities).
AGENT_ACTOR_DISPLAY_NAME = "Research crew"

# The metadata key the project scoping (and the partial unique index) keys on.
_PROJECT_ID_KEY = "project_id"


async def find_research_crew_actor(db: AsyncSession, project_id: UUID) -> Actor | None:
    """The existing Research-crew Actor for ``project_id`` (matching the partial unique index).

    ``actor_metadata[...].as_string()`` renders the Postgres ``actor_metadata ->> 'project_id'``
    accessor — the same expression the unique index is built on. Scoped to
    ``display_name = 'Research crew'`` so a later named harness agent on the same
    project cannot be mistaken for the default slot (and so ``scalar_one_or_none``
    cannot raise once a roster of two exists).
    """
    result = await db.execute(
        select(Actor).where(
            Actor.type == ActorType.AGENT,
            Actor.display_name == AGENT_ACTOR_DISPLAY_NAME,
            Actor.actor_metadata[_PROJECT_ID_KEY].as_string() == str(project_id),
        )
    )
    return result.scalar_one_or_none()


# Back-compat alias for the few in-module / older call sites.
_find_agent_actor = find_research_crew_actor


async def _project_owner_account_id(db: AsyncSession, project_id: UUID) -> UUID | None:
    result = await db.execute(
        select(ProjectMember.account_id).where(
            ProjectMember.project_id == project_id,
            ProjectMember.role == ProjectRole.OWNER,
        )
    )
    return result.scalar_one_or_none()


async def _ensure_research_crew_roster(
    db: AsyncSession, project_id: UUID, actor: Actor
) -> None:
    """Insert an ACTIVE RESEARCHER roster row if the project exists and none does.

    A missing project (UUID-only tests) cannot take a roster FK. An existing
    roster row of any status is left untouched so a transfer suspend sticks.
    """
    if await db.get(Project, project_id) is None:
        return

    existing = await db.execute(
        select(ProjectAgentMember.id).where(
            ProjectAgentMember.project_id == project_id,
            ProjectAgentMember.actor_id == actor.id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return

    owner_account_id = await _project_owner_account_id(db, project_id)
    if actor.account_id is None and owner_account_id is not None:
        actor.account_id = owner_account_id
        db.add(actor)

    db.add(
        ProjectAgentMember(
            project_id=project_id,
            actor_id=actor.id,
            deployed_by_account_id=owner_account_id,
            responsible_account_id=owner_account_id,
            role=ProjectAgentRole.RESEARCHER,
            status=ProjectAgentStatus.ACTIVE,
        )
    )
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        # Concurrent first-pass winner already inserted the unique pair.
        return


async def get_or_create_project_agent_actor(db: AsyncSession, project_id: UUID) -> Actor:
    """Return the project's agent Actor, creating it on first call. Idempotent and race-safe.

    Composes with the caller's transaction (``flush``, no commit). On the rare concurrent-first-pass
    race the partial unique index rejects the loser's insert with an ``IntegrityError``; we roll the
    savepoint back and refetch the winner, so the caller always gets exactly one agent Actor.
    When the project row exists, also ensures a roster seat (does not revive suspended/revoked).
    """
    existing = await _find_agent_actor(db, project_id)
    if existing is not None:
        await _ensure_research_crew_roster(db, project_id, existing)
        return existing

    actor = Actor(
        type=ActorType.AGENT,
        display_name=AGENT_ACTOR_DISPLAY_NAME,
        account_id=None,
        actor_metadata={_PROJECT_ID_KEY: str(project_id)},
    )
    db.add(actor)
    try:
        # A SAVEPOINT isolates the insert: if the unique index rejects it (a concurrent winner), we
        # roll back to here and refetch — without poisoning the caller's outer transaction.
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        winner = await _find_agent_actor(db, project_id)
        if winner is None:
            # The insert failed for a reason other than the idempotency race — surface it.
            raise
        await _ensure_research_crew_roster(db, project_id, winner)
        return winner
    await _ensure_research_crew_roster(db, project_id, actor)
    return actor
