"""Perpetual ops dashboard (0.49.0) — DB-free honesty + import posture.

Ledger round-trips live in ``test_ops_ledger.py`` and skip without
``TEST_DATABASE_URL``. This module stays green in default CI.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from app.models.enums import ComputeDebitRateSource
from app.services.harness_meter import (
    DAILY_TOKEN_CAP_ENV,
    DEFAULT_DAILY_TOKEN_CAP,
    DEFAULT_HOLD_TTL_SECONDS,
    DEFAULT_TURN_TOKEN_FLOOR,
    HOLD_TTL_ENV,
    POT_ROOM_NONE,
    PRICE_UNKNOWN_MARK,
    SESSION_NOTES,
    TURN_TOKEN_FLOOR_ENV,
    budget_state,
    clamp_max_tokens,
    clamp_rate_per_1k,
    classify_harness_row,
    hold_notes,
    is_daily_cap_adjustment,
    open_pot_holds,
    overshoot_tokens,
    pair_holds,
    parse_clamp,
    parse_hold_id,
    parse_overshoot,
    parse_pot_hold,
    parse_pot_room,
    parse_price_known,
    peek_daily_token_cap,
    peek_hold_ttl_seconds,
    peek_turn_token_floor,
    pot_available_after_holds,
    pot_hold_usd,
    pot_tokens_from_available,
    price_is_known,
    release_notes,
    spend_notes,
    turn_clamp,
)
from app.services.ops import _REFUSALS, _last_turn_note

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_ops_route_is_get_only() -> None:
    paths = create_app().openapi()["paths"]
    ops = paths["/api/v1/projects/{project_id}/ops"]
    assert "get" in ops
    assert "post" not in ops
    assert "put" not in ops
    assert "patch" not in ops
    assert "delete" not in ops


def test_health_still_ok() -> None:
    response = TestClient(create_app()).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_fastapi_ops_path_does_not_import_harness() -> None:
    files = (
        "app/main.py",
        "app/api/router.py",
        "app/api/routes/ops.py",
        "app/services/ops.py",
        "app/services/harness_meter.py",
        "app/schemas/ops.py",
    )
    for rel in files:
        source = (BACKEND_ROOT / rel).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("app.harness"), rel
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("app.harness"), rel


def test_budget_state_unfunded_is_not_exhausted() -> None:
    assert budget_state(funded=0, available=0) == "unfunded"
    assert budget_state(funded=Decimal("0"), available=Decimal("-1.5")) == "unfunded"
    assert budget_state(funded=Decimal("10"), available=Decimal("0")) == "exhausted"
    assert budget_state(funded=Decimal("10"), available=Decimal("-0.01")) == "exhausted"
    assert budget_state(funded=Decimal("10"), available=Decimal("1")) == "available"


def test_peek_cap_invalid_is_unknown() -> None:
    assert peek_daily_token_cap({}) == peek_daily_token_cap({})
    unset = peek_daily_token_cap({})
    assert unset.value == DEFAULT_DAILY_TOKEN_CAP
    assert unset.source == "default"

    override = peek_daily_token_cap({DAILY_TOKEN_CAP_ENV: "500"})
    assert override.value == 500
    assert override.source == "process_env"

    bad = peek_daily_token_cap({DAILY_TOKEN_CAP_ENV: "nope"})
    assert bad.value is None
    assert bad.source == "invalid"

    zero = peek_daily_token_cap({DAILY_TOKEN_CAP_ENV: "0"})
    assert zero.value is None
    assert zero.source == "invalid"


def test_peek_ttl_invalid_is_unknown() -> None:
    unset = peek_hold_ttl_seconds({})
    assert unset.value == DEFAULT_HOLD_TTL_SECONDS
    assert unset.source == "default"
    bad = peek_hold_ttl_seconds({HOLD_TTL_ENV: "x"})
    assert bad.value is None
    assert bad.source == "invalid"


def test_classify_and_parse_hold_id() -> None:
    hold_id = uuid4()
    assert classify_harness_row(hold_notes(hold_id)) == "hold"
    assert classify_harness_row(release_notes(hold_id)) == "release"
    assert classify_harness_row(f"{SESSION_NOTES}; rate fallback: blended_fallback") == "spend"
    assert parse_hold_id(hold_notes(hold_id)) == hold_id
    marked = hold_notes(hold_id, pot_hold=Decimal("0.05"))
    assert classify_harness_row(marked) == "hold"
    assert parse_hold_id(marked) == hold_id
    assert parse_pot_hold(marked) == Decimal("0.05")
    assert parse_hold_id(f"{SESSION_NOTES}; extra") is None
    assert is_daily_cap_adjustment(hold_notes(hold_id))
    assert not is_daily_cap_adjustment(SESSION_NOTES)


@dataclass
class _Row:
    tokens_used: int
    notes: str | None
    created_at: datetime


def test_pair_holds_by_hold_id_and_legacy_fifo() -> None:
    t0 = datetime(2026, 10, 5, 1, 0, tzinfo=UTC)
    t1 = datetime(2026, 10, 5, 1, 1, tzinfo=UTC)
    t2 = datetime(2026, 10, 5, 1, 2, tzinfo=UTC)
    hid = uuid4()
    rows = [
        _Row(100, hold_notes(hid), t0),
        _Row(-100, release_notes(hid), t1),
        _Row(50, f"{SESSION_NOTES}; daily_cap_hold", t0),
        _Row(-50, f"{SESSION_NOTES}; daily_cap_release", t2),
        _Row(25, f"{SESSION_NOTES}; daily_cap_hold", t1),
    ]
    paired = pair_holds(rows)
    assert len(paired) == 3
    identified = next(item for item in paired if item.hold_id == hid)
    assert identified.status == "released"
    assert identified.released_at == t1
    legacy = [item for item in paired if item.hold_id is None]
    assert len(legacy) == 2
    assert {item.status for item in legacy} == {"open", "released"}
    assert sum(1 for item in legacy if item.status == "open") == 1


def test_pot_hold_notes_pair_and_legacy_reserves_nothing() -> None:
    t0 = datetime(2026, 10, 6, 1, 0, tzinfo=UTC)
    t1 = datetime(2026, 10, 6, 1, 1, tzinfo=UTC)
    hid = uuid4()
    marked = hold_notes(hid, pot_hold=Decimal("0.05"))
    rows = [
        _Row(50, marked, t0),
        _Row(-50, release_notes(hid), t1),
        _Row(25, hold_notes(uuid4()), t0),
        _Row(10, f"{SESSION_NOTES}; daily_cap_hold", t1),
    ]
    paired = pair_holds(rows)
    identified = next(item for item in paired if item.hold_id == hid)
    assert identified.status == "released"
    assert parse_pot_hold(identified.notes) == Decimal("0.05")
    assert open_pot_holds(rows) == Decimal("0")
    open_only = [_Row(50, marked, t0), _Row(25, hold_notes(uuid4()), t0)]
    assert open_pot_holds(open_only) == Decimal("0.05")
    assert parse_pot_hold(hold_notes(uuid4())) is None
    assert parse_pot_hold(f"{SESSION_NOTES}; daily_cap_hold") is None
    assert pot_hold_usd(tokens=50, rate_per_1k=Decimal("1.00")) == Decimal("0.05")
    assert pot_hold_usd(tokens=20, rate_per_1k=Decimal("4.00")) == Decimal("0.08")
    assert pot_available_after_holds(Decimal("0.05"), Decimal("0.02")) == Decimal("0.03")
    assert pot_available_after_holds(Decimal("0.05"), Decimal("0.05")) == Decimal("0")
    assert pot_available_after_holds(Decimal("0.05"), Decimal("0.08")) == Decimal("0")


def test_refusals_are_not_invented() -> None:
    assert _REFUSALS.recorded is False
    assert "writes nothing" in _REFUSALS.note


def test_turn_clamp_is_min_of_daily_and_pot_when_price_known() -> None:
    assert turn_clamp(daily_room=20_000, pot_room=50) == 50
    assert turn_clamp(daily_room=40, pot_room=50) == 40
    assert turn_clamp(daily_room=40, pot_room=40) == 40
    assert pot_tokens_from_available(Decimal("0.05"), Decimal("1.00")) == 50
    assert pot_tokens_from_available(Decimal("0.049"), Decimal("1.00")) == 49
    assert pot_tokens_from_available(Decimal("0"), Decimal("1.00")) == 0
    assert pot_tokens_from_available(Decimal("1.00"), Decimal("0")) is None
    assert price_is_known(ComputeDebitRateSource.OPENROUTER_LIVE) is True
    assert price_is_known(ComputeDebitRateSource.CATALOG_OVERRIDE) is True
    assert price_is_known(ComputeDebitRateSource.BLENDED_FALLBACK) is False
    assert price_is_known(None) is False


def test_clamp_rate_prefers_completion_or_higher_split() -> None:
    mean = Decimal("2.50")
    assert clamp_rate_per_1k(
        effective_rate_per_1k=mean,
        prompt_rate_per_1k=Decimal("1.00"),
        completion_rate_per_1k=Decimal("4.00"),
    ) == Decimal("4.00")
    assert clamp_rate_per_1k(
        effective_rate_per_1k=mean,
        prompt_rate_per_1k=Decimal("4.00"),
        completion_rate_per_1k=Decimal("1.00"),
    ) == Decimal("4.00")
    assert clamp_rate_per_1k(effective_rate_per_1k=mean) == mean
    assert pot_tokens_from_available(Decimal("0.05"), Decimal("4.00")) == 12
    assert pot_tokens_from_available(Decimal("0.05"), mean) == 20


def test_turn_clamp_is_daily_room_when_price_unknown() -> None:
    assert turn_clamp(daily_room=20_000, pot_room=None) == 20_000
    assert turn_clamp(daily_room=7, pot_room=None) == 7
    assert clamp_max_tokens(None, 50) == 50
    assert clamp_max_tokens(80, 50) == 50
    assert clamp_max_tokens(20, 50) == 20
    assert clamp_max_tokens(0, 50) == 50
    assert overshoot_tokens(80, 50) == 30
    assert overshoot_tokens(50, 50) == 0
    assert overshoot_tokens(10, 50) == 0


def test_spend_notes_carry_clamp_overshoot_and_unknown_price() -> None:
    known = spend_notes(clamp=50, overshoot=30, price_known=True, pot_room=50)
    assert known.startswith(SESSION_NOTES)
    assert parse_clamp(known) == 50
    assert parse_overshoot(known) == 30
    assert parse_price_known(known) is True
    assert parse_pot_room(known) == 50
    unused = spend_notes(clamp=80, price_known=True)
    assert f"pot_room={POT_ROOM_NONE}" in unused
    assert parse_pot_room(unused) is None
    unknown = spend_notes(clamp=20, price_known=False)
    assert PRICE_UNKNOWN_MARK in unknown
    assert parse_price_known(unknown) is False
    assert parse_overshoot(unknown) == 0
    assert parse_pot_room(unknown) is None
    assert parse_clamp(f"{SESSION_NOTES}; rate fallback: blended_fallback") is None
    assert parse_overshoot(f"{SESSION_NOTES}; rate fallback: blended_fallback") is None
    assert parse_price_known(f"{SESSION_NOTES}; rate fallback: blended_fallback") is None
    assert parse_pot_room(f"{SESSION_NOTES}; rate fallback: blended_fallback") is None


def test_last_turn_note_does_not_claim_pot_when_unused() -> None:
    unused = _last_turn_note(clamp=80, overshoot=0, price_known=True, pot_room=None)
    assert "pot room was not applied" in unused
    assert "min of daily room and pot room" not in unused
    used = _last_turn_note(clamp=50, overshoot=0, price_known=True, pot_room=50)
    assert "min of daily room and pot room" in used
    unknown = _last_turn_note(clamp=80, overshoot=0, price_known=False, pot_room=None)
    assert "price unknown" in unknown
    assert "min of daily room and pot room" not in unknown


def test_peek_floor_invalid_is_unknown() -> None:
    unset = peek_turn_token_floor({})
    assert unset.value == DEFAULT_TURN_TOKEN_FLOOR
    assert unset.source == "default"
    override = peek_turn_token_floor({TURN_TOKEN_FLOOR_ENV: "32"})
    assert override.value == 32
    bad = peek_turn_token_floor({TURN_TOKEN_FLOOR_ENV: "nope"})
    assert bad.value is None
    assert bad.source == "invalid"
