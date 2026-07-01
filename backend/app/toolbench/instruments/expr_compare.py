"""``expr.compare`` — *are two expressions the same thing?* — the workbench's core verb.

Compares ``left`` and ``right`` by reducing ``simplify(left - right)``, with the **three honest
outcomes** the whole bench is built around:

- ``equivalent`` — the difference is **provably zero** (``is_zero``) → ``result``;
- ``not_equivalent`` — the difference is **provably non-zero** (``is_zero is False``, a witness) →
  ``refuted``;
- ``unknown`` — SymPy cannot decide whether the difference is zero (free symbols remain, *or* a
  constant it cannot settle — e.g. ``cos(π/7) − cos(2π/7) + cos(3π/7)`` vs ``½``, a true identity
  ``simplify`` does not close) → ``undecided``: they *might* still be equal, but the CAS could not
  decide. This is the seam to escalate to a proof (the deferred Z3/Lean verifier), **never**
  rendered as a pass. Refuting only on a *proven* non-zero (not merely "the residue is a constant")
  is what keeps a true identity from being reported as a false counterexample.

Assumptions plumb straight through: with ``{"x": {"positive": true}}`` the difference
``√(x²) − x`` reduces to ``0`` (equivalent), where without it the same comparison is ``undecided``.
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


class ExprCompareInput(BaseModel):
    left: str = Field(
        min_length=1,
        max_length=1000,
        description="Left-hand expression, e.g. '(a + b)**2 - 2*a*b'.",
    )
    right: str = Field(
        min_length=1, max_length=1000, description="Right-hand expression, e.g. 'a**2 + b**2'."
    )


class ExprCompareOutput(BaseModel):
    # True (equivalent) / False (not equivalent) / None (could not decide).
    equivalent: bool | None
    # The simplified difference: "0" when equivalent, the witness constant when not, the unreduced
    # form when undecided — so provenance always shows *why* the outcome is what it is.
    difference: str


class ExprCompare:
    """Decide expression equivalence via ``simplify(left - right)`` (see module docstring)."""

    name = "expr.compare"
    namespace = "expr"
    version = "0.1.0"
    engine = ENGINE
    engine_version = ENGINE_VERSION
    description = (
        "Are two expressions equivalent? Reduces simplify(left - right) to one of three outcomes: "
        "equivalent (result), not equivalent with a witness (refuted), or unknown (undecided)."
    )
    InputModel = ExprCompareInput
    OutputModel = ExprCompareOutput

    def run(self, inputs: ExprCompareInput, assumptions: dict[str, Any]) -> InstrumentResult:
        syms = symbol_assumptions(assumptions)
        difference = simplify(parse(inputs.left, syms) - parse(inputs.right, syms))

        if difference.is_zero:  # provably zero → equivalent
            equivalent, status, kind = True, ResultStatus.RESULT, "derivation"
        elif difference.is_zero is False:  # provably non-zero → a definite witness (refuted)
            equivalent, status, kind = False, ResultStatus.REFUTED, "counterexample"
        else:
            # is_zero is None → SymPy could not decide: free symbols remain, OR it is a constant
            # simplify cannot settle (a true identity would then falsely refute if we keyed off
            # is_number). Escalate, never guess. See the module docstring for the worked example.
            equivalent, status, kind = None, ResultStatus.UNDECIDED, "derivation"

        output = ExprCompareOutput(equivalent=equivalent, difference=str(difference))
        return InstrumentResult(
            output=output.model_dump(mode="json"), status=status, artifact_kind=kind
        )


EXPR_COMPARE = ExprCompare()
