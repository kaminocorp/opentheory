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
actors — the loser hits the constraint, and this service refetches the winner. This
slice does **not** attach an account or write a roster row (later membership slice).
Like the other write helpers, it composes with the caller's transaction: it ``flush``es
but **never commits**.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actor import Actor
from app.models.enums import ActorType

# The single display name every project's agent Actor carries (Decision #3 — role + model are
# recorded per-pass on the AgentRun, not baked into separate identities).
AGENT_ACTOR_DISPLAY_NAME = "Research crew"

# The metadata key the project scoping (and the partial unique index) keys on.
_PROJECT_ID_KEY = "project_id"


async def _find_agent_actor(db: AsyncSession, project_id: UUID) -> Actor | None:
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


async def get_or_create_project_agent_actor(db: AsyncSession, project_id: UUID) -> Actor:
    """Return the project's agent Actor, creating it on first call. Idempotent and race-safe.

    Composes with the caller's transaction (``flush``, no commit). On the rare concurrent-first-pass
    race the partial unique index rejects the loser's insert with an ``IntegrityError``; we roll the
    savepoint back and refetch the winner, so the caller always gets exactly one agent Actor.
    """
    existing = await _find_agent_actor(db, project_id)
    if existing is not None:
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
        return winner
    return actor
