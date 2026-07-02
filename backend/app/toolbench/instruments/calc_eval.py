"""``calc.eval`` — the primitive exact calculator, and the bench's falsification engine.

Two modes, chosen by whether the input carries a top-level relational operator:

- **value** — ``2 + 2`` → ``4``; ``1/3 + 1/6`` → ``1/2``; ``sqrt(2)`` → ``sqrt(2)`` (exact, never a
  float — the ledger hashes the output, and a float is not an exact hash);
- **relation** — ``3**2 + 4**2 == 5**2`` → holds (``result``); ``5 == 7`` → does not hold
  (``refuted`` — a counterexample, the asymmetrically-strong outcome); ``x**2 == 2*x`` → cannot be
  decided (``undecided``).

Exact-equality over concrete values is what lets ``calc.eval`` *falsify* a claim: it settles a
specific case exactly and reports ``refuted`` when the relation is false. Relations that still carry
free symbols are honestly ``undecided`` — the seam to escalate, never a silent pass.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import ResultStatus
from app.toolbench.adapter import InstrumentResult
from app.toolbench.instruments._sympy_support import (
    ENGINE,
    ENGINE_VERSION,
    attach_latex,
    latex_of,
    parse,
    relation_holds,
    relation_to_latex,
    split_relation,
    symbol_assumptions,
    to_latex,
)


class CalcEvalInput(BaseModel):
    expression: str = Field(
        min_length=1,
        max_length=1000,
        description=(
            "An exact expression to evaluate (e.g. '3**2 + 4**2', '1/3 + 1/6', 'sqrt(2)'), or a "
            "relation to test using a relational operator (==, !=, <, <=, >, >=), e.g. "
            "'3**2 + 4**2 == 5**2'. Use '==' for equality, not '='."
        ),
    )


class CalcEvalOutput(BaseModel):
    expression: str  # the input, echoed for the provenance record
    is_relation: bool  # True when a relational operator was evaluated
    value: str | None = None  # value mode: the exact result (e.g. "4", "1/2", "sqrt(2)")
    holds: bool | None = None  # relation mode: does it hold? None when it could not be decided
    expression_latex: str | None = None  # render hint only — excluded from content hashes
    value_latex: str | None = None


class CalcEval:
    """The primitive exact calculator (see module docstring)."""

    name = "calc.eval"
    namespace = "calc"
    version = "0.1.0"
    engine = ENGINE
    engine_version = ENGINE_VERSION
    description = (
        "Evaluate an expression exactly, or test a relation (==, !=, <, <=, >, >=) — the exact "
        "falsification engine: a false relation is reported as a refuted counterexample."
    )
    InputModel = CalcEvalInput
    OutputModel = CalcEvalOutput

    def run(self, inputs: CalcEvalInput, assumptions: dict[str, Any]) -> InstrumentResult:
        syms = symbol_assumptions(assumptions)
        relation = split_relation(inputs.expression)

        if relation is None:
            value = parse(inputs.expression, syms)
            payload = CalcEvalOutput(
                expression=inputs.expression, is_relation=False, value=str(value)
            ).model_dump(mode="json")
            return InstrumentResult(
                output=attach_latex(
                    payload,
                    expression_latex=to_latex(inputs.expression, syms),
                    value_latex=latex_of(value),
                ),
                status=ResultStatus.RESULT,
                artifact_kind="derivation",
            )

        left_text, op, right_text = relation
        holds = relation_holds(parse(left_text, syms), parse(right_text, syms), op)
        if holds is None:
            status, kind = ResultStatus.UNDECIDED, "derivation"
        elif holds:
            status, kind = ResultStatus.RESULT, "derivation"
        else:  # the falsification: a false relation is a counterexample
            status, kind = ResultStatus.REFUTED, "counterexample"

        payload = CalcEvalOutput(
            expression=inputs.expression, is_relation=True, holds=holds
        ).model_dump(mode="json")
        return InstrumentResult(
            output=attach_latex(
                payload, expression_latex=relation_to_latex(inputs.expression, syms)
            ),
            status=status,
            artifact_kind=kind,
        )


CALC_EVAL = CalcEval()
