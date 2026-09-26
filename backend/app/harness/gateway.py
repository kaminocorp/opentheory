"""Fail-closed OpenRouter gateway for the external DeepSeek Harness (0.42.0).

Mirrors the OpenWorld gateway posture named in ``docs/harness/prior-art.md``:
provider allowlist, ``allow_fallbacks: false``, ``require_parameters: true``,
``data_collection: deny``. Traffic goes to OpenRouter only — never the raw
DeepSeek API. Secrets come from the environment / secrets manager; they must
never land in ``fly.toml [env]``.

This module is **not** imported by ``app.main`` or ``api/router.py``. It does
not flip ``AGENT_LOOP_ENABLED``. The built-in planner's ``OpenRouterClient``
is a different owner of the session and is left untouched.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.openrouter_models import OPENROUTER_MODELS, VALID_MODEL_IDS
from app.harness.auth import redact

VERSION = "0.42.0"
DEFAULT_MODEL = "deepseek/deepseek-chat"
DEFAULT_PROVIDERS: tuple[str, ...] = ("DeepSeek",)
ALLOWED_OPENROUTER_HOSTS = frozenset({"openrouter.ai", "www.openrouter.ai"})
FORBIDDEN_UPSTREAM_HOSTS = frozenset(
    {
        "api.deepseek.com",
        "deepseek.com",
        "www.deepseek.com",
    }
)
GATEWAY_TOKEN_ENV = "OPENTHEORY_GATEWAY_TOKEN"
OPENROUTER_KEY_ENV = "OPENROUTER_API_KEY"
MODEL_ENV = "OPENTHEORY_MODEL"
PROVIDERS_ENV = "OPENTHEORY_GATEWAY_PROVIDERS"
GATEWAY_URL_ENV = "OPENTHEORY_GATEWAY_URL"

# OpenRouter extra_body knobs. Names are load-bearing — tests assert the exact payload.
FAIL_CLOSED_ALLOW_FALLBACKS = False
FAIL_CLOSED_REQUIRE_PARAMETERS = True
FAIL_CLOSED_DATA_COLLECTION = "deny"


class GatewayError(Exception):
    """The fail-closed completion did not yield usable content.

    Raised for a missing key, a forbidden upstream, a model outside the
    allowlist, a network error, or an empty/malformed body. ``tokens_used``
    carries spend that *did* occur before the failure so a supervisor can
    still debit — a parsed-but-empty completion still cost tokens.
    """

    def __init__(
        self,
        message: str,
        *,
        tokens_used: int = 0,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
    ) -> None:
        super().__init__(message)
        self.tokens_used = tokens_used
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


@dataclass(frozen=True)
class GatewayResponse:
    """One successful fail-closed completion."""

    text: str
    tokens_used: int
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


def resolve_providers(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Provider allowlist. Empty is refuse, not "any provider"."""
    lookup = env if env is not None else os.environ
    raw = (lookup.get(PROVIDERS_ENV) or "").strip()
    if not raw:
        return DEFAULT_PROVIDERS
    providers = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not providers:
        raise GatewayError(f"{PROVIDERS_ENV} is empty — refuse rather than open the allowlist")
    return providers


def resolve_model(model: str | None = None, *, env: Mapping[str, str] | None = None) -> str:
    lookup = env if env is not None else os.environ
    chosen = (model or lookup.get(MODEL_ENV) or DEFAULT_MODEL).strip()
    if not chosen:
        raise GatewayError("model is required")
    if chosen not in VALID_MODEL_IDS:
        raise GatewayError(f"model {chosen!r} is not in the OpenTheory OpenRouter catalog")
    providers = resolve_providers(lookup)
    option = next(item for item in OPENROUTER_MODELS if item.id == chosen)
    # Default allowlist is DeepSeek-only. A widened OPENTHEORY_GATEWAY_PROVIDERS
    # must still name the catalog vendor or we refuse — do not silently route
    # Claude through a DeepSeek-only strip (or the reverse).
    if option.provider not in providers:
        raise GatewayError(
            f"model {chosen!r} vendor {option.provider!r} is outside provider allowlist "
            f"{list(providers)}"
        )
    return chosen


def provider_preferences(providers: tuple[str, ...] | None = None) -> dict[str, Any]:
    """Exact OpenRouter ``provider`` object. Callers cannot weaken these knobs."""
    only = list(providers if providers is not None else resolve_providers())
    if not only:
        raise GatewayError("provider allowlist must be non-empty")
    return {
        "only": only,
        "allow_fallbacks": FAIL_CLOSED_ALLOW_FALLBACKS,
        "require_parameters": FAIL_CLOSED_REQUIRE_PARAMETERS,
        "data_collection": FAIL_CLOSED_DATA_COLLECTION,
    }


def assert_openrouter_base_url(base_url: str) -> str:
    """Refuse anything that is not OpenRouter — especially the raw DeepSeek API."""
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()
    if host in FORBIDDEN_UPSTREAM_HOSTS:
        raise GatewayError(f"raw DeepSeek API is forbidden ({host}); use OpenRouter")
    if host not in ALLOWED_OPENROUTER_HOSTS:
        raise GatewayError(f"upstream host {host!r} is not OpenRouter")
    if parsed.scheme not in {"https", "http"}:
        raise GatewayError("upstream URL must be http(s)")
    return base_url.rstrip("/")


def build_fail_closed_body(
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int | None = None,
    extra: dict[str, Any] | None = None,
    providers: tuple[str, ...] | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """OpenAI-compatible chat body with fail-closed ``provider`` always overwritten."""
    resolved = resolve_model(model, env=env)
    allowlist = providers if providers is not None else resolve_providers(env)
    body: dict[str, Any] = {
        "model": resolved,
        "messages": messages,
        "provider": provider_preferences(allowlist),
    }
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    if extra:
        # A caller (or the dsh child) must not be able to re-open fallbacks.
        sanitized = {key: value for key, value in extra.items() if key != "provider"}
        body.update(sanitized)
        body["provider"] = provider_preferences(allowlist)
    return body


class GatewayClient:
    """Async OpenRouter ``/chat/completions`` client with fail-closed extras.

    ``transport`` is the test injection seam (``httpx.MockTransport``). The
    API key defaults to ``settings.openrouter_api_key`` so production constructs
    this argument-free; tests pass an explicit key so a local ``.env`` cannot
    leak onto the network.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        if api_key is not None:
            self._api_key = api_key
        elif env is not None and (env.get(OPENROUTER_KEY_ENV) or "").strip():
            self._api_key = env[OPENROUTER_KEY_ENV].strip()
        else:
            self._api_key = settings.openrouter_api_key
        raw_base = base_url or settings.openrouter_base_url
        self._base_url = assert_openrouter_base_url(raw_base)
        self._transport = transport
        self._timeout = timeout if timeout is not None else settings.agent_llm_timeout_s
        self._env = env

    async def complete(
        self,
        *,
        model: str | None = None,
        messages: list[dict[str, Any]],
        max_tokens: int | None = None,
        extra: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> GatewayResponse:
        if not self._api_key:
            raise GatewayError("OpenRouter API key is not configured")
        payload = build_fail_closed_body(
            model=model or DEFAULT_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            extra=extra,
            env=self._env,
        )
        effective_timeout = timeout if timeout is not None else self._timeout
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
        except GatewayError:
            raise
        except httpx.TimeoutException as exc:
            raise GatewayError(f"OpenRouter request timed out after {effective_timeout}s") from exc
        except httpx.HTTPStatusError as exc:
            raise GatewayError(f"OpenRouter returned {exc.response.status_code}") from exc
        except Exception as exc:
            raise GatewayError(f"OpenRouter request failed: {exc}") from exc

        return _parse_completion(data, model=payload["model"])


def _parse_completion(data: Any, *, model: str) -> GatewayResponse:
    usage = (
        data.get("usage")
        if isinstance(data, dict) and isinstance(data.get("usage"), dict)
        else {}
    )
    prompt_tokens = _optional_int(usage.get("prompt_tokens"))
    completion_tokens = _optional_int(usage.get("completion_tokens"))
    tokens_used = int(usage.get("total_tokens", 0) or 0)
    if tokens_used <= 0 and prompt_tokens is not None:
        tokens_used = prompt_tokens + (completion_tokens or 0)
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GatewayError(
            "OpenRouter response missing choices[0].message.content",
            tokens_used=tokens_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        ) from exc
    if not isinstance(text, str) or not text.strip():
        raise GatewayError(
            "OpenRouter returned empty content",
            tokens_used=tokens_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    return GatewayResponse(
        text=text,
        tokens_used=tokens_used,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _require_gateway_token(
    headers: Mapping[str, str], *, env: Mapping[str, str] | None = None
) -> None:
    """Inbound HTTP auth. The child holds a gateway token, never the OpenRouter key."""
    lookup = env if env is not None else os.environ
    expected = (lookup.get(GATEWAY_TOKEN_ENV) or "").strip()
    if not expected:
        raise GatewayError(f"{GATEWAY_TOKEN_ENV} is not configured — HTTP gateway refuses")
    incoming = headers.get("authorization") or headers.get("Authorization") or ""
    if incoming.lower().startswith("bearer "):
        incoming = incoming[7:]
    if incoming.strip() != expected:
        raise GatewayError("gateway token mismatch")


def create_gateway_app(
    *,
    env: Mapping[str, str] | None = None,
    gateway: GatewayClient | None = None,
):
    """Standalone ASGI app the Cordis ``llm-pi-ai`` plugin can point at.

    Not mounted on the product FastAPI app. ``python -m app.harness.gateway``.
    ``gateway`` is the test injection seam (MockTransport client).
    """
    app = FastAPI(title="OpenTheory OpenRouter gateway", version=VERSION)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "ok": True,
            "version": VERSION,
            "fail_closed": True,
            "allow_fallbacks": FAIL_CLOSED_ALLOW_FALLBACKS,
            "require_parameters": FAIL_CLOSED_REQUIRE_PARAMETERS,
            "data_collection": FAIL_CLOSED_DATA_COLLECTION,
            "providers": list(resolve_providers(env)),
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> JSONResponse:
        try:
            _require_gateway_token(request.headers, env=env)
            raw = await request.json()
            if not isinstance(raw, dict):
                raise GatewayError("body must be a JSON object")
            model = raw.get("model")
            messages = raw.get("messages")
            if not isinstance(messages, list):
                raise GatewayError("messages must be a list")
            extra = {key: value for key, value in raw.items() if key not in {"model", "messages"}}
            client = gateway or GatewayClient(env=env)
            result = await client.complete(
                model=str(model) if model else None,
                messages=messages,
                max_tokens=extra.pop("max_tokens", None),
                extra=extra,
            )
        except GatewayError as exc:
            return JSONResponse(
                status_code=422,
                content=redact(
                    {
                        "error": str(exc),
                        "tokens_used": exc.tokens_used,
                        "minted": False,
                    }
                ),
            )
        return JSONResponse(
            {
                "id": "opentheory-gateway",
                "object": "chat.completion",
                "model": result.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": result.text},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                    "total_tokens": result.tokens_used,
                },
            }
        )

    return app


def main() -> None:
    import uvicorn

    host = os.environ.get("OPENTHEORY_GATEWAY_HOST", "127.0.0.1")
    port = int(os.environ.get("OPENTHEORY_GATEWAY_PORT", "8787"))
    uvicorn.run(create_gateway_app(), host=host, port=port)


if __name__ == "__main__":
    main()
