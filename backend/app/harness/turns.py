"""Turn supervision library for the external DeepSeek Harness path.

``0.42.0`` shipped these helpers; ``0.43.0`` keeps them as a library
tests and a no-``dsh`` driver can call. ``0.44.0`` fails closed on the
authored composition: ``dsh → llm-pi-ai`` launches
``python -m app.harness.campaign``, which refuses when unbound. The
session owner remains :class:`~app.harness.session.HarnessSession`,
wired into ``create_gateway_app``. A project-scoped
:func:`supervise_turn` composes that owner rather than minting a
parallel debit path.

A supervised turn: fail-closed composition check → project budget check →
one OpenRouter completion through :class:`GatewayClient` → ``ComputeDebit``
for tokens that moved → optional live MCP dispatch through the existing
``run_instrument`` / ``create_checkpoint`` door.

Bounds:
- ``OPENTHEORY_HARNESS_MAX_TURNS`` (default 4). Crossing it refuses.
  Process-local — a restart starts at turn 0.
- ``OPENTHEORY_HARNESS_DAILY_TOKEN_CAP`` (default 20_000 tokens / UTC
  day). Counted from today's ``ComputeDebit`` rows whose notes start
  with ``harness_session_turn``. Survives a process restart. A
  remaining-room hold (0.47.0) is appended under the project-row lock
  so two overlapping authorizes cannot both pass and both debit past
  the cap. An unmatched hold older than the TTL (0.48.0) is released
  on the next authorize so a crash after authorize does not pin the
  UTC day.
- Composition drift refuses (``composition.verify``).
- A funded pot with ``available <= 0`` refuses before the LLM call.

Debit uses :func:`app.services.compute.record_compute_debit` — the same
writer the built-in planner uses. Harness turns have no ``AgentRun`` (this
path does not light ``AGENT_LOOP_ENABLED``), so ``agent_run_id`` is left
null and ``notes`` carry ``harness_session_turn``. Tokens that moved are
always billed, including an attempted completion that then failed to parse.
A refused start (drift / exhausted / turn cap / daily cap / room below
floor / hold TTL) writes nothing: no tokens moved. ``0.50.0`` clamps
the completion ``max_tokens`` to the authorize room and records a
provider overshoot when usage exceeds that clamp. The 0.50 hold
already occupies the whole remaining daily room, so a second
overlapping authorize is refused. ``0.51.0`` keeps that occupancy
and refuses composition / session / gateway start when the hold
TTL is not strictly greater than the provider request timeout plus
a margin — a live turn must never be released as an orphan.

Exceptions still mint nothing. The MCP door is the only ledger writer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.harness.gateway import (
    DEFAULT_MODEL,
    GatewayClient,
    GatewayError,
    GatewayResponse,
    resolve_model,
)
from app.harness.session import (
    DEFAULT_MAX_TURNS,
    MAX_TURNS_ENV,
    REASON_COMPOSITION,
    REASON_PROJECT_BUDGET,
    REASON_TURN_BUDGET,
    SESSION_NOTES,
    DailyCapHold,
    HarnessSession,
    TurnRefused,
    assert_project_budget,
    assert_turn_in_budget,
    clamp_max_tokens,
    overshoot_tokens,
    resolve_max_turns,
    spend_notes,
)
from app.harness.session import (
    assert_composition as assert_session_composition,
)

TURN_NOTES = SESSION_NOTES

__all__ = [
    "DEFAULT_MAX_TURNS",
    "MAX_TURNS_ENV",
    "REASON_COMPOSITION",
    "REASON_PROJECT_BUDGET",
    "REASON_TURN_BUDGET",
    "SESSION_NOTES",
    "TURN_NOTES",
    "HarnessSession",
    "SupervisedTurn",
    "TurnRefused",
    "assert_composition",
    "assert_project_budget",
    "assert_turn_in_budget",
    "resolve_max_turns",
    "supervise_session",
    "supervise_turn",
]


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
    clamp: int | None = None
    overshoot: int = 0
    price_known: bool | None = None
    extras: dict[str, Any] = field(default_factory=dict)


def assert_composition(
    *,
    version: str | None = None,
    env: Mapping[str, str] | None = None,
) -> None:
    assert_session_composition(version=version, env=env)


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
        assert_composition(env=env)
        cap = max_turns if max_turns is not None else resolve_max_turns(env)
        assert_turn_in_budget(turn_index, cap)
        resolved_model = resolve_model(model, env=env)
    except (TurnRefused, GatewayError) as exc:
        reason = exc.reason if isinstance(exc, TurnRefused) else str(exc)
        return SupervisedTurn(
            ok=False, refused=True, reason=reason, model=model, turn_index=turn_index
        )

    owner: HarnessSession | None = None
    hold: DailyCapHold | None = None
    factory = session_factory
    if project_id is not None and str(project_id):
        owner = HarnessSession(
            project_id=project_id,
            turn_index=turn_index,
            max_turns=cap,
            session_factory=session_factory,
            env=env,
        )
        factory = owner.session_factory or session_factory
        try:
            hold = await owner.authorize(model=resolved_model)
        except TurnRefused as exc:
            return SupervisedTurn(
                ok=False,
                refused=True,
                reason=exc.reason,
                model=resolved_model,
                turn_index=turn_index,
            )

    bound_max = clamp_max_tokens(max_tokens, hold.clamp) if hold is not None else max_tokens
    client = gateway or GatewayClient(env=env)
    response: GatewayResponse | None = None
    error: GatewayError | None = None
    try:
        response = await client.complete(
            model=resolved_model,
            messages=messages,
            max_tokens=bound_max,
        )
    except GatewayError as exc:
        error = exc
    except Exception:
        if owner is not None and hold is not None:
            await owner.release_hold(hold)
        raise

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
    clamp = hold.clamp if hold is not None else None
    overshoot = overshoot_tokens(tokens_used, hold.clamp) if hold is not None else 0
    price_known = hold.price_known if hold is not None else None
    if owner is not None:
        debit_recorded = await owner.record_spend(
            tokens_used=tokens_used,
            model=resolved_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            notes=(
                spend_notes(
                    clamp=hold.clamp,
                    overshoot=overshoot,
                    price_known=hold.price_known,
                    pot_room=hold.pot_room,
                )
                if hold is not None
                else None
            ),
            hold=hold,
        )
        owner.advance()

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
            clamp=clamp,
            overshoot=overshoot,
            price_known=price_known,
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
        clamp=clamp,
        overshoot=overshoot,
        price_known=price_known,
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
