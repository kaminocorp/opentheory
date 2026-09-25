"""DB-free selection helpers for the 0.22.0 / 0.27.0 multi-thread orchestrator."""

from app.core.config import settings
from app.schemas.claim import SETTLED_HEADLINES
from app.services.orchestration import (
    ORCHESTRATION_CONCURRENCY_HARD_CAP,
    claim_is_raisable,
    resolve_concurrency,
)


def test_proven_and_refuted_are_not_raisable() -> None:
    assert SETTLED_HEADLINES == frozenset({"proven", "refuted"})
    assert claim_is_raisable("proven") is False
    assert claim_is_raisable("refuted") is False


def test_ungrounded_and_letter_rungs_are_raisable() -> None:
    for headline in ("ungrounded", "cited", "D", "C", "B"):
        assert claim_is_raisable(headline) is True


def test_resolve_concurrency_defaults_to_settings(monkeypatch) -> None:
    monkeypatch.setattr(settings, "orchestration_concurrency", 3)
    assert resolve_concurrency(None) == 3


def test_resolve_concurrency_clamps_to_hard_cap_and_floor(monkeypatch) -> None:
    monkeypatch.setattr(settings, "orchestration_concurrency", 64)
    assert resolve_concurrency(None) == ORCHESTRATION_CONCURRENCY_HARD_CAP
    assert resolve_concurrency(1) == 1
    assert resolve_concurrency(0) == 1
    monkeypatch.setattr(settings, "orchestration_concurrency", 2)
    assert resolve_concurrency(8) == 2
