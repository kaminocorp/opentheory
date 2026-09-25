"""DB-free helpers for the 0.25.0 / 0.32.0 continuous research campaign."""

from app.core.config import settings
from app.services.campaigns import (
    CAMPAIGN_CYCLE_CONCURRENCY_HARD_CAP,
    resolve_cycle_concurrency,
    resolve_max_cycles,
)


def test_resolve_max_cycles_defaults_to_settings(monkeypatch) -> None:
    monkeypatch.setattr(settings, "campaign_max_cycles", 8)
    assert resolve_max_cycles(None) == 8


def test_resolve_max_cycles_clamps_to_server_cap(monkeypatch) -> None:
    monkeypatch.setattr(settings, "campaign_max_cycles", 8)
    assert resolve_max_cycles(2) == 2
    assert resolve_max_cycles(64) == 8
    assert resolve_max_cycles(0) == 1


def test_resolve_cycle_concurrency_defaults_to_settings(monkeypatch) -> None:
    monkeypatch.setattr(settings, "campaign_cycle_concurrency", 2)
    assert resolve_cycle_concurrency(None) == 2


def test_resolve_cycle_concurrency_clamps_to_hard_cap_and_floor(monkeypatch) -> None:
    monkeypatch.setattr(settings, "campaign_cycle_concurrency", 64)
    assert resolve_cycle_concurrency(None) == CAMPAIGN_CYCLE_CONCURRENCY_HARD_CAP
    assert resolve_cycle_concurrency(1) == 1
    assert resolve_cycle_concurrency(0) == 1
    monkeypatch.setattr(settings, "campaign_cycle_concurrency", 2)
    assert resolve_cycle_concurrency(4) == 2
