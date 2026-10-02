"""Session owner for an external DeepSeek Harness run (0.43.0).

One :class:`HarnessSession` owns one campaign-bound run: the project, the
turn cap, pre-LLM exhaust, and ``ComputeDebit`` for tokens that moved.
This is the object the composition a later campaign actually runs must
bind — ``dsh → llm-pi-ai → python -m app.harness.gateway``. Without it,
``create_gateway_app`` never sees a ``project_id`` and spends OpenRouter
unmetered.

``live_mcp`` stays the domain door (``run_instrument`` /
``create_checkpoint``). This module does not mint a ``Checkpoint``.
It does not light ``AGENT_LOOP_ENABLED`` and does not reuse
``ResearchCampaign`` (that row commissions the built-in orchestrator).
FastAPI does not import this package.

Unfunded is not exhausted: refuse only when ``funded > 0`` and
``available <= 0``. Debit only when ``tokens_used > 0``. A refused
start writes nothing. Exceptions mint nothing.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.harness.composition import CompositionError, verify
from app.models.enums import ComputeDebitKind
from app.services import compute as compute_service
from app.services import funding as funding_service

PROJECT_ID_ENV = "OPENTHEORY_PROJECT_ID"
MAX_TURNS_ENV = "OPENTHEORY_HARNESS_MAX_TURNS"
DEFAULT_MAX_TURNS = 4
SESSION_NOTES = "harness_session_turn"
REASON_COMPOSITION = "composition drifted"
REASON_TURN_BUDGET = "turn budget exhausted"
REASON_PROJECT_BUDGET = compute_service.BUDGET_EXHAUSTED


class TurnRefused(Exception):
    """The turn did not start. No LLM call, no debit, no mint."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def resolve_max_turns(env: Mapping[str, str] | None = None) -> int:
    lookup = env if env is not None else os.environ
    raw = (lookup.get(MAX_TURNS_ENV) or "").strip()
    if not raw:
        return DEFAULT_MAX_TURNS
    try:
        value = int(raw)
    except ValueError as exc:
        raise TurnRefused(f"{MAX_TURNS_ENV} must be an integer") from exc
    if value < 1:
        raise TurnRefused(f"{MAX_TURNS_ENV} must be >= 1")
    return value


def assert_turn_in_budget(turn_index: int, max_turns: int | None = None) -> None:
    cap = max_turns if max_turns is not None else resolve_max_turns()
    if turn_index < 0:
        raise TurnRefused(REASON_TURN_BUDGET)
    if turn_index >= cap:
        raise TurnRefused(REASON_TURN_BUDGET)


def assert_composition(*, version: str | None = None) -> None:
    try:
        if version is None:
            verify()
        else:
            verify(version=version)
    except CompositionError as exc:
        raise TurnRefused(f"{REASON_COMPOSITION}: {exc}") from exc


async def assert_project_budget(
    db: AsyncSession,
    project_id: UUID,
) -> None:
    """Refuse when a funded project has no remaining ComputeDebit pot.

    Unfunded projects (``funded == 0``) are not exhausted — same honesty as
    the live MCP door. The LLM call has not happened yet, so there is
    nothing to debit.
    """
    budget = await funding_service.project_budget(db, project_id)
    if budget.funded > 0 and budget.available <= 0:
        raise TurnRefused(REASON_PROJECT_BUDGET)


def _as_project_id(value: UUID | str) -> UUID:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError as exc:
        raise TurnRefused(f"{PROJECT_ID_ENV} must be a UUID") from exc


@dataclass
class HarnessSession:
    """In-process owner of one external-harness run.

    Persistence is the existing ledger: the human-authored ``Project``
    (question + roster), ``FundingAllocation`` (budget), and
    ``ComputeDebit`` (spend). Turn index is process-local — a restart
    starts a new bound session at turn 0. No schema, no second campaign
    table, no ``AgentRun``.
    """

    project_id: UUID | str
    turn_index: int = 0
    max_turns: int | None = None
    session_factory: async_sessionmaker[AsyncSession] | None = None
    env: Mapping[str, str] | None = None
    notes: str = SESSION_NOTES
    extras: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.project_id = _as_project_id(self.project_id)
        if self.max_turns is None:
            self.max_turns = resolve_max_turns(self.env)

    @property
    def project_uuid(self) -> UUID:
        return self.project_id if isinstance(self.project_id, UUID) else UUID(str(self.project_id))

    def resolved_max_turns(self) -> int:
        return self.max_turns if self.max_turns is not None else resolve_max_turns(self.env)

    def _factory(self) -> async_sessionmaker[AsyncSession]:
        if self.session_factory is not None:
            return self.session_factory
        from app.db.session import AsyncSessionLocal

        return AsyncSessionLocal

    async def authorize(self) -> None:
        """Refuse before the LLM call on drift, turn cap, or funded exhaust."""
        assert_composition()
        assert_turn_in_budget(self.turn_index, self.resolved_max_turns())
        async with self._factory() as db:
            await assert_project_budget(db, self.project_uuid)

    async def record_spend(
        self,
        *,
        tokens_used: int,
        model: str | None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        notes: str | None = None,
    ) -> bool:
        """Debit tokens that moved. ``tokens_used <= 0`` writes nothing."""
        if tokens_used <= 0:
            return False
        async with self._factory() as db:
            debit = await compute_service.record_compute_debit(
                db,
                project_id=self.project_uuid,
                tokens_used=tokens_used,
                model=model,
                kind=ComputeDebitKind.PLANNING,
                notes=notes or self.notes,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            await db.commit()
            return debit is not None

    def advance(self) -> int:
        """Count a started completion (success or attempted) against the cap."""
        self.turn_index += 1
        return self.turn_index


def session_from_env(
    env: Mapping[str, str] | None = None,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> HarnessSession | None:
    """Bind a session when ``OPENTHEORY_PROJECT_ID`` is set. ``None`` otherwise."""
    lookup = env if env is not None else os.environ
    raw = (lookup.get(PROJECT_ID_ENV) or "").strip()
    if not raw:
        return None
    return HarnessSession(
        project_id=raw,
        session_factory=session_factory,
        env=lookup,
    )
