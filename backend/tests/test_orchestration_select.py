"""DB-free selection helpers for the 0.22.0 multi-thread orchestrator."""

from app.schemas.claim import SETTLED_HEADLINES
from app.services.orchestration import claim_is_raisable


def test_proven_and_refuted_are_not_raisable() -> None:
    assert SETTLED_HEADLINES == frozenset({"proven", "refuted"})
    assert claim_is_raisable("proven") is False
    assert claim_is_raisable("refuted") is False


def test_ungrounded_and_letter_rungs_are_raisable() -> None:
    for headline in ("ungrounded", "cited", "D", "C", "B"):
        assert claim_is_raisable(headline) is True
