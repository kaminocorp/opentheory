"""DB-free metering math (0.19.0) — tokens → cost, rate lookup, the policy seam."""

from decimal import Decimal

import pytest

from app.agent.pricing import PriceQuote, live_quote, parse_models_catalog, usage_to_cost
from app.core.config import settings
from app.core.openrouter_models import ModelOption
from app.models.enums import ComputeDebitRateSource
from app.services.compute import (
    ProjectBudgetPolicy,
    pass_reserve_amount,
    rate_for_model,
    tokens_to_cost,
)


def test_tokens_to_cost_is_tokens_times_rate_over_1000() -> None:
    assert tokens_to_cost(1000, Decimal("1.00")) == Decimal("1.000000")
    assert tokens_to_cost(42, Decimal("1.00")) == Decimal("0.042000")
    assert tokens_to_cost(1, Decimal("0.005")) == Decimal("0.000005")


def test_tokens_to_cost_is_zero_when_there_is_nothing_to_bill() -> None:
    assert tokens_to_cost(0, Decimal("1.00")) == Decimal("0")
    assert tokens_to_cost(-3, Decimal("1.00")) == Decimal("0")
    assert tokens_to_cost(100, Decimal("0")) == Decimal("0")


def test_rate_for_model_falls_back_to_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "agent_token_rate_usd_per_1k", Decimal("0.123"))
    assert rate_for_model(None) == Decimal("0.123")
    assert rate_for_model("anthropic/claude-sonnet-4") == Decimal("0.123")


def test_rate_for_model_uses_catalog_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "agent_token_rate_usd_per_1k", Decimal("0.005"))
    override = ModelOption(
        "test/override", "Override", "Test", usd_per_1k=Decimal("9.99")
    )
    monkeypatch.setattr(
        "app.services.compute.OPENROUTER_MODELS",
        (override,),
    )
    assert rate_for_model("test/override") == Decimal("9.99")
    assert rate_for_model("unknown/model") == Decimal("0.005")


def test_project_budget_policy_stops_when_tokens_consume_the_remainder() -> None:
    policy = ProjectBudgetPolicy(Decimal("0.050000"), rate_per_1k=Decimal("1.00"))
    assert policy.check(tokens_used=49, ran_count=0) is True  # $0.049 < $0.05
    assert policy.check(tokens_used=50, ran_count=0) is False  # $0.050 is exhausted
    assert policy.check(tokens_used=51, ran_count=0) is False


def test_project_budget_policy_refuses_when_available_is_already_zero() -> None:
    policy = ProjectBudgetPolicy(Decimal("0"), rate_per_1k=Decimal("1.00"))
    assert policy.check(tokens_used=0, ran_count=0) is False
    assert policy.check(tokens_used=1, ran_count=0) is False


def test_pass_reserve_amount_clamps_to_available_and_the_safety_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "agent_pass_max_tokens", 1000)
    # 1000 tokens × $1/1k = $1 envelope.
    assert pass_reserve_amount(Decimal("5.00"), rate_per_1k=Decimal("1.00")) == Decimal("1.000000")
    assert pass_reserve_amount(Decimal("0.25"), rate_per_1k=Decimal("1.00")) == Decimal("0.25")
    assert pass_reserve_amount(Decimal("0"), rate_per_1k=Decimal("1.00")) == Decimal("0")


def test_usage_to_cost_live_split_does_not_use_the_blended_default() -> None:
    catalog = parse_models_catalog(
        {
            "data": [
                {
                    "id": "anthropic/claude-sonnet-4",
                    "pricing": {"prompt": "0.000003", "completion": "0.000015"},
                }
            ]
        }
    )
    quote = live_quote("anthropic/claude-sonnet-4", catalog["anthropic/claude-sonnet-4"])
    # Distinct from the $0.005 blended default: 500 prompt + 500 completion.
    assert usage_to_cost(
        tokens_used=1000,
        prompt_tokens=500,
        completion_tokens=500,
        quote=quote,
    ) == Decimal("0.009000")
    fallback = PriceQuote(
        source=ComputeDebitRateSource.BLENDED_FALLBACK,
        effective_rate_per_1k=Decimal("0.005"),
        fallback_reason="openrouter_api_key_missing",
    )
    assert usage_to_cost(
        tokens_used=1000,
        prompt_tokens=500,
        completion_tokens=500,
        quote=fallback,
    ) == Decimal("0.005000")
