"""``counterexample.search`` — cheap grid search for an input that breaks a relation.

Given a top-level relational expression (``d == a + b``) and bounded integer ranges per variable,
evaluate the relation over a deterministic Cartesian grid. The first assignment where the relation
is **provably false** is a definitive counterexample (``refuted``). Exhausting the search space (or
hitting ``max_samples``) without a witness is **weak support** (``result``) — absence of evidence
is never recorded as proof.
"""

from __future__ import annotations

import math
from itertools import product
from typing import Any

from pydantic import BaseModel, Field, model_validator
from sympy import Symbol

from app.models.enums import ResultStatus
from app.toolbench.adapter import InstrumentResult
from app.toolbench.instruments._sympy_support import (
    ENGINE,
    ENGINE_VERSION,
    attach_latex,
    parse,
    relation_holds,
    relation_to_latex,
    split_relation,
)

_MAX_VARIABLE_WIDTH = 50
_MAX_SEARCH_PRODUCT = 50_000


class VariableRange(BaseModel):
    min: int = Field(ge=-1000, le=1000)
    max: int = Field(ge=-1000, le=1000)

    @model_validator(mode="after")
    def _bounds_are_valid(self) -> VariableRange:
        if self.min > self.max:
            raise ValueError(f"min ({self.min}) must be <= max ({self.max})")
        width = self.max - self.min + 1
        if width > _MAX_VARIABLE_WIDTH:
            raise ValueError(
                f"variable range too wide ({width} values; max {_MAX_VARIABLE_WIDTH})"
            )
        return self


class CounterexampleSearchInput(BaseModel):
    relation: str = Field(
        min_length=1,
        max_length=500,
        description=(
            "A relational expression to falsify over integer assignments, using ==, !=, <, <=, >, "
            ">= at top level (e.g. 'd == a + b'). Use '==' for equality, not '='."
        ),
    )
    variables: dict[str, VariableRange] = Field(
        min_length=1,
        max_length=8,
        description="Inclusive integer bounds per variable name appearing in the relation.",
    )
    max_samples: int = Field(
        default=500,
        ge=1,
        le=5000,
        description="Maximum assignments to try before stopping (caps large grids).",
    )

    @model_validator(mode="after")
    def _search_space_is_bounded(self) -> CounterexampleSearchInput:
        product_size = 1
        for var_range in self.variables.values():
            product_size *= var_range.max - var_range.min + 1
            if product_size > _MAX_SEARCH_PRODUCT:
                raise ValueError(
                    f"search space too large (>{_MAX_SEARCH_PRODUCT} assignments)"
                )
        return self


class CounterexampleSearchOutput(BaseModel):
    relation: str
    search_space: dict[str, str]
    samples_tried: int
    truncated: bool
    found: bool
    witness: dict[str, str] | None = None
    witness_relation: str | None = None
    relation_latex: str | None = None  # render hints only — excluded from content hashes
    witness_relation_latex: str | None = None


def _integer_symbol_assumptions(names: frozenset[str]) -> dict[str, dict[str, bool]]:
    return {name: {"integer": True} for name in names}


def _relation_variable_names(relation: str, variable_names: frozenset[str]) -> frozenset[str]:
    """Return the subset of ``variable_names`` that appear free in ``relation``."""
    sym_flags = _integer_symbol_assumptions(variable_names)
    split = split_relation(relation)
    if split is None:
        raise ValueError("relation must contain a top-level relational operator")
    left_text, _op, right_text = split
    left = parse(left_text, sym_flags)
    right = parse(right_text, sym_flags)
    return frozenset(str(s) for s in left.free_symbols | right.free_symbols)


def _format_search_space(variables: dict[str, VariableRange]) -> dict[str, str]:
    return {
        name: f"{variables[name].min}..{variables[name].max}"
        for name in sorted(variables)
    }


def _search_product_size(variables: dict[str, VariableRange]) -> int:
    return math.prod(var_range.max - var_range.min + 1 for var_range in variables.values())


class CounterexampleSearch:
    """Grid search for a falsifying integer assignment (see module docstring)."""

    name = "counterexample.search"
    namespace = "counterexample"
    version = "0.1.0"
    engine = ENGINE
    engine_version = ENGINE_VERSION
    description = (
        "Search bounded integer ranges for an assignment that makes a relation false — a cheap "
        "falsifier. Finding a witness is a definitive counterexample; not finding one is weak "
        "support only, never proof."
    )
    InputModel = CounterexampleSearchInput
    OutputModel = CounterexampleSearchOutput

    def run(
        self, inputs: CounterexampleSearchInput, assumptions: dict[str, Any]
    ) -> InstrumentResult:
        if assumptions:
            raise ValueError("counterexample.search does not accept assumptions in v1")

        relation_parts = split_relation(inputs.relation)
        if relation_parts is None:
            raise ValueError("relation must contain a top-level relational operator")
        left_text, op, right_text = relation_parts

        declared = frozenset(inputs.variables)
        used = _relation_variable_names(inputs.relation, declared)
        if not used:
            raise ValueError("relation has no variables to search over")
        extra = declared - used
        if extra:
            raise ValueError(
                f"variables not used in relation: {', '.join(sorted(extra))}"
            )
        missing = used - declared
        if missing:
            raise ValueError(
                f"relation references undeclared variables: {', '.join(sorted(missing))}"
            )

        # Search only the variables that appear in the relation, in deterministic name order.
        search_vars = {name: inputs.variables[name] for name in sorted(used)}
        search_space = _format_search_space(search_vars)
        total_assignments = _search_product_size(search_vars)
        truncated = total_assignments > inputs.max_samples

        sym_flags = _integer_symbol_assumptions(frozenset(search_vars))
        left_expr = parse(left_text, sym_flags)
        right_expr = parse(right_text, sym_flags)

        samples_tried = 0
        value_lists = [
            range(search_vars[name].min, search_vars[name].max + 1) for name in sorted(used)
        ]
        names = sorted(used)

        for assignment_values in product(*value_lists):
            if samples_tried >= inputs.max_samples:
                break
            samples_tried += 1
            assignment = dict(zip(names, assignment_values, strict=True))
            subs = {Symbol(name, integer=True): value for name, value in assignment.items()}

            holds = relation_holds(
                left_expr.subs(subs),
                right_expr.subs(subs),
                op,
            )
            if holds is None:
                continue  # undecidable at this point — not a counterexample
            if not holds:
                left_val = left_expr.subs(subs)
                right_val = right_expr.subs(subs)
                witness_relation = f"{left_val} {op} {right_val}"
                payload = CounterexampleSearchOutput(
                    relation=inputs.relation,
                    search_space=search_space,
                    samples_tried=samples_tried,
                    truncated=truncated,
                    found=True,
                    witness={name: str(value) for name, value in assignment.items()},
                    witness_relation=witness_relation,
                ).model_dump(mode="json")
                return InstrumentResult(
                    output=attach_latex(
                        payload,
                        relation_latex=relation_to_latex(inputs.relation, sym_flags),
                        witness_relation_latex=relation_to_latex(witness_relation, {}),
                    ),
                    status=ResultStatus.REFUTED,
                    artifact_kind="counterexample",
                )

        payload = CounterexampleSearchOutput(
            relation=inputs.relation,
            search_space=search_space,
            samples_tried=samples_tried,
            truncated=truncated,
            found=False,
        ).model_dump(mode="json")
        return InstrumentResult(
            output=attach_latex(
                payload, relation_latex=relation_to_latex(inputs.relation, sym_flags)
            ),
            status=ResultStatus.RESULT,
            artifact_kind="derivation",
        )


COUNTEREXAMPLE_SEARCH = CounterexampleSearch()