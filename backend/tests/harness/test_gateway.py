"""Fail-closed OpenRouter gateway (0.42.0) — DB-free, no live key, no dsh."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.harness.gateway import (
    DEFAULT_MODEL,
    DEFAULT_PROVIDERS,
    FAIL_CLOSED_ALLOW_FALLBACKS,
    FAIL_CLOSED_DATA_COLLECTION,
    FAIL_CLOSED_REQUIRE_PARAMETERS,
    GATEWAY_TOKEN_ENV,
    GatewayClient,
    GatewayError,
    assert_openrouter_base_url,
    build_fail_closed_body,
    create_gateway_app,
    provider_preferences,
    resolve_model,
    resolve_providers,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]

_OK_BODY = {
    "choices": [{"message": {"content": "pong"}}],
    "usage": {"total_tokens": 12, "prompt_tokens": 8, "completion_tokens": 4},
}


def _client(handler, **kwargs) -> GatewayClient:
    return GatewayClient(
        api_key="sk-test",
        base_url="https://openrouter.ai/api/v1",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def test_fail_closed_provider_knobs() -> None:
    prefs = provider_preferences()
    assert prefs["only"] == list(DEFAULT_PROVIDERS)
    assert prefs["allow_fallbacks"] is FAIL_CLOSED_ALLOW_FALLBACKS is False
    assert prefs["require_parameters"] is FAIL_CLOSED_REQUIRE_PARAMETERS is True
    assert prefs["data_collection"] == FAIL_CLOSED_DATA_COLLECTION == "deny"


def test_body_overwrites_client_provider_block() -> None:
    body = build_fail_closed_body(
        model=DEFAULT_MODEL,
        messages=[{"role": "user", "content": "hi"}],
        extra={
            "provider": {
                "allow_fallbacks": True,
                "data_collection": "allow",
                "only": [],
            },
            "temperature": 0,
        },
    )
    assert body["provider"]["allow_fallbacks"] is False
    assert body["provider"]["require_parameters"] is True
    assert body["provider"]["data_collection"] == "deny"
    assert body["provider"]["only"] == ["DeepSeek"]
    assert body["temperature"] == 0
    assert body["model"] == DEFAULT_MODEL


def test_unknown_model_is_refused() -> None:
    with pytest.raises(GatewayError, match="not in the OpenTheory OpenRouter catalog"):
        resolve_model("deepseek/not-a-real-model")


def test_non_deepseek_model_refused_on_default_allowlist() -> None:
    with pytest.raises(GatewayError, match="outside provider allowlist"):
        resolve_model("anthropic/claude-sonnet-4")


def test_widened_allowlist_accepts_catalog_vendor() -> None:
    assert (
        resolve_model(
            "anthropic/claude-sonnet-4",
            env={"OPENTHEORY_GATEWAY_PROVIDERS": "Anthropic,DeepSeek"},
        )
        == "anthropic/claude-sonnet-4"
    )


def test_empty_providers_env_refuses() -> None:
    with pytest.raises(GatewayError, match="empty"):
        resolve_providers({"OPENTHEORY_GATEWAY_PROVIDERS": " , "})


def test_raw_deepseek_api_is_forbidden() -> None:
    with pytest.raises(GatewayError, match="raw DeepSeek API"):
        assert_openrouter_base_url("https://api.deepseek.com/v1")


def test_non_openrouter_host_is_forbidden() -> None:
    with pytest.raises(GatewayError, match="not OpenRouter"):
        assert_openrouter_base_url("https://example.com/v1")


def test_openrouter_base_url_is_accepted() -> None:
    assert assert_openrouter_base_url("https://openrouter.ai/api/v1") == (
        "https://openrouter.ai/api/v1"
    )


async def test_complete_sends_fail_closed_payload() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        assert "api.deepseek.com" not in seen["url"]
        return httpx.Response(200, json=_OK_BODY)

    resp = await _client(handler).complete(
        model=DEFAULT_MODEL,
        messages=[{"role": "user", "content": "ping"}],
        extra={"provider": {"allow_fallbacks": True}},
    )
    assert resp.text == "pong"
    assert resp.tokens_used == 12
    assert resp.prompt_tokens == 8
    assert resp.completion_tokens == 4
    assert seen["body"]["provider"]["allow_fallbacks"] is False
    assert seen["body"]["provider"]["require_parameters"] is True
    assert seen["body"]["provider"]["data_collection"] == "deny"
    assert seen["body"]["provider"]["only"] == ["DeepSeek"]
    assert seen["url"].startswith("https://openrouter.ai/")


async def test_missing_key_raises_before_any_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("a request was made despite the missing key")

    client = GatewayClient(
        api_key="",
        base_url="https://openrouter.ai/api/v1",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(GatewayError, match="not configured"):
        await client.complete(model=DEFAULT_MODEL, messages=[])


async def test_empty_content_still_reports_tokens() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "  "}}],
                "usage": {"total_tokens": 9, "prompt_tokens": 6, "completion_tokens": 3},
            },
        )

    with pytest.raises(GatewayError) as exc:
        await _client(handler).complete(model=DEFAULT_MODEL, messages=[])
    assert exc.value.tokens_used == 9
    assert exc.value.prompt_tokens == 6
    assert exc.value.completion_tokens == 3


async def test_http_gateway_requires_token_and_overwrites_provider() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["provider"]["allow_fallbacks"] is False
        return httpx.Response(200, json=_OK_BODY)

    env = {GATEWAY_TOKEN_ENV: "gw-secret"}
    app = create_gateway_app(env=env, gateway=_client(handler, env=env))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://gw") as client:
        denied = await client.post(
            "/v1/chat/completions",
            json={"model": DEFAULT_MODEL, "messages": [{"role": "user", "content": "hi"}]},
        )
        assert denied.status_code == 422

        ok = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer gw-secret"},
            json={
                "model": DEFAULT_MODEL,
                "messages": [{"role": "user", "content": "hi"}],
                "provider": {"allow_fallbacks": True, "data_collection": "allow"},
            },
        )
        assert ok.status_code == 200
        payload = ok.json()
        assert payload["choices"][0]["message"]["content"] == "pong"
        assert payload["usage"]["total_tokens"] == 12


def test_fastapi_boot_path_still_ignores_harness() -> None:
    for rel in ("app/main.py", "app/api/router.py"):
        source = (BACKEND_ROOT / rel).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("app.harness"), rel
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("app.harness"), rel


def test_fly_toml_env_has_no_secrets() -> None:
    text = (BACKEND_ROOT / "fly.toml").read_text(encoding="utf-8")
    assigned: list[str] = []
    in_env = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "[env]":
            in_env = True
            continue
        if in_env and stripped.startswith("["):
            break
        if not in_env or not stripped or stripped.startswith("#"):
            continue
        key = stripped.split("=", 1)[0].strip().upper()
        assigned.append(key)
    for secret in (
        "OPENROUTER_API_KEY",
        "OPENTHEORY_GATEWAY_TOKEN",
        "OPENTHEORY_ACTOR_JWT",
        "DATABASE_URL",
        "AGENT_LOOP_ENABLED",
    ):
        assert secret not in assigned, secret
