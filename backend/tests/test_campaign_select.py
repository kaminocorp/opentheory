"""DB-free helpers for the 0.25.0 continuous research campaign."""

from app.core.config import settings
from app.services.campaigns import resolve_max_cycles


def test_resolve_max_cycles_defaults_to_settings(monkeypatch) -> None:
    monkeypatch.setattr(settings, "campaign_max_cycles", 8)
    assert resolve_max_cycles(None) == 8


def test_resolve_max_cycles_clamps_to_server_cap(monkeypatch) -> None:
    monkeypatch.setattr(settings, "campaign_max_cycles", 8)
    assert resolve_max_cycles(2) == 2
    assert resolve_max_cycles(64) == 8
    assert resolve_max_cycles(0) == 1
