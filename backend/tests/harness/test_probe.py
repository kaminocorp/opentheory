"""Probe skips live OpenRouter unless explicitly opted in with a key."""

from __future__ import annotations

import json

import httpx
import pytest

from app.harness.composition import VERSION
from app.harness.gateway import DEFAULT_MODEL, GatewayClient
from app.harness.probe import (
    LIVE_FLAG,
    OPENROUTER_KEY_ENV,
    live_probe_skip_reason,
    run_probe,
)


def test_probe_always_asserts_composition() -> None:
    report = run_probe()
    assert report.composition == "ok"
    assert report.fixture == "ok"
    assert report.skipped_live is True
    assert LIVE_FLAG in report.live


def test_live_skips_without_flag() -> None:
    reason = live_probe_skip_reason(
        {OPENROUTER_KEY_ENV: "sk-test"},
        dsh_on_path=True,
        sdk_importable=True,
    )
    assert reason is not None
    assert LIVE_FLAG in reason


def test_live_skips_without_key() -> None:
    reason = live_probe_skip_reason(
        {LIVE_FLAG: "1"},
        dsh_on_path=True,
        sdk_importable=True,
    )
    assert reason is not None
    assert OPENROUTER_KEY_ENV in reason


def test_live_openrouter_does_not_require_dsh() -> None:
    """The 0.42.0 gateway path is OT code — missing dsh is not a skip."""
    reason = live_probe_skip_reason(
        {LIVE_FLAG: "1", OPENROUTER_KEY_ENV: "sk-test"},
        dsh_on_path=False,
        sdk_importable=False,
    )
    assert reason is None


def test_live_opt_in_runs_fail_closed_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LIVE_FLAG, "1")
    monkeypatch.setenv(OPENROUTER_KEY_ENV, "sk-test")

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["provider"]["allow_fallbacks"] is False
        assert body["provider"]["require_parameters"] is True
        assert body["provider"]["data_collection"] == "deny"
        assert body["model"] == DEFAULT_MODEL
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "pong"}}],
                "usage": {"total_tokens": 3, "prompt_tokens": 2, "completion_tokens": 1},
            },
        )

    gateway = GatewayClient(
        api_key="sk-test",
        base_url="https://openrouter.ai/api/v1",
        transport=httpx.MockTransport(handler),
    )
    report = run_probe(live_gateway=gateway)
    assert report.skipped_live is False
    assert report.composition == "ok"
    assert report.fixture == "ok"
    assert "ok tokens=3" in report.live
    assert VERSION == "0.1.5rc1"


def test_live_opt_in_failure_is_honest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LIVE_FLAG, "1")
    monkeypatch.setenv(OPENROUTER_KEY_ENV, "sk-test")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "down"})

    gateway = GatewayClient(
        api_key="sk-test",
        base_url="https://openrouter.ai/api/v1",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(Exception, match="OpenRouter returned 503"):
        run_probe(live_gateway=gateway)
