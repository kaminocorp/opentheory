"""OpenRouter chat-completions client for the thin agent loop (0.12.0).

The planner (0.12.1) needs exactly one thing from an LLM: turn a prompt into text (a JSON plan),
with token usage recorded. This module isolates that single outbound call behind a small
:class:`OpenRouterClient`, deliberately mirroring the retrieval
:class:`~app.toolbench.retrieval.Fetcher` posture:

- a typed :class:`AgentLlmError` for *every* failure mode (missing key, down provider, timeout,
  non-2xx, empty/malformed body) so a route maps it to ``422``/``503`` — **never a ``500``**;
- a thin :class:`LlmClient` ``Protocol`` so the planner takes an injectable ``llm`` (a ``StubLlm``
  in tests) and CI never touches the live network — tests inject an ``httpx.MockTransport`` to
  exercise the real request/parse path with a canned response.

Research crew is *config only* today — nothing in the backend calls OpenRouter — so this is the
first LLM client in the codebase. Settings live in ``core/config.py`` (the ``agent_*`` /
``openrouter_*`` group); the key is a Fly secret, never ``fly.toml [env]``.

On token caps: ``agent_pass_max_tokens`` is a *budget/usage* ceiling — recorded on each pass but
**not yet enforced** (a comparison against ``usage.total_tokens`` lands with the project-level
budget in 0.12.5; the single planning call is meanwhile bounded by ``agent_llm_timeout_s`` and the
planner's own completion cap). It is also **not** the request's ``max_tokens`` (200k completion
tokens would be rejected by most providers). So this client only sends ``max_tokens`` when a caller
passes one explicitly; the planner picks a sane completion budget.
"""

from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.config import settings


class AgentLlmError(Exception):
    """The planning call did not yield usable content.

    Raised for a missing key, a network error, a timeout, a non-2xx status, or an empty/malformed
    body. The orchestrator records it on the ``AgentRun`` trace and mints nothing; a route surfaces
    it as a ``422``/``503`` — a provider hiccup is never an internal server error.

    ``tokens_used`` carries any spend that *did* occur before the failure — a completion that
    returned but parsed badly still cost tokens, so the planner attaches them here for an honest
    trace. It is ``0`` when nothing completed (a missing key, a timeout, a down provider).
    """

    def __init__(self, message: str, *, tokens_used: int = 0) -> None:
        super().__init__(message)
        self.tokens_used = tokens_used


@dataclass(frozen=True)
class LlmResponse:
    """One successful completion: the raw text content, tokens consumed, and the model that ran."""

    text: str
    tokens_used: int
    model: str


class LlmClient(Protocol):
    """The single method the planner depends on — a ``StubLlm`` substitutes trivially in tests."""

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
        timeout: float | None = None,
        max_tokens: int | None = None,
    ) -> LlmResponse: ...


class OpenRouterClient:
    """An async OpenRouter ``/chat/completions`` client with typed failure.

    ``transport`` is an injection seam: tests pass an ``httpx.MockTransport`` to drive the real
    request/parse path with a canned response and no network. ``api_key`` / ``base_url`` default to
    the configured settings, so production constructs it argument-free.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.openrouter_api_key
        self._base_url = (base_url or settings.openrouter_base_url).rstrip("/")
        self._transport = transport

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
        timeout: float | None = None,
        max_tokens: int | None = None,
    ) -> LlmResponse:
        """POST one completion request → :class:`LlmResponse`, or raise :class:`AgentLlmError`."""
        if not self._api_key:
            # A misconfigured deployment (no key) is a clean, legible failure — not a 500 at request
            # time. The dark-launch flag should keep the routes 404 until the key is set, so this is
            # a belt-and-braces guard for direct service/test use.
            raise AgentLlmError("OpenRouter API key is not configured")

        payload: dict[str, Any] = {"model": model, "messages": messages}
        if response_format is not None:
            payload["response_format"] = response_format
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        effective_timeout = timeout if timeout is not None else settings.agent_llm_timeout_s
        try:
            async with httpx.AsyncClient(
                timeout=effective_timeout, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            raise AgentLlmError(
                f"OpenRouter request timed out after {effective_timeout}s"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise AgentLlmError(
                f"OpenRouter returned {exc.response.status_code}"
            ) from exc
        except Exception as exc:  # any transport/JSON-decode failure is one "provider unavailable"
            raise AgentLlmError(f"OpenRouter request failed: {exc}") from exc

        try:
            text = data["choices"][0]["message"]["content"]
            tokens_used = int(data.get("usage", {}).get("total_tokens", 0) or 0)
        except (KeyError, IndexError, TypeError) as exc:
            raise AgentLlmError("OpenRouter response missing choices[0].message.content") from exc

        if not isinstance(text, str) or not text.strip():
            raise AgentLlmError("OpenRouter returned empty content")

        return LlmResponse(text=text, tokens_used=tokens_used, model=model)
