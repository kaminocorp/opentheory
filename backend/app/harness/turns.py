"""Turn supervision for the external DeepSeek Harness path (0.42.0).

A supervised turn: fail-closed composition check → project budget check →
one OpenRouter completion through :class:`GatewayClient` → ``ComputeDebit``
for tokens that moved → optional live MCP dispatch through the existing
``run_instrument`` / ``create_checkpoint`` door.

Bounds:
- ``OPENTHEORY_HARNESS_MAX_TURNS`` (default 4). Crossing it refuses.
- Composition drift refuses (``composition.verify``).
- A funded pot with ``available <= 0`` refuses before the LLM call.

Debit uses :func:`app.services.compute.record_compute_debit` — the same
writer the built-in planner uses. Harness turns have no ``AgentRun`` (this
path does not light ``AGENT_LOOP_ENABLED``), so ``agent_run_id`` is left
null and ``notes`` carry ``harness_gateway_turn``. Tokens that moved are
always billed, including an attempted completion that then failed to parse.
A refused start (drift / exhausted / turn cap) writes nothing: no tokens
moved.

Exceptions still mint nothing. The MCP door is the only ledger writer.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.harness.composition import CompositionError, verify
from app.harness.gateway import (
    DEFAULT_MODEL,
    GatewayClient,
    GatewayError,
    GatewayResponse,
    resolve_model,
)
from app.models.enums import ComputeDebitKind
from app.services import compute as compute_service
from app.services import funding as funding_service

TURN_NOTES = "harness_gateway_turn"
MAX_TURNS_ENV = "OPENTHEORY_HARNESS_MAX_TURNS"
DEFAULT_MAX_TURNS = 4
REASON_COMPOSITION = "composition drifted"
REASON_TURN_BUDGET = "turn budget exhausted"
REASON_PROJECT_BUDGET = compute_service.BUDGET_EXHAUSTED


class TurnRefused(Exception):
    """The turn did not start. No LLM call, no debit, no mint."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class SupervisedTurn:
    """Outcome of one supervised turn. ``minted`` is only true after a chokepoint commit."""

    ok: bool
    refused: bool
    reason: str | None
    tokens_used: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    model: str | None = None
    text: str | None = None
    debit_recorded: bool = False
    minted: bool = False
    checkpoint_id: str | None = None
    mcp: dict[str, Any] | None = None
    turn_index: int = 0
    extras: dict[str, Any] = field(default_factory=dict)


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


async def _record_harness_debit(
    db: AsyncSession,
    *,
    project_id: UUID,
    tokens_used: int,
    model: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    notes: str | None = None,
) -> bool:
    debit = await compute_service.record_compute_debit(
        db,
        project_id=project_id,
        tokens_used=tokens_used,
        model=model,
        kind=ComputeDebitKind.PLANNING,
        notes=notes or TURN_NOTES,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    await db.commit()
    return debit is not None


async def supervise_turn(
    *,
    messages: list[dict[str, Any]],
    project_id: UUID | str | None = None,
    model: str | None = None,
    turn_index: int = 0,
    max_turns: int | None = None,
    mcp_call: dict[str, Any] | None = None,
    gateway: GatewayClient | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    actor_env: Mapping[str, str] | None = None,
    env: Mapping[str, str] | None = None,
    max_tokens: int | None = 64,
) -> SupervisedTurn:
    """Run one bounded, metered, fail-closed turn.

    ``mcp_call`` is ``{"name": "run_instrument", "arguments": {...}}`` and is
    dispatched only after a successful completion. A gateway exception
    never reaches the MCP door (exceptions mint nothing) but still
    records a debit when tokens moved.
    """
    try:
        assert_composition()
        cap = max_turns if max_turns is not None else resolve_max_turns(env)
        assert_turn_in_budget(turn_index, cap)
        resolved_model = resolve_model(model, env=env)
    except (TurnRefused, GatewayError) as exc:
        reason = exc.reason if isinstance(exc, TurnRefused) else str(exc)
        return SupervisedTurn(
            ok=False, refused=True, reason=reason, model=model, turn_index=turn_index
        )

    project_uuid: UUID | None = None
    if project_id is not None and str(project_id):
        project_uuid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))

    factory = session_factory
    if project_uuid is not None:
        if factory is None:
            from app.db.session import AsyncSessionLocal

            factory = AsyncSessionLocal
        async with factory() as db:
            try:
                await assert_project_budget(db, project_uuid)
            except TurnRefused as exc:
                return SupervisedTurn(
                    ok=False,
                    refused=True,
                    reason=exc.reason,
                    model=resolved_model,
                    turn_index=turn_index,
                )

    client = gateway or GatewayClient(env=env)
    response: GatewayResponse | None = None
    error: GatewayError | None = None
    try:
        response = await client.complete(
            model=resolved_model,
            messages=messages,
            max_tokens=max_tokens,
        )
    except GatewayError as exc:
        error = exc

    tokens_used = (
        response.tokens_used if response is not None else (error.tokens_used if error else 0)
    )
    prompt_tokens = (
        response.prompt_tokens if response is not None else (error.prompt_tokens if error else None)
    )
    completion_tokens = (
        response.completion_tokens
        if response is not None
        else (error.completion_tokens if error else None)
    )

    debit_recorded = False
    if project_uuid is not None and tokens_used > 0 and factory is not None:
        async with factory() as db:
            debit_recorded = await _record_harness_debit(
                db,
                project_id=project_uuid,
                tokens_used=tokens_used,
                model=resolved_model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

    if error is not None:
        return SupervisedTurn(
            ok=False,
            refused=False,
            reason=str(error),
            tokens_used=tokens_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=resolved_model,
            debit_recorded=debit_recorded,
            minted=False,
            checkpoint_id=None,
            turn_index=turn_index,
        )

    assert response is not None
    mcp_result: dict[str, Any] | None = None
    minted = False
    checkpoint_id: str | None = None
    if mcp_call is not None:
        from app.harness.live_mcp import invoke

        name = str(mcp_call.get("name") or "")
        arguments = mcp_call.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        mcp_result = await invoke(
            name,
            arguments,
            session_factory=factory,
            env=actor_env,
        )
        minted = bool(mcp_result.get("minted"))
        raw_checkpoint = mcp_result.get("checkpoint_id")
        checkpoint_id = str(raw_checkpoint) if raw_checkpoint else None

    return SupervisedTurn(
        ok=True,
        refused=False,
        reason=None,
        tokens_used=response.tokens_used,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        model=response.model,
        text=response.text,
        debit_recorded=debit_recorded,
        minted=minted,
        checkpoint_id=checkpoint_id,
        mcp=mcp_result,
        turn_index=turn_index,
    )


async def supervise_session(
    turns: list[dict[str, Any]],
    *,
    max_turns: int | None = None,
    **kwargs: Any,
) -> list[SupervisedTurn]:
    """Run a bounded sequence of :func:`supervise_turn` calls. Stops on refuse."""
    cap = max_turns if max_turns is not None else resolve_max_turns(kwargs.get("env"))
    results: list[SupervisedTurn] = []
    for index, spec in enumerate(turns):
        if index >= cap:
            results.append(
                SupervisedTurn(
                    ok=False,
                    refused=True,
                    reason=REASON_TURN_BUDGET,
                    turn_index=index,
                    model=spec.get("model") or kwargs.get("model") or DEFAULT_MODEL,
                )
            )
            break
        result = await supervise_turn(
            messages=spec["messages"],
            project_id=spec.get("project_id", kwargs.get("project_id")),
            model=spec.get("model", kwargs.get("model")),
            turn_index=index,
            max_turns=cap,
            mcp_call=spec.get("mcp_call"),
            gateway=kwargs.get("gateway"),
            session_factory=kwargs.get("session_factory"),
            actor_env=kwargs.get("actor_env"),
            env=kwargs.get("env"),
            max_tokens=spec.get("max_tokens", kwargs.get("max_tokens", 64)),
        )
        results.append(result)
        if result.refused:
            break
    return results
