"""Live OpenRouter price metering (0.28.0) — DB-free, network-free via ``httpx.MockTransport``.

Covers the four acceptance bars: live prompt/completion billing, honest blended
fallback, process cache + TTL, and a short timeout that never raises into the
caller. CI never touches the live network.
"""

from decimal import Decimal

import httpx
import pytest

from app.agent.pricing import (
    REASON_API_KEY_MISSING,
    REASON_FETCH_FAILED,
    REASON_LIVE_PRICES_DISABLED,
    REASON_MODEL_UNKNOWN,
    REASON_TIMEOUT,
    OpenRouterPriceClient,
    PriceQuote,
    blended_fallback_quote,
    live_quote,
    parse_models_catalog,
    quote_model_price,
    reset_price_cache,
    usage_to_cost,
)
from app.core.config import settings
from app.core.openrouter_models import ModelOption
from app.models.enums import ComputeDebitRateSource

_MODEL = "anthropic/claude-sonnet-4"
_PROMPT_PER_TOKEN = "0.000003"  # → $0.003 / 1k
_COMPLETION_PER_TOKEN = "0.000015"  # → $0.015 / 1k


def _models_body(*ids: str) -> dict:
    return {
        "data": [
            {
                "id": model_id,
                "pricing": {
                    "prompt": _PROMPT_PER_TOKEN,
                    "completion": _COMPLETION_PER_TOKEN,
                },
            }
            for model_id in ids
        ]
    }


@pytest.fixture(autouse=True)
def _isolate_price_cache() -> None:
    reset_price_cache()
    yield
    reset_price_cache()


@pytest.fixture
def live_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openrouter_live_prices", True)
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "openrouter_price_cache_ttl_s", 3600.0)
    monkeypatch.setattr(settings, "openrouter_price_timeout_s", 2.0)
    monkeypatch.setattr(settings, "agent_token_rate_usd_per_1k", Decimal("0.005"))


def _client(handler, *, api_key: str = "test-key", **kwargs) -> OpenRouterPriceClient:
    return OpenRouterPriceClient(
        api_key=api_key,
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def test_parse_models_catalog_converts_per_token_usd_to_per_1k() -> None:
    catalog = parse_models_catalog(_models_body(_MODEL))
    rate = catalog[_MODEL]
    assert rate.prompt_per_1k == Decimal("0.003000")
    assert rate.completion_per_1k == Decimal("0.015000")
    assert rate.mean_per_1k == Decimal("0.009000")


def test_usage_to_cost_bills_prompt_and_completion_separately() -> None:
    quote = live_quote(
        _MODEL,
        parse_models_catalog(_models_body(_MODEL))[_MODEL],
    )
    # 1000 prompt @ $0.003 + 2000 completion @ $0.015 = 0.003 + 0.030 = 0.033
    assert usage_to_cost(
        tokens_used=3000,
        prompt_tokens=1000,
        completion_tokens=2000,
        quote=quote,
    ) == Decimal("0.033000")


def test_usage_to_cost_bills_unknown_split_at_the_live_mean() -> None:
    quote = live_quote(
        _MODEL,
        parse_models_catalog(_models_body(_MODEL))[_MODEL],
    )
    # 1000 tokens @ mean $0.009
    assert usage_to_cost(
        tokens_used=1000,
        prompt_tokens=None,
        completion_tokens=None,
        quote=quote,
    ) == Decimal("0.009000")


def test_usage_to_cost_bills_reasoning_remainder_at_completion_rate() -> None:
    quote = live_quote(
        _MODEL,
        parse_models_catalog(_models_body(_MODEL))[_MODEL],
    )
    # 800 prompt @ 0.003 + (200 completion + 100 remainder) @ 0.015
    # = 0.0024 + 0.0045 = 0.0069
    assert usage_to_cost(
        tokens_used=1100,
        prompt_tokens=800,
        completion_tokens=200,
        quote=quote,
    ) == Decimal("0.006900")


def test_usage_to_cost_falls_back_to_blended_rate() -> None:
    quote = PriceQuote(
        source=ComputeDebitRateSource.BLENDED_FALLBACK,
        effective_rate_per_1k=Decimal("0.005"),
        fallback_reason=REASON_API_KEY_MISSING,
        model=_MODEL,
    )
    assert usage_to_cost(
        tokens_used=1000,
        prompt_tokens=400,
        completion_tokens=600,
        quote=quote,
    ) == Decimal("0.005000")


async def test_quote_uses_live_prompt_and_completion_rates(live_on: None) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        assert request.url.path.endswith("/models")
        return httpx.Response(200, json=_models_body(_MODEL))

    quote = await quote_model_price(_MODEL, client=_client(handler))
    assert quote.source is ComputeDebitRateSource.OPENROUTER_LIVE
    assert quote.prompt_rate_per_1k == Decimal("0.003000")
    assert quote.completion_rate_per_1k == Decimal("0.015000")
    assert quote.effective_rate_per_1k == Decimal("0.009000")
    assert quote.fallback_reason is None
    assert calls["n"] == 1


async def test_quote_falls_back_when_api_key_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_live_prices", True)
    monkeypatch.setattr(settings, "openrouter_api_key", None)
    monkeypatch.setattr(settings, "agent_token_rate_usd_per_1k", Decimal("0.123"))

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("a price fetch ran despite the missing key")

    quote = await quote_model_price(
        _MODEL, client=_client(handler, api_key="")
    )
    assert quote.source is ComputeDebitRateSource.BLENDED_FALLBACK
    assert quote.effective_rate_per_1k == Decimal("0.123")
    assert quote.fallback_reason == REASON_API_KEY_MISSING
    assert quote.prompt_rate_per_1k is None


async def test_quote_falls_back_when_live_prices_are_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openrouter_live_prices", False)
    monkeypatch.setattr(settings, "agent_token_rate_usd_per_1k", Decimal("0.005"))

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("a price fetch ran while live prices were disabled")

    quote = await quote_model_price(_MODEL, client=_client(handler))
    assert quote.source is ComputeDebitRateSource.BLENDED_FALLBACK
    assert quote.fallback_reason == REASON_LIVE_PRICES_DISABLED


async def test_quote_falls_back_on_timeout(live_on: None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    quote = await quote_model_price(_MODEL, client=_client(handler, timeout=0.01))
    assert quote.source is ComputeDebitRateSource.BLENDED_FALLBACK
    assert quote.fallback_reason == REASON_TIMEOUT
    assert quote.effective_rate_per_1k == Decimal("0.005")


async def test_quote_falls_back_on_fetch_failure(live_on: None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    quote = await quote_model_price(_MODEL, client=_client(handler))
    assert quote.source is ComputeDebitRateSource.BLENDED_FALLBACK
    assert quote.fallback_reason == REASON_FETCH_FAILED


async def test_quote_falls_back_when_model_is_missing_from_catalog(live_on: None) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_models_body("openai/gpt-4o"))

    quote = await quote_model_price(_MODEL, client=_client(handler))
    assert quote.source is ComputeDebitRateSource.BLENDED_FALLBACK
    assert quote.fallback_reason == REASON_MODEL_UNKNOWN


async def test_catalog_is_cached_within_ttl(live_on: None) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_models_body(_MODEL))

    client = _client(handler)
    first = await quote_model_price(_MODEL, client=client)
    second = await quote_model_price(_MODEL, client=client)
    assert first.is_live and second.is_live
    assert calls["n"] == 1


async def test_catalog_refetches_after_ttl(
    live_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"n": 0}
    now = {"t": 100.0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_models_body(_MODEL))

    monkeypatch.setattr("app.agent.pricing._now", lambda: now["t"])
    monkeypatch.setattr(settings, "openrouter_price_cache_ttl_s", 10.0)

    client = _client(handler)
    await quote_model_price(_MODEL, client=client)
    now["t"] = 111.0
    await quote_model_price(_MODEL, client=client)
    assert calls["n"] == 2


async def test_stale_cache_is_used_when_refresh_fails(
    live_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"n": 0}
    now = {"t": 100.0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json=_models_body(_MODEL))
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr("app.agent.pricing._now", lambda: now["t"])
    monkeypatch.setattr(settings, "openrouter_price_cache_ttl_s", 10.0)

    client = _client(handler)
    first = await quote_model_price(_MODEL, client=client)
    assert first.is_live and not first.stale
    now["t"] = 111.0
    second = await quote_model_price(_MODEL, client=client)
    assert second.source is ComputeDebitRateSource.OPENROUTER_LIVE
    assert second.stale is True
    assert second.prompt_rate_per_1k == Decimal("0.003000")


async def test_catalog_override_beats_settings_on_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "agent_token_rate_usd_per_1k", Decimal("0.005"))
    override = ModelOption(
        "test/override", "Override", "Test", usd_per_1k=Decimal("9.99")
    )
    monkeypatch.setattr("app.agent.pricing.OPENROUTER_MODELS", (override,))
    quote = blended_fallback_quote("test/override", reason=REASON_API_KEY_MISSING)
    assert quote.source is ComputeDebitRateSource.CATALOG_OVERRIDE
    assert quote.effective_rate_per_1k == Decimal("9.99")
    assert quote.fallback_reason == REASON_API_KEY_MISSING
