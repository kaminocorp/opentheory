"""Shared table payload + exact-cell plumbing for Bench 6 (``table.*``).

Tables are the primary falsification grid. Cells are **exact or labels** — never a silent
float. A JSON ``1.5`` or a decimal token ``0.5`` is a caller error (422, mint nothing),
matching the calc spine. Opaque labels (``"triangle"``) are allowed on ``table.create`` /
``table.render``; ``table.derive_column`` refuses them on any column the expression names.

Bounds are small on purpose: a workspace table is a *grid you can inspect*, not a
dataframe service.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sympy import Float
from sympy.core.expr import Expr

from app.toolbench.instruments._sympy_support import (
    ENGINE,
    ENGINE_VERSION,
    parse,
    symbol_assumptions,
)

COLUMN_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_COLS = 16
MAX_ROWS = 200
MAX_CELL_LEN = 200
MAX_COLUMN_NAME = 32
MAX_TITLE = 200

CellKind = Literal["exact", "label"]
CellRaw = int | str


class TablePayload(BaseModel):
    """Columns + rows as the human/agent supplies them.

    Cell values are ``int`` or ``str`` only. A JSON float is rejected before the
    instrument runs so the ledger never hashes an inexact number as if it were exact.
    """

    model_config = ConfigDict(extra="forbid")

    columns: list[str] = Field(min_length=1, max_length=MAX_COLS)
    rows: list[dict[str, CellRaw]] = Field(default_factory=list, max_length=MAX_ROWS)
    title: str | None = Field(default=None, max_length=MAX_TITLE)

    @field_validator("columns")
    @classmethod
    def _columns_are_names(cls, columns: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in columns:
            name = raw.strip()
            if not name:
                raise ValueError("column names must be non-empty")
            if len(name) > MAX_COLUMN_NAME:
                raise ValueError(f"column name {name!r} exceeds {MAX_COLUMN_NAME} characters")
            if not COLUMN_NAME_RE.match(name):
                raise ValueError(
                    f"column name {name!r} must be a Python-ish identifier "
                    "(letter/underscore, then letters, digits, underscores)"
                )
            if name in seen:
                raise ValueError(f"duplicate column name {name!r}")
            seen.add(name)
            cleaned.append(name)
        return cleaned

    @field_validator("rows", mode="before")
    @classmethod
    def _reject_float_cells(cls, rows: Any) -> Any:
        if not isinstance(rows, list):
            return rows
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(f"row {index} must be an object keyed by column name")
            for key, value in row.items():
                if isinstance(value, bool) or not isinstance(value, (int, str)):
                    # ``bool`` is an ``int`` subclass — reject it before the int branch.
                    # A JSON float lands here as ``float``.
                    raise ValueError(
                        f"row {index} column {key!r}: cells must be an integer or an exact "
                        "string (1/2, sqrt(2), a label). Floats are not allowed — no silent "
                        "promotion."
                    )
                if isinstance(value, str) and len(value) > MAX_CELL_LEN:
                    raise ValueError(
                        f"row {index} column {key!r}: cell exceeds {MAX_CELL_LEN} characters"
                    )
        return rows

    @field_validator("title")
    @classmethod
    def _strip_title(cls, title: str | None) -> str | None:
        if title is None:
            return None
        cleaned = title.strip()
        return cleaned or None


class NormalizedTable:
    """Validated, hash-stable table: every cell is a string; kinds are exact or label."""

    def __init__(
        self,
        columns: list[str],
        rows: list[dict[str, str]],
        kinds: list[dict[str, CellKind]],
        title: str | None,
    ) -> None:
        self.columns = columns
        self.rows = rows
        self.kinds = kinds
        self.title = title

    @property
    def n_rows(self) -> int:
        return len(self.rows)

    @property
    def n_cols(self) -> int:
        return len(self.columns)

    @property
    def has_labels(self) -> bool:
        return any(kind == "label" for row in self.kinds for kind in row.values())

    def as_output(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "columns": list(self.columns),
            "rows": [dict(row) for row in self.rows],
            "n_rows": self.n_rows,
            "n_cols": self.n_cols,
            "has_labels": self.has_labels,
            "exact": True,
        }


def _try_exact_expr(text: str, assumptions: dict[str, dict[str, bool]]) -> Expr | None:
    """Parse ``text`` as exact math, or ``None`` if it is not an expression.

    A successful parse that is a SymPy ``Float`` is a caller error — that is the
    silent-promotion path this module exists to close.
    """
    try:
        expr = parse(text, assumptions)
    except ValueError:
        return None
    if isinstance(expr, Float) or bool(getattr(expr, "is_Float", False)):
        raise ValueError(
            f"inexact decimal {text!r} — use a rational (1/2) or an exact form "
            "(sqrt(2)), never a float"
        )
    atoms = getattr(expr, "atoms", None)
    if callable(atoms) and any(isinstance(atom, Float) for atom in atoms(Float)):
        raise ValueError(
            f"inexact decimal {text!r} — use a rational (1/2) or an exact form "
            "(sqrt(2)), never a float"
        )
    return expr


def normalize_cell(
    value: CellRaw,
    *,
    allow_label: bool,
    assumptions: dict[str, dict[str, bool]],
) -> tuple[str, CellKind]:
    """Turn one raw cell into a stable string + kind.

    Integers stay integers. Parseable exact expressions canonicalize via ``str(expr)``
    so ``1/2`` and ``2/4`` hash as ``1/2``. Unparseable text is a label (when allowed).
    """
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(
            "cells must be an integer or an exact string — floats are not allowed"
        )
    if isinstance(value, int):
        return str(value), "exact"

    text = value.strip()
    if not text:
        if allow_label:
            return "", "label"
        raise ValueError("empty cell cannot be used in a derived column")

    expr = _try_exact_expr(text, assumptions)
    if expr is not None:
        return str(expr), "exact"
    if allow_label:
        return text, "label"
    raise ValueError(
        f"cell {text!r} is not exact math — derive_column can only bind exact cells "
        "(integers, rationals, exact expressions)"
    )


def normalize_table(
    payload: TablePayload,
    *,
    allow_labels: bool,
    assumptions: dict[str, Any] | None = None,
) -> NormalizedTable:
    """Validate row keys against columns and canonicalize every cell."""
    syms = symbol_assumptions(assumptions or {})
    columns = list(payload.columns)
    colset = set(columns)
    rows: list[dict[str, str]] = []
    kinds: list[dict[str, CellKind]] = []

    for index, raw in enumerate(payload.rows):
        extra = set(raw) - colset
        if extra:
            raise ValueError(
                f"row {index} has unknown column(s) {sorted(extra)} — columns are {columns}"
            )
        missing = [name for name in columns if name not in raw]
        if missing:
            raise ValueError(
                f"row {index} is missing column(s) {missing} — every row must fill every column"
            )
        row: dict[str, str] = {}
        kind_row: dict[str, CellKind] = {}
        for name in columns:
            text, kind = normalize_cell(
                raw[name], allow_label=allow_labels, assumptions=syms
            )
            row[name] = text
            kind_row[name] = kind
        rows.append(row)
        kinds.append(kind_row)

    return NormalizedTable(columns, rows, kinds, payload.title)


def render_markdown(table: NormalizedTable) -> str:
    """Serialize the table as GitHub-flavored markdown (inspectable, not a proof)."""
    header = "| " + " | ".join(table.columns) + " |"
    sep = "| " + " | ".join("---" for _ in table.columns) + " |"
    body = ["| " + " | ".join(row[c] for c in table.columns) + " |" for row in table.rows]
    lines = [header, sep, *body]
    if table.title:
        return f"{table.title}\n\n" + "\n".join(lines)
    return "\n".join(lines)


def bind_row(
    row: dict[str, str],
    columns: list[str],
    assumptions: dict[str, dict[str, bool]],
) -> dict[str, Expr]:
    """Parse named cells as exact expressions for substitution into a derived column."""
    bound: dict[str, Expr] = {}
    for name in columns:
        expr = _try_exact_expr(row[name], assumptions)
        if expr is None:
            raise ValueError(
                f"column {name!r} value {row[name]!r} is not exact math — cannot bind it"
            )
        bound[name] = expr
    return bound


__all__ = [
    "ENGINE",
    "ENGINE_VERSION",
    "MAX_COLS",
    "MAX_ROWS",
    "TablePayload",
    "NormalizedTable",
    "bind_row",
    "normalize_table",
    "render_markdown",
]
