"""OpenRouter client (0.12.0) — DB-free and network-free via ``httpx.MockTransport``.

Exercises the real request/parse path against a canned transport: a success returns text +
``tokens_used``; every failure mode (timeout, non-2xx, missing key, malformed/empty body) raises the
typed :class:`AgentLlmError` so a route can map it to ``422``/``503`` — never a ``500``.
"""

import httpx
import pytest

from app.agent.llm import AgentLlmError, OpenRouterClient

_OK_BODY = {
    "choices": [{"message": {"content": '{"runs": []}'}}],
    "usage": {"total_tokens": 123},
}


def _client(handler) -> OpenRouterClient:
    return OpenRouterClient(api_key="test-key", transport=httpx.MockTransport(handler))


async def test_complete_returns_text_and_tokens() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_OK_BODY)

    resp = await _client(handler).complete(
        model="test/model", messages=[{"role": "user", "content": "hi"}]
    )
    assert resp.text == '{"runs": []}'
    assert resp.tokens_used == 123
    assert resp.model == "test/model"


async def test_timeout_raises_agent_llm_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    with pytest.raises(AgentLlmError):
        await _client(handler).complete(model="m", messages=[], timeout=0.01)


async def test_non_2xx_raises_agent_llm_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    with pytest.raises(AgentLlmError):
        await _client(handler).complete(model="m", messages=[])


async def test_missing_key_raises_before_any_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("a request was made despite the missing key")

    # api_key="" is falsy → fail fast, regardless of any OPENROUTER_API_KEY in the dev .env.
    client = OpenRouterClient(
        api_key="", base_url="https://x", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(AgentLlmError):
        await client.complete(model="m", messages=[])


async def test_malformed_body_raises_agent_llm_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})  # no choices[0]

    with pytest.raises(AgentLlmError):
        await _client(handler).complete(model="m", messages=[])


async def test_empty_content_raises_agent_llm_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "  "}}]})

    with pytest.raises(AgentLlmError):
        await _client(handler).complete(model="m", messages=[])
