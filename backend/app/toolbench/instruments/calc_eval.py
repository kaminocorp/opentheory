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
from sympy import simplify

from app.models.enums import ResultStatus
from app.toolbench.adapter import InstrumentResult
from app.toolbench.instruments._sympy_support import (
    ENGINE,
    ENGINE_VERSION,
    parse,
    symbol_assumptions,
)

# Two-char operators must be tested before their one-char prefixes ("<=" before "<"); a lone "="
# is rejected (see ``_split_relation``) so equality is always the unambiguous "==".
_RELATIONAL_OPS = ("==", "!=", "<=", ">=", "<", ">")


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


def _split_relation(text: str) -> tuple[str, str, str] | None:
    """Split ``text`` at its first top-level relational operator → ``(left, op, right)``.

    Only depth-0 operators split (so a relational buried inside ``Max(a < b, ...)`` — unusual —
    is left for the parser). Returns ``None`` when the input is a plain expression. A lone ``=``
    (not part of ``==`` / ``<=`` / ``>=`` / ``!=``) is a caller mistake and raises.
    """
    depth = 0
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0:
            for op in _RELATIONAL_OPS:
                if text.startswith(op, i):
                    return text[:i].strip(), op, text[i + len(op) :].strip()
            if ch == "=":  # a lone '=' at top level — not one of the operators above
                raise ValueError("use '==' for equality, not '='")
        i += 1
    return None


def _relation_holds(left: Any, right: Any, op: str) -> bool | None:
    """Decide ``left op right`` exactly → ``True`` / ``False`` / ``None`` (could not decide).

    ``==`` / ``!=`` hinge on whether the simplified difference is provably zero; the inequalities
    need its sign, which is only available for a concrete (symbol-free) real difference. Anything
    SymPy cannot settle returns ``None`` — recorded as ``undecided``, never guessed.
    """
    diff = simplify(left - right)
    is_zero = diff.is_zero  # True / False / None (fuzzy)

    if op == "==":
        return is_zero
    if op == "!=":
        return None if is_zero is None else (not is_zero)

    # Inequalities: need a decidable sign of a concrete real difference.
    if diff.free_symbols:
        return None
    if is_zero:
        sign = 0
    elif diff.is_positive:
        sign = 1
    elif diff.is_negative:
        sign = -1
    else:  # non-real / undecidable magnitude
        return None
    return {"<": sign < 0, "<=": sign <= 0, ">": sign > 0, ">=": sign >= 0}[op]


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
        relation = _split_relation(inputs.expression)

        if relation is None:
            value = parse(inputs.expression, syms)
            output = CalcEvalOutput(
                expression=inputs.expression, is_relation=False, value=str(value)
            )
            return InstrumentResult(
                output=output.model_dump(mode="json"),
                status=ResultStatus.RESULT,
                artifact_kind="derivation",
            )

        left_text, op, right_text = relation
        holds = _relation_holds(parse(left_text, syms), parse(right_text, syms), op)
        if holds is None:
            status, kind = ResultStatus.UNDECIDED, "derivation"
        elif holds:
            status, kind = ResultStatus.RESULT, "derivation"
        else:  # the falsification: a false relation is a counterexample
            status, kind = ResultStatus.REFUTED, "counterexample"

        output = CalcEvalOutput(expression=inputs.expression, is_relation=True, holds=holds)
        return InstrumentResult(
            output=output.model_dump(mode="json"), status=status, artifact_kind=kind
        )


CALC_EVAL = CalcEval()
