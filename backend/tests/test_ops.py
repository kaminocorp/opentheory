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
from app.services.harness_meter import (
    DAILY_TOKEN_CAP_ENV,
    DEFAULT_DAILY_TOKEN_CAP,
    DEFAULT_HOLD_TTL_SECONDS,
    HOLD_TTL_ENV,
    SESSION_NOTES,
    budget_state,
    classify_harness_row,
    hold_notes,
    is_daily_cap_adjustment,
    pair_holds,
    parse_hold_id,
    peek_daily_token_cap,
    peek_hold_ttl_seconds,
    release_notes,
)
from app.services.ops import _REFUSALS

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


def test_refusals_are_not_invented() -> None:
    assert _REFUSALS.recorded is False
    assert "writes nothing" in _REFUSALS.note
