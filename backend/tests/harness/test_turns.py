"""Turn supervision (0.42.0) — composition/turn-cap refuses; no ledger required."""

from __future__ import annotations

import json

import httpx
import pytest

from app.harness.composition import VERSION, CompositionError
from app.harness.gateway import GatewayClient
from app.harness.turns import (
    DEFAULT_MAX_TURNS,
    REASON_COMPOSITION,
    REASON_TURN_BUDGET,
    SupervisedTurn,
    assert_composition,
    assert_turn_in_budget,
    resolve_max_turns,
    supervise_session,
    supervise_turn,
)

_OK_BODY = {
    "choices": [{"message": {"content": "pong"}}],
    "usage": {"total_tokens": 7, "prompt_tokens": 5, "completion_tokens": 2},
}


def _gateway(handler) -> GatewayClient:
    return GatewayClient(
        api_key="sk-test",
        base_url="https://openrouter.ai/api/v1",
        transport=httpx.MockTransport(handler),
    )


def test_default_max_turns_is_bounded() -> None:
    assert resolve_max_turns({}) == DEFAULT_MAX_TURNS == 4
    assert_turn_in_budget(0, max_turns=4)
    assert_turn_in_budget(3, max_turns=4)
    with pytest.raises(Exception, match=REASON_TURN_BUDGET):
        assert_turn_in_budget(4, max_turns=4)


def test_composition_ok_on_authored_patch() -> None:
    assert_composition()
    assert VERSION == "0.1.5rc1"


def test_composition_drift_refuses_before_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.harness import turns as turns_mod

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise CompositionError("disabled plugin inventory drifted")

    monkeypatch.setattr(turns_mod, "verify", _boom)

    class _Boom(GatewayClient):
        async def complete(self, **_kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("gateway must not be called after composition drift")

    import asyncio

    result = asyncio.run(
        supervise_turn(
            messages=[{"role": "user", "content": "hi"}],
            gateway=_Boom(
                api_key="sk-test",
                base_url="https://openrouter.ai/api/v1",
            ),
        )
    )
    assert isinstance(result, SupervisedTurn)
    assert result.refused is True
    assert result.ok is False
    assert result.debit_recorded is False
    assert result.minted is False
    assert REASON_COMPOSITION in (result.reason or "")


async def test_successful_turn_without_project_does_not_debit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["provider"]["allow_fallbacks"] is False
        return httpx.Response(200, json=_OK_BODY)

    result = await supervise_turn(
        messages=[{"role": "user", "content": "ping"}],
        gateway=_gateway(handler),
    )
    assert result.ok is True
    assert result.refused is False
    assert result.tokens_used == 7
    assert result.text == "pong"
    assert result.debit_recorded is False
    assert result.minted is False


async def test_turn_cap_refuses_without_calling_gateway() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("turn cap must refuse before the LLM call")

    result = await supervise_turn(
        messages=[{"role": "user", "content": "hi"}],
        turn_index=4,
        max_turns=4,
        gateway=_gateway(handler),
    )
    assert result.refused is True
    assert result.reason == REASON_TURN_BUDGET
    assert result.tokens_used == 0
    assert result.minted is False


async def test_session_stops_when_turn_cap_hit() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_OK_BODY)

    results = await supervise_session(
        [
            {"messages": [{"role": "user", "content": "a"}]},
            {"messages": [{"role": "user", "content": "b"}]},
            {"messages": [{"role": "user", "content": "c"}]},
        ],
        max_turns=2,
        gateway=_gateway(handler),
    )
    assert len(results) == 3
    assert results[0].ok is True
    assert results[1].ok is True
    assert results[2].refused is True
    assert results[2].reason == REASON_TURN_BUDGET
    assert calls["n"] == 2


async def test_attempted_turn_reports_tokens_on_empty_completion() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": ""}}],
                "usage": {"total_tokens": 11, "prompt_tokens": 10, "completion_tokens": 1},
            },
        )

    result = await supervise_turn(
        messages=[{"role": "user", "content": "hi"}],
        gateway=_gateway(handler),
    )
    assert result.ok is False
    assert result.refused is False
    assert result.tokens_used == 11
    assert result.minted is False
    assert result.checkpoint_id is None
