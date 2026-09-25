"""Unit tests for Bench 6 ``table.*`` — exact cells, derived columns, render.

Pure in-process (no DB). Write-path / ``run_instrument`` round-trips live in
``test_instruments_write_path.py``.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.models.enums import ResultStatus
from app.toolbench.conformance import check_conformance
from app.toolbench.execution import limits_for, run_bounded_sync
from app.toolbench.instruments._sympy_support import ENGINE, ENGINE_VERSION
from app.toolbench.instruments.table_create import TABLE_CREATE
from app.toolbench.instruments.table_derive_column import TABLE_DERIVE_COLUMN
from app.toolbench.instruments.table_render import TABLE_RENDER

# Flagship 3-4-5 / 5-12-13 triples — the grid that shows d = a+b is false.
_TRIPLES = {
    "columns": ["a", "b", "d"],
    "rows": [
        {"a": 3, "b": 4, "d": 5},
        {"a": 5, "b": 12, "d": 13},
    ],
    "title": "integer triples",
}


def _run(instrument: Any, inputs: dict[str, Any], assumptions: dict[str, Any] | None = None):
    validated = instrument.InputModel.model_validate(inputs)
    return instrument.run(validated, assumptions or {})


# --- conformance ---------------------------------------------------------------------------------


def test_table_create_conforms() -> None:
    assert check_conformance(TABLE_CREATE, example_inputs=_TRIPLES) == []


def test_table_derive_column_conforms() -> None:
    inputs = {**_TRIPLES, "name": "sum_sq", "expression": "a**2 + b**2"}
    assert check_conformance(TABLE_DERIVE_COLUMN, example_inputs=inputs) == []


def test_table_render_conforms() -> None:
    assert check_conformance(TABLE_RENDER, example_inputs=_TRIPLES) == []


@pytest.mark.parametrize("instrument", (TABLE_CREATE, TABLE_DERIVE_COLUMN, TABLE_RENDER))
def test_engine_is_pinned_to_sympy(instrument: Any) -> None:
    assert instrument.engine == ENGINE
    assert instrument.engine_version == ENGINE_VERSION
    assert instrument.version == "0.1.0"


# --- table.create --------------------------------------------------------------------------------


def test_create_canonicalizes_exact_cells() -> None:
    result = _run(
        TABLE_CREATE,
        {
            "columns": ["x", "y"],
            "rows": [{"x": "2/4", "y": "sqrt(4)"}],
        },
    )
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "table"
    assert result.output["rows"] == [{"x": "1/2", "y": "2"}]
    assert result.output["exact"] is True
    assert result.output["has_labels"] is False
    assert result.output["n_rows"] == 1
    assert result.output["n_cols"] == 2


def test_create_keeps_opaque_labels() -> None:
    result = _run(
        TABLE_CREATE,
        {
            "columns": ["name", "n"],
            "rows": [{"name": "flagship corner", "n": 3}],
        },
    )
    assert result.output["rows"][0]["name"] == "flagship corner"
    assert result.output["has_labels"] is True
    assert result.output["exact"] is True


def test_create_rejects_json_float() -> None:
    with pytest.raises(ValidationError):
        TABLE_CREATE.InputModel.model_validate(
            {"columns": ["x"], "rows": [{"x": 0.5}]}
        )


def test_create_rejects_decimal_string() -> None:
    with pytest.raises(ValueError, match="inexact decimal"):
        _run(TABLE_CREATE, {"columns": ["x"], "rows": [{"x": "0.5"}]})


def test_create_rejects_unknown_column() -> None:
    with pytest.raises(ValueError, match="unknown column"):
        _run(
            TABLE_CREATE,
            {"columns": ["a"], "rows": [{"a": 1, "b": 2}]},
        )


def test_create_rejects_missing_column() -> None:
    with pytest.raises(ValueError, match="missing column"):
        _run(TABLE_CREATE, {"columns": ["a", "b"], "rows": [{"a": 1}]})


def test_create_empty_rows_is_a_result() -> None:
    result = _run(TABLE_CREATE, {"columns": ["a"], "rows": []})
    assert result.status is ResultStatus.RESULT
    assert result.output["n_rows"] == 0


# --- table.derive_column -------------------------------------------------------------------------


def test_derive_value_column_is_exact() -> None:
    result = _run(
        TABLE_DERIVE_COLUMN,
        {**_TRIPLES, "name": "sum_sq", "expression": "a**2 + b**2"},
    )
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "table"
    assert result.output["is_relation"] is False
    assert result.output["columns"] == ["a", "b", "d", "sum_sq"]
    assert result.output["rows"][0]["sum_sq"] == "25"
    assert result.output["rows"][1]["sum_sq"] == "169"
    assert result.output["exact"] is True
    # No silent float in the payload values we care about.
    assert result.output["rows"][0]["sum_sq"] != "25.0"


def test_derive_pythagoras_relation_holds() -> None:
    result = _run(
        TABLE_DERIVE_COLUMN,
        {**_TRIPLES, "name": "pythag", "expression": "a**2 + b**2 == d**2"},
    )
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "table"
    assert result.output["is_relation"] is True
    assert result.output["holds_per_row"] == [True, True]
    assert result.output["n_false"] == 0
    assert result.output["rows"][0]["pythag"] == "true"


def test_derive_sum_of_legs_is_a_refuted_witness() -> None:
    """The 3-4-5 triple falsifies d == a+b — exact, blamable, Grade B."""
    result = _run(
        TABLE_DERIVE_COLUMN,
        {**_TRIPLES, "name": "sum_legs", "expression": "d == a + b"},
    )
    assert result.status is ResultStatus.REFUTED
    assert result.artifact_kind == "counterexample"
    assert result.output["n_false"] == 2
    witness = result.output["witness"]
    assert witness is not None
    assert witness["a"] == "3"
    assert witness["b"] == "4"
    assert witness["d"] == "5"
    assert witness["sum_legs"] == "false"


def test_derive_undecided_when_a_row_cannot_be_settled() -> None:
    result = _run(
        TABLE_DERIVE_COLUMN,
        {
            "columns": ["x", "y"],
            "rows": [{"x": "x", "y": "2*x"}],
            "name": "eq",
            "expression": "x**2 == y",
        },
    )
    assert result.status is ResultStatus.UNDECIDED
    assert result.artifact_kind == "table"
    assert result.output["holds_per_row"] == [None]
    assert result.output["n_undecided"] == 1


def test_derive_passes_through_unreferenced_label_columns() -> None:
    result = _run(
        TABLE_DERIVE_COLUMN,
        {
            "columns": ["a", "b", "note"],
            "rows": [{"a": 3, "b": 4, "note": "flagship corner"}],
            "name": "sum_sq",
            "expression": "a**2 + b**2",
        },
    )
    assert result.output["rows"][0]["note"] == "flagship corner"
    assert result.output["rows"][0]["sum_sq"] == "25"


def test_derive_rejects_float_in_expression() -> None:
    with pytest.raises(ValueError, match="inexact decimal"):
        _run(
            TABLE_DERIVE_COLUMN,
            {**_TRIPLES, "name": "approx", "expression": "a + 0.5"},
        )


def test_derive_rejects_unknown_symbol() -> None:
    with pytest.raises(ValueError, match="not columns"):
        _run(
            TABLE_DERIVE_COLUMN,
            {**_TRIPLES, "name": "z", "expression": "z + 1"},
        )


def test_derive_rejects_name_collision() -> None:
    with pytest.raises(ValueError, match="already exists"):
        _run(
            TABLE_DERIVE_COLUMN,
            {**_TRIPLES, "name": "a", "expression": "b + d"},
        )


def test_derive_rejects_empty_table() -> None:
    with pytest.raises(ValueError, match="at least one row"):
        _run(
            TABLE_DERIVE_COLUMN,
            {
                "columns": ["a"],
                "rows": [],
                "name": "twice",
                "expression": "2*a",
            },
        )


def test_derive_mixed_false_and_undecided_is_refuted() -> None:
    """A single false row settles the relation — undecided neighbours do not dilute it."""
    result = _run(
        TABLE_DERIVE_COLUMN,
        {
            "columns": ["x", "y"],
            "rows": [{"x": 1, "y": 2}, {"x": "x", "y": "2*x"}],
            "name": "eq",
            "expression": "x == y",
        },
    )
    assert result.status is ResultStatus.REFUTED
    assert result.output["n_false"] == 1
    assert result.output["n_undecided"] == 1


# --- table.render --------------------------------------------------------------------------------


def test_render_includes_markdown() -> None:
    result = _run(TABLE_RENDER, _TRIPLES)
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "table"
    markdown = result.output["markdown"]
    assert markdown.startswith("integer triples")
    assert "| a | b | d |" in markdown
    assert "| 3 | 4 | 5 |" in markdown
    assert result.output["rows"][0]["a"] == "3"


# --- sandbox dispatch ----------------------------------------------------------------------------


def test_table_create_runs_through_the_killable_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "toolbench_subprocess_sandbox_enabled", True)
    limits = limits_for(TABLE_CREATE)
    result = run_bounded_sync("table.create", _TRIPLES, {}, limits)
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "table"
    assert result.output["n_rows"] == 2
