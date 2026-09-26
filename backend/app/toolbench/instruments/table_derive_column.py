"""``table.derive_column`` — add a *computed* column. This is compute, not display.

The derived column is blamed on this instrument, same honesty as ``calc.eval``:
exact substitution, no silent float. When the expression is a relation, a false
row is a definitive ``refuted`` witness (Grade B); every row holding is finite
exact support (Grade C), never a proof of a universal.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sympy import Float, simplify

from app.models.enums import ResultStatus
from app.toolbench.adapter import InstrumentResult
from app.toolbench.instruments._sympy_support import (
    attach_latex,
    parse,
    relation_holds,
    relation_to_latex,
    split_relation,
    symbol_assumptions,
    to_latex,
)
from app.toolbench.instruments._table_support import (
    COLUMN_NAME_RE,
    ENGINE,
    ENGINE_VERSION,
    MAX_COLUMN_NAME,
    TablePayload,
    bind_row,
    normalize_table,
)


class TableDeriveColumnInput(TablePayload):
    name: str = Field(
        min_length=1,
        max_length=MAX_COLUMN_NAME,
        description=(
            "Name of the new column (identifier). Must not collide with an existing column."
        ),
    )
    expression: str = Field(
        min_length=1,
        max_length=1000,
        description=(
            "Exact expression over column names (e.g. 'a**2 + b**2'), or a relation "
            "('a**2 + b**2 == d**2'). Use '==' for equality. Floats are rejected."
        ),
    )


class TableDeriveColumnOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    columns: list[str]
    rows: list[dict[str, str]]
    n_rows: int
    n_cols: int
    has_labels: bool
    exact: bool
    name: str
    expression: str
    is_relation: bool
    holds_per_row: list[bool | None] | None = None
    n_false: int | None = None
    n_undecided: int | None = None
    witness: dict[str, str] | None = None
    expression_latex: str | None = None


def _validate_new_name(name: str, existing: list[str]) -> str:
    cleaned = name.strip()
    if not cleaned or not COLUMN_NAME_RE.match(cleaned):
        raise ValueError(
            f"derived column name {name!r} must be a Python-ish identifier"
        )
    if cleaned in existing:
        raise ValueError(f"column {cleaned!r} already exists")
    return cleaned


class TableDeriveColumn:
    name = "table.derive_column"
    namespace = "table"
    version = "0.1.0"
    engine = ENGINE
    engine_version = ENGINE_VERSION
    description = (
        "Add a computed column by evaluating an exact expression (or relation) on each "
        "row. Same honesty as calc.eval: no silent float. A false relation is a "
        "refuted witness; every row holding is finite support, never a proof."
    )
    InputModel = TableDeriveColumnInput
    OutputModel = TableDeriveColumnOutput

    def run(
        self, inputs: TableDeriveColumnInput, assumptions: dict[str, Any]
    ) -> InstrumentResult:
        table = normalize_table(inputs, allow_labels=True, assumptions=assumptions)
        new_name = _validate_new_name(inputs.name, table.columns)
        if table.n_rows == 0:
            raise ValueError("derive_column needs at least one row to compute")

        syms = symbol_assumptions(assumptions)
        env = {**syms, **{name: {} for name in table.columns if name not in syms}}
        relation = split_relation(inputs.expression)
        needed = _referenced_columns(inputs.expression, relation, env, table.columns)
        derived_rows: list[dict[str, str]] = []
        holds_per_row: list[bool | None] = []
        witness: dict[str, str] | None = None

        for raw in table.rows:
            bound = bind_row(raw, needed, syms)
            if relation is None:
                expr = _eval_under(inputs.expression, bound, env)
                cell = _exact_result_string(expr)
                derived_rows.append({**raw, new_name: cell})
            else:
                left_text, op, right_text = relation
                left = _eval_under(left_text, bound, env)
                right = _eval_under(right_text, bound, env)
                holds = relation_holds(left, right, op)
                holds_per_row.append(holds)
                cell = _relation_cell(holds)
                new_row = {**raw, new_name: cell}
                derived_rows.append(new_row)
                if holds is False and witness is None:
                    witness = dict(new_row)

        columns = [*table.columns, new_name]
        base = {
            "title": table.title,
            "columns": columns,
            "rows": derived_rows,
            "n_rows": len(derived_rows),
            "n_cols": len(columns),
            "has_labels": table.has_labels,
            "exact": True,
            "name": new_name,
            "expression": inputs.expression,
            "is_relation": relation is not None,
        }

        if relation is None:
            status, kind = ResultStatus.RESULT, "table"
            payload = TableDeriveColumnOutput.model_validate(base).model_dump(mode="json")
            return InstrumentResult(
                output=attach_latex(payload, expression_latex=to_latex(inputs.expression, env)),
                status=status,
                artifact_kind=kind,
            )

        n_false = sum(1 for h in holds_per_row if h is False)
        n_undecided = sum(1 for h in holds_per_row if h is None)
        base["holds_per_row"] = holds_per_row
        base["n_false"] = n_false
        base["n_undecided"] = n_undecided
        base["witness"] = witness

        if n_false > 0:
            status, kind = ResultStatus.REFUTED, "counterexample"
        elif n_undecided > 0:
            status, kind = ResultStatus.UNDECIDED, "table"
        else:
            status, kind = ResultStatus.RESULT, "table"

        payload = TableDeriveColumnOutput.model_validate(base).model_dump(mode="json")
        return InstrumentResult(
            output=attach_latex(
                payload, expression_latex=relation_to_latex(inputs.expression, env)
            ),
            status=status,
            artifact_kind=kind,
        )


def _referenced_columns(
    expression: str,
    relation: tuple[str, str, str] | None,
    env: dict[str, dict[str, bool]],
    columns: list[str],
) -> list[str]:
    """Columns the expression actually names — extra label columns pass through."""
    texts = [expression] if relation is None else [relation[0], relation[2]]
    names: set[str] = set()
    for text in texts:
        names.update(str(symbol) for symbol in parse(text, env).free_symbols)
    unknown = sorted(names - set(columns))
    if unknown:
        raise ValueError(
            f"expression names {unknown} which are not columns — columns are {columns}"
        )
    return [name for name in columns if name in names]


def _contains_float(expr: Any) -> bool:
    if isinstance(expr, Float) or bool(getattr(expr, "is_Float", False)):
        return True
    atoms = getattr(expr, "atoms", None)
    if callable(atoms):
        return any(isinstance(atom, Float) for atom in atoms(Float))
    return False


def _eval_under(
    text: str,
    bound: dict[str, Any],
    env: dict[str, dict[str, bool]],
) -> Any:
    expr = parse(text, env)
    if _contains_float(expr):
        raise ValueError(
            f"inexact decimal in expression {text!r} — use a rational, never a float"
        )
    substituted = expr.subs(bound)
    if _contains_float(substituted):
        raise ValueError(
            f"deriving {text!r} produced a float — refused; keep the column exact"
        )
    return substituted


def _exact_result_string(expr: Any) -> str:
    simplified = simplify(expr)
    if _contains_float(simplified):
        raise ValueError("derived value is a float — refused; keep the column exact")
    return str(simplified)


def _relation_cell(holds: bool | None) -> str:
    if holds is True:
        return "true"
    if holds is False:
        return "false"
    return "undecided"


TABLE_DERIVE_COLUMN = TableDeriveColumn()
