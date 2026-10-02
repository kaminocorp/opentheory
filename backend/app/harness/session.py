"""Session owner for an external DeepSeek Harness run (0.43.0 / 0.46.0).

One :class:`HarnessSession` owns one campaign-bound run: the project, the
process-local turn cap, the daily token cap, pre-LLM exhaust, and
``ComputeDebit`` for tokens that moved. This is the object the composition
a campaign actually runs must bind — ``dsh → llm-pi-ai →
python -m app.harness.campaign``. Without it, ``create_gateway_app``
never sees a ``project_id`` and spends OpenRouter unmetered.

``live_mcp`` stays the domain door (``run_instrument`` /
``create_checkpoint``). This module does not mint a ``Checkpoint``.
It does not light ``AGENT_LOOP_ENABLED`` and does not reuse
``ResearchCampaign`` (that row commissions the built-in orchestrator).
FastAPI does not import this package.

Unfunded is not exhausted: refuse only when ``funded > 0`` and
``available <= 0``. Debit only when ``tokens_used > 0``. A refused
start writes nothing. Exceptions mint nothing.

The process-local turn index still resets to 0 on restart. The daily
token cap does not: ``authorize()`` sums today's ``ComputeDebit`` rows
whose notes start with ``harness_session_turn`` (UTC day) and refuses
before the model when that sum has already hit
``OPENTHEORY_HARNESS_DAILY_TOKEN_CAP`` (default 20_000). No campaign
table.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.harness.composition import CompositionError, verify
from app.models.compute_debit import ComputeDebit
from app.models.enums import ComputeDebitKind
from app.services import compute as compute_service
from app.services import funding as funding_service

PROJECT_ID_ENV = "OPENTHEORY_PROJECT_ID"
MAX_TURNS_ENV = "OPENTHEORY_HARNESS_MAX_TURNS"
DAILY_TOKEN_CAP_ENV = "OPENTHEORY_HARNESS_DAILY_TOKEN_CAP"
DEFAULT_MAX_TURNS = 4
# Small operator-overridable UTC-day ceiling. The process-local turn cap
# (default 4) resets on restart; this sum of today's harness_session_turn
# ComputeDebit.tokens_used does not. 20_000 tokens is a handful of short
# planning completions — enough to work, not enough to drain a funded pot
# by bouncing the child.
DEFAULT_DAILY_TOKEN_CAP = 20_000
SESSION_NOTES = "harness_session_turn"
REASON_COMPOSITION = "composition drifted"
REASON_TURN_BUDGET = "turn budget exhausted"
REASON_DAILY_CAP = "daily token cap exhausted"
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


def resolve_daily_token_cap(env: Mapping[str, str] | None = None) -> int:
    """UTC-day token ceiling. Default 20_000. Operator-overridable."""
    lookup = env if env is not None else os.environ
    raw = (lookup.get(DAILY_TOKEN_CAP_ENV) or "").strip()
    if not raw:
        return DEFAULT_DAILY_TOKEN_CAP
    try:
        value = int(raw)
    except ValueError as exc:
        raise TurnRefused(f"{DAILY_TOKEN_CAP_ENV} must be an integer") from exc
    if value < 1:
        raise TurnRefused(f"{DAILY_TOKEN_CAP_ENV} must be >= 1")
    return value


def utc_day_start(now: datetime | None = None) -> datetime:
    """Inclusive start of the current UTC day (the daily-cap window)."""
    moment = datetime.now(UTC) if now is None else now
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    moment = moment.astimezone(UTC)
    return moment.replace(hour=0, minute=0, second=0, microsecond=0)


def assert_turn_in_budget(turn_index: int, max_turns: int | None = None) -> None:
    cap = max_turns if max_turns is not None else resolve_max_turns()
    if turn_index < 0:
        raise TurnRefused(REASON_TURN_BUDGET)
    if turn_index >= cap:
        raise TurnRefused(REASON_TURN_BUDGET)


def assert_daily_tokens_in_budget(tokens_used_today: int, cap: int) -> None:
    """Refuse when today's harness token sum has already hit the cap."""
    if tokens_used_today < 0:
        raise TurnRefused(REASON_DAILY_CAP)
    if tokens_used_today >= cap:
        raise TurnRefused(REASON_DAILY_CAP)


def assert_composition(*, version: str | None = None) -> None:
    try:
        if version is None:
            verify()
        else:
            verify(version=version)
    except CompositionError as exc:
        raise TurnRefused(f"{REASON_COMPOSITION}: {exc}") from exc


async def harness_tokens_used_today(
    db: AsyncSession,
    project_id: UUID,
    *,
    now: datetime | None = None,
    notes: str = SESSION_NOTES,
) -> int:
    """Σ tokens_used on today's harness_session_turn ComputeDebit rows.

    The existing ledger is the meter — a process restart does not reset
    this sum. Rows whose notes start with ``harness_session_turn`` count
    (``record_compute_debit`` may append a rate-fallback suffix). Other
    project spend (agent-pass debits) does not. Window is UTC midnight
    inclusive through now.
    """
    start = utc_day_start(now)
    result = await db.execute(
        select(func.coalesce(func.sum(ComputeDebit.tokens_used), 0)).where(
            ComputeDebit.project_id == project_id,
            ComputeDebit.created_at >= start,
            ComputeDebit.notes.startswith(notes),
        )
    )
    return int(result.scalar_one() or 0)


async def assert_daily_token_cap(
    db: AsyncSession,
    project_id: UUID,
    cap: int,
    *,
    now: datetime | None = None,
    notes: str = SESSION_NOTES,
) -> None:
    """Refuse before the LLM call when today's harness spend has hit ``cap``."""
    used = await harness_tokens_used_today(db, project_id, now=now, notes=notes)
    assert_daily_tokens_in_budget(used, cap)


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
    ``ComputeDebit`` (spend, including the daily token cap). Turn index
    is process-local — a restart starts a new bound session at turn 0.
    Today's harness token sum does not reset. No schema, no second
    campaign table, no ``AgentRun``.
    """

    project_id: UUID | str
    turn_index: int = 0
    max_turns: int | None = None
    daily_token_cap: int | None = None
    session_factory: async_sessionmaker[AsyncSession] | None = None
    env: Mapping[str, str] | None = None
    notes: str = SESSION_NOTES
    extras: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.project_id = _as_project_id(self.project_id)
        if self.max_turns is None:
            self.max_turns = resolve_max_turns(self.env)
        if self.daily_token_cap is None:
            self.daily_token_cap = resolve_daily_token_cap(self.env)

    @property
    def project_uuid(self) -> UUID:
        return self.project_id if isinstance(self.project_id, UUID) else UUID(str(self.project_id))

    def resolved_max_turns(self) -> int:
        return self.max_turns if self.max_turns is not None else resolve_max_turns(self.env)

    def resolved_daily_token_cap(self) -> int:
        if self.daily_token_cap is not None:
            return self.daily_token_cap
        return resolve_daily_token_cap(self.env)

    def _factory(self) -> async_sessionmaker[AsyncSession]:
        if self.session_factory is not None:
            return self.session_factory
        from app.db.session import AsyncSessionLocal

        return AsyncSessionLocal

    async def authorize(self) -> None:
        """Refuse before the LLM call on drift, turn cap, daily cap, or pot."""
        assert_composition()
        assert_turn_in_budget(self.turn_index, self.resolved_max_turns())
        factory = self._factory()
        async with factory() as db:
            await assert_daily_token_cap(
                db,
                self.project_uuid,
                self.resolved_daily_token_cap(),
                notes=self.notes,
            )
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
        factory = self._factory()
        async with factory() as db:
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
