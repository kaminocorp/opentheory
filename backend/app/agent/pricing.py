"""Live OpenRouter model prices for compute metering (0.28.0).

A pass should debit at the model's actual prompt / completion rates when the
price catalog is available, and fall back to the configured blended rate when
it is not. This module never raises into the orchestrator: a missing key, a
timeout, a non-2xx, or an unknown model becomes an honest
:class:`PriceQuote` with ``source != openrouter_live``. Metering is never
skipped.

The catalog is cached in-process with a TTL. A refresh uses
``settings.openrouter_price_timeout_s`` (default 2s) so a slow ``GET /models``
cannot stall a planning call. Tests inject an ``httpx.MockTransport`` and call
:func:`reset_price_cache` so CI never touches the live network.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import httpx

from app.core.config import settings
from app.core.openrouter_models import OPENROUTER_MODELS
from app.models.enums import ComputeDebitRateSource

# Matches ``ComputeDebit.amount`` / rate columns.
_AMOUNT_QUANTUM = Decimal("0.000001")
_PER_TOKEN_TO_1K = Decimal("1000")

# Stable fallback reasons snapshotted onto the debit (notes + tests).
REASON_LIVE_PRICES_DISABLED = "live_prices_disabled"
REASON_API_KEY_MISSING = "openrouter_api_key_missing"
REASON_TIMEOUT = "openrouter_price_timeout"
REASON_FETCH_FAILED = "openrouter_price_fetch_failed"
REASON_MODEL_UNKNOWN = "model_not_in_openrouter_catalog"
REASON_EMPTY_CATALOG = "openrouter_price_catalog_empty"


@dataclass(frozen=True)
class ModelRate:
    """USD per 1 000 tokens, split the way OpenRouter bills."""

    prompt_per_1k: Decimal
    completion_per_1k: Decimal

    @property
    def mean_per_1k(self) -> Decimal:
        raw = (self.prompt_per_1k + self.completion_per_1k) / Decimal("2")
        return raw.quantize(_AMOUNT_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PriceQuote:
    """The rate decision for one debit — live, catalog override, or blended fallback."""

    source: ComputeDebitRateSource
    effective_rate_per_1k: Decimal
    prompt_rate_per_1k: Decimal | None = None
    completion_rate_per_1k: Decimal | None = None
    fallback_reason: str | None = None
    model: str | None = None
    stale: bool = False

    @property
    def is_live(self) -> bool:
        return self.source is ComputeDebitRateSource.OPENROUTER_LIVE


@dataclass
class _CatalogCache:
    models: dict[str, ModelRate]
    fetched_at: float


_cache: _CatalogCache | None = None


def reset_price_cache() -> None:
    """Drop the process cache. Tests call this so one case cannot leak into the next."""
    global _cache
    _cache = None


def _now() -> float:
    return time.monotonic()


def _per_token_to_per_1k(value: Any) -> Decimal | None:
    """OpenRouter ``pricing.prompt`` / ``completion`` are USD-per-token strings."""
    if value is None or value == "":
        return None
    try:
        per_token = Decimal(str(value))
    except Exception:
        return None
    if per_token < 0:
        return None
    return (per_token * _PER_TOKEN_TO_1K).quantize(_AMOUNT_QUANTUM, rounding=ROUND_HALF_UP)


def parse_models_catalog(payload: Any) -> dict[str, ModelRate]:
    """Extract ``{model_id: ModelRate}`` from an OpenRouter ``GET /models`` body."""
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {}
    out: dict[str, ModelRate] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        model_id = row.get("id")
        pricing = row.get("pricing") if isinstance(row.get("pricing"), dict) else {}
        prompt = _per_token_to_per_1k(pricing.get("prompt"))
        completion = _per_token_to_per_1k(pricing.get("completion"))
        if isinstance(model_id, str) and model_id and prompt is not None and completion is not None:
            out[model_id] = ModelRate(prompt_per_1k=prompt, completion_per_1k=completion)
    return out


def blended_fallback_quote(model: str | None, *, reason: str) -> PriceQuote:
    """The static rate path: catalog ``usd_per_1k`` override, else the settings default."""
    if model:
        for option in OPENROUTER_MODELS:
            if option.id == model and option.usd_per_1k is not None:
                return PriceQuote(
                    source=ComputeDebitRateSource.CATALOG_OVERRIDE,
                    effective_rate_per_1k=option.usd_per_1k,
                    fallback_reason=reason,
                    model=model,
                )
    return PriceQuote(
        source=ComputeDebitRateSource.BLENDED_FALLBACK,
        effective_rate_per_1k=settings.agent_token_rate_usd_per_1k,
        fallback_reason=reason,
        model=model,
    )


def live_quote(model: str, rate: ModelRate, *, stale: bool = False) -> PriceQuote:
    return PriceQuote(
        source=ComputeDebitRateSource.OPENROUTER_LIVE,
        effective_rate_per_1k=rate.mean_per_1k,
        prompt_rate_per_1k=rate.prompt_per_1k,
        completion_rate_per_1k=rate.completion_per_1k,
        model=model,
        stale=stale,
    )


def _tokens_to_cost(tokens_used: int, rate_per_1k: Decimal) -> Decimal:
    """Same quantum as ``services.compute.tokens_to_cost`` — kept local to avoid a cycle."""
    if tokens_used <= 0 or rate_per_1k < 0:
        return Decimal("0")
    raw = (Decimal(tokens_used) * rate_per_1k) / Decimal(1000)
    return raw.quantize(_AMOUNT_QUANTUM, rounding=ROUND_HALF_UP)


def usage_to_cost(
    *,
    tokens_used: int,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    quote: PriceQuote,
) -> Decimal:
    """Bill a recorded usage against a quote.

    When live prompt/completion rates *and* a token split are known: prompt tokens
    at the prompt rate, completion tokens at the completion rate. Any remainder
    (``tokens_used − prompt − completion``, e.g. reasoning tokens) is billed at
    the completion rate. When the split is missing, bill the total at the quote's
    effective rate (live mean, or the blended fallback).
    """
    if tokens_used <= 0:
        return Decimal("0")
    if (
        quote.is_live
        and quote.prompt_rate_per_1k is not None
        and quote.completion_rate_per_1k is not None
        and prompt_tokens is not None
        and completion_tokens is not None
    ):
        prompt_n = max(int(prompt_tokens), 0)
        completion_n = max(int(completion_tokens), 0)
        remainder = max(tokens_used - prompt_n - completion_n, 0)
        return _tokens_to_cost(prompt_n, quote.prompt_rate_per_1k) + _tokens_to_cost(
            completion_n + remainder, quote.completion_rate_per_1k
        )
    return _tokens_to_cost(tokens_used, quote.effective_rate_per_1k)


class OpenRouterPriceClient:
    """``GET /models`` with a short timeout. ``transport`` is the test injection seam."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
        timeout: float | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.openrouter_api_key
        self._base_url = (base_url or settings.openrouter_base_url).rstrip("/")
        self._transport = transport
        self._timeout = (
            timeout if timeout is not None else settings.openrouter_price_timeout_s
        )

    async def fetch_catalog(self) -> dict[str, ModelRate]:
        if not self._api_key:
            raise PriceFetchError(REASON_API_KEY_MISSING)
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.get(
                    f"{self._base_url}/models",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException as exc:
            raise PriceFetchError(REASON_TIMEOUT) from exc
        except Exception as exc:
            raise PriceFetchError(REASON_FETCH_FAILED) from exc
        catalog = parse_models_catalog(payload)
        if not catalog:
            raise PriceFetchError(REASON_EMPTY_CATALOG)
        return catalog


class PriceFetchError(Exception):
    """The catalog could not be refreshed. ``reason`` is a stable fallback token."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


async def _refresh_catalog(client: OpenRouterPriceClient) -> dict[str, ModelRate]:
    global _cache
    catalog = await client.fetch_catalog()
    _cache = _CatalogCache(models=catalog, fetched_at=_now())
    return catalog


def _cached_if_fresh(*, ttl_s: float) -> dict[str, ModelRate] | None:
    if _cache is None:
        return None
    if (_now() - _cache.fetched_at) < ttl_s:
        return _cache.models
    return None


async def quote_model_price(
    model: str | None,
    *,
    client: OpenRouterPriceClient | None = None,
) -> PriceQuote:
    """Resolve the rate for ``model``. Never raises; never skips a fallback quote.

    A pass calls this *before* planning (short timeout) so ``ProjectBudgetPolicy``
    and the subsequent ``ComputeDebit`` share the same snapshot.
    """
    if not settings.openrouter_live_prices:
        return blended_fallback_quote(model, reason=REASON_LIVE_PRICES_DISABLED)

    price_client = client or OpenRouterPriceClient()
    if not price_client._api_key:
        return blended_fallback_quote(model, reason=REASON_API_KEY_MISSING)
    if not model:
        return blended_fallback_quote(model, reason=REASON_MODEL_UNKNOWN)

    ttl = settings.openrouter_price_cache_ttl_s
    cached = _cached_if_fresh(ttl_s=ttl)
    if cached is not None:
        rate = cached.get(model)
        if rate is None:
            return blended_fallback_quote(model, reason=REASON_MODEL_UNKNOWN)
        return live_quote(model, rate)

    try:
        catalog = await _refresh_catalog(price_client)
    except PriceFetchError as exc:
        if _cache is not None:
            rate = _cache.models.get(model)
            if rate is not None:
                return live_quote(model, rate, stale=True)
            return blended_fallback_quote(model, reason=REASON_MODEL_UNKNOWN)
        return blended_fallback_quote(model, reason=exc.reason)

    rate = catalog.get(model)
    if rate is None:
        return blended_fallback_quote(model, reason=REASON_MODEL_UNKNOWN)
    return live_quote(model, rate)
