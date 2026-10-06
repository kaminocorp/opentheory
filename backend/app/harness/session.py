"""Session owner for an external DeepSeek Harness run (0.43.0 / 0.51.0).

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
``OPENTHEORY_HARNESS_DAILY_TOKEN_CAP`` (default 20_000).

``0.47.0`` closes the leftover 0.46.0 race: two in-flight turns could
both pass the unlocked sum and both debit past the cap.
``authorize()`` takes the project row ``FOR UPDATE``, then appends a
remaining-room hold on the existing ``ComputeDebit`` ledger (amount
``0`` — not a pot debit). The second concurrent authorize sees the
hold in today's sum and refuses. After the model call the hold is
released by a new credit row (append-only; never an edit) and the
real spend is recorded when ``tokens_used > 0``.

``0.48.0`` closes the leftover crash pin: a hold whose convert never
ran used to occupy the remaining room until UTC midnight. Hold notes
now carry a ``hold_id``. The next ``authorize()`` — still under the
project-row lock — appends a matching release for an unmatched hold
older than ``OPENTHEORY_HARNESS_HOLD_TTL_SECONDS`` (default 300) and
only then takes a new hold. A fresh in-flight hold is not released.

``0.50.0`` closes the leftover single-turn overshoot: the hold still
occupies remaining daily tokens (the 0.47/0.48 race close), and also
carries a ``clamp`` — ``min(daily room, pot room)`` when pot room
was applied (funded + live/catalog price). Pot dollars convert at
the completion rate, or ``max(prompt, completion)`` when both are
known — ``max_tokens`` bounds completion tokens, billed at the
completion rate. Prompt cost is not reserved. Unfunded and
unknown-price turns have no pot room and clamp to the daily room
(never an invented blended rate). The gateway sets ``max_tokens``
to that clamp. A room below
``OPENTHEORY_HARNESS_TURN_TOKEN_FLOOR`` (default 16) is
``TurnRefused``. Provider usage above the clamp is recorded in full
and flagged.

``0.51.0`` does not reserve the pot: the 0.50 hold already occupies
the whole remaining daily room, so a second overlapping authorize
on the same project is always refused. The real hole is a live turn
that outlives ``OPENTHEORY_HARNESS_HOLD_TTL_SECONDS`` — the next
authorize would release that hold as an orphan. Composition /
session startup refuse when the TTL is not strictly greater than
the provider request timeout (``AGENT_LLM_TIMEOUT_S``, default 60)
plus a margin (5s). ``GatewayClient.complete`` wraps the whole
provider call (post + body read) in a total deadline of that
timeout — a per-phase httpx timeout is not enough, and ``stream``
is 422 before authorize. An abandoned request may still be billed
by OpenRouter; usage is unknown so we debit nothing. No campaign
table.

``0.52.0`` closes the leftover membership gap on this spend path.
``authorize()`` resolves the actor the session / turn is running
for (``actor_env``, else ``env`` — the same JWT-file / JWT /
flagged ``OPENTHEORY_DEV_ACTOR_ID`` injection ``live_mcp`` uses)
and calls ``ensure_is_member`` *before* any hold write or
provider call. A missing credential, a non-member, or an
account-less actor (including the built-in ``Research crew``)
is ``TurnRefused``: no hold, no debit, no OpenRouter call.
``record_spend`` does not re-check. Membership is a start-of-turn
gate (same as pot / daily cap / floor). Tokens that moved after
a successful authorize are billed — a mid-turn removal does not
erase the pot. The next authorize fails closed. No schema.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.pricing import PriceQuote, quote_model_price
from app.harness.composition import CompositionError, verify
from app.models.compute_debit import ComputeDebit
from app.models.enums import ComputeDebitKind, ComputeDebitRateSource
from app.models.project import Project
from app.services import compute as compute_service
from app.services import funding as funding_service
from app.services.harness_meter import (
    DAILY_TOKEN_CAP_ENV,
    DEFAULT_DAILY_TOKEN_CAP,
    DEFAULT_HOLD_TTL_SECONDS,
    DEFAULT_TURN_TIMEOUT_SECONDS,
    DEFAULT_TURN_TOKEN_FLOOR,
    HOLD_ID_MARK,
    HOLD_NOTES,
    HOLD_NOTES_MARK,
    HOLD_TTL_ENV,
    RELEASE_NOTES,
    RELEASE_NOTES_MARK,
    SESSION_NOTES,
    TURN_DURATION_MARGIN_SECONDS,
    TURN_TIMEOUT_ENV,
    TURN_TOKEN_FLOOR_ENV,
    AdjustmentRow,
    clamp_max_tokens,
    clamp_rate_per_1k,
    harness_notes_prefix_match,
    harness_tokens_used_today,
    hold_notes,
    hold_ttl_covers_turn,
    is_daily_cap_adjustment,
    is_hold_stale,
    load_today_adjustments,
    max_turn_duration_seconds,
    overshoot_tokens,
    parse_hold_id,
    pot_tokens_from_available,
    price_is_known,
    release_notes,
    spend_notes,
    turn_clamp,
    unmatched_holds,
    utc_day_start,
)

PROJECT_ID_ENV = "OPENTHEORY_PROJECT_ID"
MAX_TURNS_ENV = "OPENTHEORY_HARNESS_MAX_TURNS"
DEFAULT_MAX_TURNS = 4
REASON_COMPOSITION = "composition drifted"
REASON_TURN_BUDGET = "turn budget exhausted"
REASON_DAILY_CAP = "daily token cap exhausted"
REASON_TURN_ROOM = "turn room below floor"
REASON_HOLD_TTL = "hold TTL does not exceed turn duration"
REASON_PROJECT_BUDGET = compute_service.BUDGET_EXHAUSTED
REASON_ACTOR = "actor required"
REASON_NOT_MEMBER = "not a project member"

__all__ = [
    "DAILY_TOKEN_CAP_ENV",
    "DEFAULT_DAILY_TOKEN_CAP",
    "DEFAULT_HOLD_TTL_SECONDS",
    "DEFAULT_MAX_TURNS",
    "DEFAULT_TURN_TIMEOUT_SECONDS",
    "DEFAULT_TURN_TOKEN_FLOOR",
    "HOLD_ID_MARK",
    "HOLD_NOTES",
    "HOLD_NOTES_MARK",
    "HOLD_TTL_ENV",
    "MAX_TURNS_ENV",
    "PROJECT_ID_ENV",
    "REASON_COMPOSITION",
    "REASON_DAILY_CAP",
    "REASON_PROJECT_BUDGET",
    "REASON_TURN_BUDGET",
    "REASON_ACTOR",
    "REASON_HOLD_TTL",
    "REASON_NOT_MEMBER",
    "REASON_TURN_ROOM",
    "RELEASE_NOTES",
    "RELEASE_NOTES_MARK",
    "SESSION_NOTES",
    "TURN_DURATION_MARGIN_SECONDS",
    "TURN_TIMEOUT_ENV",
    "TURN_TOKEN_FLOOR_ENV",
    "AdjustmentRow",
    "DailyCapHold",
    "HarnessSession",
    "TurnRefused",
    "assert_daily_token_cap",
    "assert_daily_tokens_in_budget",
    "assert_project_budget",
    "assert_turn_in_budget",
    "assert_hold_ttl_covers_turn",
    "assert_turn_member",
    "assert_turn_room_above_floor",
    "clamp_max_tokens",
    "clamp_rate_per_1k",
    "harness_notes_prefix_match",
    "harness_tokens_used_today",
    "hold_has_release",
    "hold_notes",
    "is_daily_cap_adjustment",
    "is_hold_stale",
    "hold_ttl_covers_turn",
    "load_today_adjustments",
    "max_turn_duration_seconds",
    "overshoot_tokens",
    "parse_hold_id",
    "pot_tokens_from_available",
    "price_is_known",
    "release_notes",
    "release_stale_holds",
    "resolve_daily_token_cap",
    "resolve_hold_ttl_seconds",
    "resolve_max_turns",
    "resolve_turn_timeout_seconds",
    "resolve_turn_token_floor",
    "session_from_env",
    "spend_notes",
    "turn_clamp",
    "unmatched_holds",
    "utc_day_start",
    "write_daily_cap_adjustment",
]


class TurnRefused(Exception):
    """The turn did not start. No LLM call, no debit, no mint."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class DailyCapHold:
    """Remaining-room hold taken by ``authorize()`` before the model call.

    Expressed as a ``ComputeDebit`` row whose notes start with
    ``harness_session_turn`` so today's cap sum sees it. ``tokens`` is
    the held remainder (``cap − used``) — the 0.47/0.48 race close.
    Amount on that row is ``0`` — this is not a project-pot debit.
    Release is a new credit row, never an edit. ``hold_id`` is written
    into the notes so a later authorize can release only this hold
    when it is stale — not a live turn.

    ``clamp`` is the honest ``max_tokens`` bound for this turn:
    ``min(daily_room, pot_room)`` when pot room was applied (funded
    project + known live/catalog price), otherwise the daily room.
    ``pot_room is None`` means it was not applied — unfunded, or
    price unknown. Pot dollars convert at the completion rate (or
    ``max(prompt, completion)``). Prompt cost is not reserved.
    The blended settings rate is not used.
    """

    tokens: int
    hold_id: UUID
    clamp: int
    daily_room: int
    pot_room: int | None = None
    price_known: bool = False


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


def resolve_hold_ttl_seconds(env: Mapping[str, str] | None = None) -> int:
    """Unmatched-hold TTL. Default 300s. ``< 1`` stays fail-closed (never auto-release)."""
    lookup = env if env is not None else os.environ
    raw = (lookup.get(HOLD_TTL_ENV) or "").strip()
    if not raw:
        return DEFAULT_HOLD_TTL_SECONDS
    try:
        value = int(raw)
    except ValueError as exc:
        raise TurnRefused(f"{HOLD_TTL_ENV} must be an integer") from exc
    if value < 1:
        raise TurnRefused(f"{HOLD_TTL_ENV} must be >= 1")
    return value


def resolve_turn_timeout_seconds(env: Mapping[str, str] | None = None) -> float:
    """Provider request timeout. Same source ``GatewayClient`` uses (default 60s)."""
    lookup = env if env is not None else os.environ
    raw = (lookup.get(TURN_TIMEOUT_ENV) or "").strip()
    if not raw:
        from app.core.config import settings

        return float(settings.agent_llm_timeout_s)
    try:
        value = float(raw)
    except ValueError as exc:
        raise TurnRefused(f"{TURN_TIMEOUT_ENV} must be a number") from exc
    if value <= 0:
        raise TurnRefused(f"{TURN_TIMEOUT_ENV} must be > 0")
    return value


def assert_hold_ttl_covers_turn(
    ttl_seconds: int,
    provider_timeout_s: float | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> None:
    """Refuse when a live turn could outlive the hold and be released as an orphan."""
    timeout = (
        provider_timeout_s
        if provider_timeout_s is not None
        else resolve_turn_timeout_seconds(env)
    )
    if hold_ttl_covers_turn(ttl_seconds, timeout):
        return
    needed = max_turn_duration_seconds(timeout)
    raise TurnRefused(
        f"{REASON_HOLD_TTL}: {HOLD_TTL_ENV}={ttl_seconds}s must be > "
        f"{timeout:g}s + {TURN_DURATION_MARGIN_SECONDS:g}s "
        f"({needed:g}s)"
    )


def resolve_turn_token_floor(env: Mapping[str, str] | None = None) -> int:
    """Minimum honest room before a provider call. Default 16."""
    lookup = env if env is not None else os.environ
    raw = (lookup.get(TURN_TOKEN_FLOOR_ENV) or "").strip()
    if not raw:
        return DEFAULT_TURN_TOKEN_FLOOR
    try:
        value = int(raw)
    except ValueError as exc:
        raise TurnRefused(f"{TURN_TOKEN_FLOOR_ENV} must be an integer") from exc
    if value < 1:
        raise TurnRefused(f"{TURN_TOKEN_FLOOR_ENV} must be >= 1")
    return value


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


def assert_turn_room_above_floor(room: int, floor: int) -> None:
    """Refuse when the remaining room cannot complete a turn honestly."""
    if room < floor:
        raise TurnRefused(REASON_TURN_ROOM)


def assert_composition(
    *,
    version: str | None = None,
    env: Mapping[str, str] | None = None,
) -> None:
    try:
        if version is None:
            verify()
        else:
            verify(version=version)
    except CompositionError as exc:
        raise TurnRefused(f"{REASON_COMPOSITION}: {exc}") from exc
    assert_hold_ttl_covers_turn(
        resolve_hold_ttl_seconds(env),
        env=env,
    )


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


async def _lock_project(db: AsyncSession, project_id: UUID) -> Project | None:
    """Serialize concurrent daily-cap authorizes on this project."""
    result = await db.execute(select(Project).where(Project.id == project_id).with_for_update())
    return result.scalar_one_or_none()


async def write_daily_cap_adjustment(
    db: AsyncSession,
    project_id: UUID,
    *,
    tokens_used: int,
    notes: str,
) -> None:
    """Append a hold or release row. Amount is 0 — not a pot debit. Does not commit."""
    db.add(
        ComputeDebit(
            project_id=project_id,
            tokens_used=tokens_used,
            amount=Decimal("0"),
            currency="USD",
            rate_per_1k=Decimal("0"),
            rate_source=ComputeDebitRateSource.BLENDED_FALLBACK,
            kind=ComputeDebitKind.PLANNING,
            notes=notes,
        )
    )
    await db.flush()


async def hold_has_release(
    db: AsyncSession,
    project_id: UUID,
    hold_id: UUID,
    *,
    now: datetime | None = None,
    notes: str = SESSION_NOTES,
) -> bool:
    """True when a release credit for ``hold_id`` already sits on today's ledger."""
    for row in await load_today_adjustments(db, project_id, now=now, notes=notes):
        text = row.notes or ""
        if RELEASE_NOTES_MARK in text and parse_hold_id(text) == hold_id:
            return True
    return False


async def release_stale_holds(
    db: AsyncSession,
    project_id: UUID,
    *,
    ttl_seconds: int,
    now: datetime | None = None,
    notes: str = SESSION_NOTES,
) -> list[UUID | None]:
    """Append release credits for unmatched holds older than ``ttl_seconds``.

    Does not commit. Caller already holds the project row. Fresh unmatched
    holds are left in place so a live overlapping authorize still refuses.
    """
    released: list[UUID | None] = []
    rows = await load_today_adjustments(db, project_id, now=now, notes=notes)
    for hold in unmatched_holds(rows):
        if not is_hold_stale(hold.created_at, ttl_seconds=ttl_seconds, now=now):
            continue
        hold_id = parse_hold_id(hold.notes)
        await write_daily_cap_adjustment(
            db,
            project_id,
            tokens_used=-hold.tokens_used,
            notes=release_notes(hold_id),
        )
        released.append(hold_id)
    return released


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


async def assert_turn_member(
    db: AsyncSession,
    project_id: UUID,
    env: Mapping[str, str] | None,
) -> None:
    """Refuse before a hold when the acting actor is not a current member.

    Uses the existing helpers: ``resolve_mcp_actor`` (JWT file / JWT /
    flagged dev-actor) then ``ensure_is_member`` (account membership;
    account-less is ``403``). Mapped to ``TurnRefused`` so the gateway
    stays 422 with no provider call, no hold, and no debit. A missing
    credential is fail-closed — there is no "project-bound so skip"
    escape. Does not write.
    """
    from fastapi import HTTPException

    from app.harness.auth import load_credential, resolve_mcp_actor
    from app.services.project_members import ensure_is_member

    if load_credential(env) is None:
        raise TurnRefused(REASON_ACTOR)
    try:
        actor = await resolve_mcp_actor(db, env)
        await ensure_is_member(db, project_id, actor)
    except HTTPException as exc:
        if exc.status_code == 401:
            raise TurnRefused(REASON_ACTOR) from exc
        raise TurnRefused(REASON_NOT_MEMBER) from exc


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
    ``ComputeDebit`` (spend, including the daily token cap, the 0.47.0
    remaining-room hold / release pair, the 0.48.0 stale-hold
    release, the 0.50.0 turn-room clamp, and the 0.51.0 hold-TTL
    bound). Turn index is process-local — a restart starts a
    new bound session at turn 0. Today's harness token sum does not
    reset. No schema, no second campaign table, no ``AgentRun``.
    """

    project_id: UUID | str
    turn_index: int = 0
    max_turns: int | None = None
    daily_token_cap: int | None = None
    hold_ttl_seconds: int | None = None
    turn_token_floor: int | None = None
    session_factory: async_sessionmaker[AsyncSession] | None = None
    env: Mapping[str, str] | None = None
    actor_env: Mapping[str, str] | None = None
    notes: str = SESSION_NOTES
    extras: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.project_id = _as_project_id(self.project_id)
        if self.max_turns is None:
            self.max_turns = resolve_max_turns(self.env)
        if self.daily_token_cap is None:
            self.daily_token_cap = resolve_daily_token_cap(self.env)
        if self.hold_ttl_seconds is None:
            self.hold_ttl_seconds = resolve_hold_ttl_seconds(self.env)
        if self.turn_token_floor is None:
            self.turn_token_floor = resolve_turn_token_floor(self.env)
        assert_hold_ttl_covers_turn(
            self.resolved_hold_ttl_seconds(),
            env=self.env,
        )

    @property
    def project_uuid(self) -> UUID:
        return self.project_id if isinstance(self.project_id, UUID) else UUID(str(self.project_id))

    def resolved_max_turns(self) -> int:
        return self.max_turns if self.max_turns is not None else resolve_max_turns(self.env)

    def resolved_daily_token_cap(self) -> int:
        if self.daily_token_cap is not None:
            return self.daily_token_cap
        return resolve_daily_token_cap(self.env)

    def resolved_hold_ttl_seconds(self) -> int:
        if self.hold_ttl_seconds is not None:
            return self.hold_ttl_seconds
        return resolve_hold_ttl_seconds(self.env)

    def resolved_turn_token_floor(self) -> int:
        if self.turn_token_floor is not None:
            return self.turn_token_floor
        return resolve_turn_token_floor(self.env)

    def _actor_lookup(self) -> Mapping[str, str] | None:
        """Actor the session / turn is running for.

        ``actor_env`` wins (``supervise_turn`` MCP credentials). Else
        ``env`` (campaign / gateway process — operator-supplied JWT
        file or flagged dev-actor, same injection as ``live_mcp``).
        """
        if self.actor_env is not None:
            return self.actor_env
        return self.env

    def _factory(self) -> async_sessionmaker[AsyncSession]:
        if self.session_factory is not None:
            return self.session_factory
        from app.db.session import AsyncSessionLocal

        return AsyncSessionLocal

    async def authorize(
        self,
        *,
        model: str | None = None,
        quote: PriceQuote | None = None,
    ) -> DailyCapHold | None:
        """Refuse before the LLM call on drift, membership, turn cap, daily cap, pot, or floor.

        Membership is first among the DB checks: resolve the acting
        actor and ``ensure_is_member`` before the project-row lock,
        stale-hold release, or remaining-room hold. A non-member or
        account-less actor cannot take a hold or call the provider.

        On a pass, locks the project row, releases unmatched holds older
        than the TTL, re-reads today's harness token sum (holds
        included), computes the turn clamp, and appends a remaining-room
        hold so a second concurrent authorize cannot also pass. The
        ledger hold occupies remaining daily tokens (0.47/0.48 / 0.50).
        ``clamp`` is ``min(daily room, pot room)`` when the project is
        funded and ``quote`` (or a live/catalog fetch for ``model``)
        is a known price; pot dollars convert at the completion rate
        (or ``max(prompt, completion)``). Unfunded and unknown-price
        turns clamp to the daily room alone. Prompt cost is not
        reserved. Returns the hold the caller must convert
        (``record_spend``) or release.
        """
        assert_composition(env=self.env)
        assert_turn_in_budget(self.turn_index, self.resolved_max_turns())
        resolved_quote = quote
        if resolved_quote is None and model:
            resolved_quote = await quote_model_price(model)
        factory = self._factory()
        async with factory() as db:
            await assert_turn_member(db, self.project_uuid, self._actor_lookup())
            project = await _lock_project(db, self.project_uuid)
            cap = self.resolved_daily_token_cap()
            await release_stale_holds(
                db,
                self.project_uuid,
                ttl_seconds=self.resolved_hold_ttl_seconds(),
                notes=self.notes,
            )
            used = await harness_tokens_used_today(
                db,
                self.project_uuid,
                notes=self.notes,
            )
            assert_daily_tokens_in_budget(used, cap)
            await assert_project_budget(db, self.project_uuid)
            if project is None:
                return None
            daily_room = cap - used
            if daily_room < 1:
                raise TurnRefused(REASON_DAILY_CAP)
            pot_room: int | None = None
            known = False
            if resolved_quote is not None and price_is_known(resolved_quote.source):
                known = True
                budget = await funding_service.project_budget(db, self.project_uuid)
                if budget.funded > 0:
                    pot_room = pot_tokens_from_available(
                        budget.available,
                        clamp_rate_per_1k(
                            effective_rate_per_1k=resolved_quote.effective_rate_per_1k,
                            prompt_rate_per_1k=resolved_quote.prompt_rate_per_1k,
                            completion_rate_per_1k=resolved_quote.completion_rate_per_1k,
                        ),
                    )
            clamp = turn_clamp(daily_room=daily_room, pot_room=pot_room)
            assert_turn_room_above_floor(clamp, self.resolved_turn_token_floor())
            hold_id = uuid4()
            await write_daily_cap_adjustment(
                db,
                self.project_uuid,
                tokens_used=daily_room,
                notes=hold_notes(hold_id),
            )
            await db.commit()
            return DailyCapHold(
                tokens=daily_room,
                hold_id=hold_id,
                clamp=clamp,
                daily_room=daily_room,
                pot_room=pot_room,
                price_known=known,
            )

    async def release_hold(self, hold: DailyCapHold | None) -> None:
        """Append the release credit for ``hold``. No-op when nothing is held."""
        if hold is None or hold.tokens <= 0:
            return
        factory = self._factory()
        async with factory() as db:
            await _lock_project(db, self.project_uuid)
            already = await hold_has_release(
                db, self.project_uuid, hold.hold_id, notes=self.notes
            )
            if not already:
                await write_daily_cap_adjustment(
                    db,
                    self.project_uuid,
                    tokens_used=-hold.tokens,
                    notes=release_notes(hold.hold_id),
                )
            await db.commit()

    async def record_spend(
        self,
        *,
        tokens_used: int,
        model: str | None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        notes: str | None = None,
        hold: DailyCapHold | None = None,
    ) -> bool:
        """Debit tokens that moved. ``tokens_used <= 0`` writes no spend row.

        When ``hold`` is present, the matching release credit is appended
        in the same transaction — convert, do not edit the hold. The
        project row is locked so a concurrent stale-hold recovery cannot
        write a second release for the same ``hold_id``.

        Does not re-check membership. ``authorize()`` is the gate: a
        member removed mid-turn does not drop a debit for tokens that
        already moved (pot honesty). The next authorize refuses.
        """
        if tokens_used <= 0 and hold is None:
            return False
        factory = self._factory()
        async with factory() as db:
            if hold is not None and hold.tokens > 0:
                await _lock_project(db, self.project_uuid)
                if not await hold_has_release(
                    db,
                    self.project_uuid,
                    hold.hold_id,
                    notes=self.notes,
                ):
                    await write_daily_cap_adjustment(
                        db,
                        self.project_uuid,
                        tokens_used=-hold.tokens,
                        notes=release_notes(hold.hold_id),
                    )
            debit = None
            if tokens_used > 0:
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
        actor_env=lookup,
    )
