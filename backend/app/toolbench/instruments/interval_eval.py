"""``interval.eval`` — evaluate an expression to a proven numeric enclosure.

Two modes, chosen by whether the input carries a top-level relational operator:

- **value** — ``sqrt(2)`` → ``√2 ∈ [lo, hi]`` with explicit working precision. The
  interval is a **proven enclosure** (Arb ball, or ``mpmath.iv`` if flint is
  missing), never a float dressed as exact.
- **relation** — enclose both sides. A relation the enclosure *definitively*
  falsifies (intervals disjoint from a claimed equality; or entirely off an
  inequality) is ``refuted`` with the two bounds as witness. Overlap is
  ``undecided`` — never a fabricated certainty. An exact singleton match may
  ``result``.

Honesty that must not regress:

- Cannot enclose / timeout / missing library / free symbols / non-real →
  ``undecided`` (never a fabricated bound).
- A float literal in the input is a ``ValueError`` (422, mint nothing).
- Grade C on a supporting enclosure; Grade B only when the enclosure
  *refutes*. Never Grade A — an interval is not a kernel/SMT proof.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.models.enums import ResultStatus
from app.toolbench.adapter import InstrumentResult
from app.toolbench.instruments._interval_support import (
    ENGINE,
    ENGINE_VERSION,
    Enclosure,
    decide_relation,
    enclose,
    enclosure_latex,
)
from app.toolbench.instruments._sympy_support import (
    attach_latex,
    parse,
    relation_to_latex,
    split_relation,
    to_latex,
)

_DEFAULT_PREC = 64
_MIN_PREC = 16
_MAX_PREC = 1024


class IntervalEvalInput(BaseModel):
    expression: str = Field(
        min_length=1,
        max_length=1000,
        description=(
            "A closed-form real expression to enclose (e.g. 'sqrt(2)', 'pi', "
            "'exp(1)'), or a relation to test (==, !=, <, <=, >, >=). Use '==' "
            "for equality, not '='. Float literals are rejected."
        ),
    )
    precision_bits: int = Field(
        default=_DEFAULT_PREC,
        ge=_MIN_PREC,
        le=_MAX_PREC,
        description=(
            f"Working precision in bits (default {_DEFAULT_PREC}, "
            f"{_MIN_PREC}–{_MAX_PREC}). Recorded on the result."
        ),
    )


class IntervalEvalOutput(BaseModel):
    expression: str
    is_relation: bool
    lo: str | None = None
    hi: str | None = None
    left_lo: str | None = None
    left_hi: str | None = None
    right_lo: str | None = None
    right_hi: str | None = None
    holds: bool | None = None
    precision_bits: int
    method: str | None = None
    status_reason: str | None = None
    expression_latex: str | None = None
    enclosure_latex: str | None = None
    left_enclosure_latex: str | None = None
    right_enclosure_latex: str | None = None


class IntervalEval:
    """Proven numeric enclosure (see module docstring)."""

    name = "interval.eval"
    namespace = "interval"
    version = "0.1.0"
    engine = ENGINE
    engine_version = ENGINE_VERSION
    description = (
        "Evaluate an expression to a proven enclosure (Arb ball arithmetic), or "
        "test a relation against those bounds. A successful enclosure is not a "
        "proof. Disjoint intervals can refute; overlap is undecided. Missing "
        "library / timeout / domain is honest undecided — never a fabricated bound."
    )
    InputModel = IntervalEvalInput
    OutputModel = IntervalEvalOutput

    def run(self, inputs: IntervalEvalInput, assumptions: dict[str, Any]) -> InstrumentResult:
        if assumptions:
            raise ValueError("interval.eval does not accept assumptions in v1")

        timeout_ms = settings.toolbench_interval_timeout_ms
        relation = split_relation(inputs.expression)
        if relation is None:
            return self._run_value(inputs, timeout_ms)
        return self._run_relation(inputs, relation, timeout_ms)

    def _run_value(self, inputs: IntervalEvalInput, timeout_ms: int) -> InstrumentResult:
        expr = parse(inputs.expression, {})
        outcome = enclose(
            expr, precision_bits=inputs.precision_bits, timeout_ms=timeout_ms
        )
        if outcome.kind != "enclosed" or outcome.enclosure is None:
            payload = IntervalEvalOutput(
                expression=inputs.expression,
                is_relation=False,
                precision_bits=inputs.precision_bits,
                status_reason=outcome.reason,
            ).model_dump(mode="json")
            return InstrumentResult(
                output=attach_latex(payload, expression_latex=to_latex(inputs.expression, {})),
                status=ResultStatus.UNDECIDED,
                artifact_kind="derivation",
            )
        enc = outcome.enclosure
        payload = IntervalEvalOutput(
            expression=inputs.expression,
            is_relation=False,
            lo=enc.lo,
            hi=enc.hi,
            precision_bits=enc.precision_bits,
            method=enc.method,
        ).model_dump(mode="json")
        return InstrumentResult(
            output=attach_latex(
                payload,
                expression_latex=to_latex(inputs.expression, {}),
                enclosure_latex=enclosure_latex(enc),
            ),
            status=ResultStatus.RESULT,
            artifact_kind="derivation",
        )

    def _run_relation(
        self,
        inputs: IntervalEvalInput,
        relation: tuple[str, str, str],
        timeout_ms: int,
    ) -> InstrumentResult:
        left_text, op, right_text = relation
        left_out = enclose(
            parse(left_text, {}),
            precision_bits=inputs.precision_bits,
            timeout_ms=timeout_ms,
        )
        right_out = enclose(
            parse(right_text, {}),
            precision_bits=inputs.precision_bits,
            timeout_ms=timeout_ms,
        )
        latex_kwargs = {
            "expression_latex": relation_to_latex(inputs.expression, {}),
        }
        if left_out.kind != "enclosed" or right_out.kind != "enclosed":
            reason = left_out.reason or right_out.reason
            payload = IntervalEvalOutput(
                expression=inputs.expression,
                is_relation=True,
                precision_bits=inputs.precision_bits,
                status_reason=reason,
                **_side_fields(left_out.enclosure, right_out.enclosure),
            ).model_dump(mode="json")
            return InstrumentResult(
                output=attach_latex(
                    payload, **latex_kwargs, **_side_latex(left_out.enclosure, right_out.enclosure)
                ),
                status=ResultStatus.UNDECIDED,
                artifact_kind="derivation",
            )

        left_enc = left_out.enclosure
        right_enc = right_out.enclosure
        assert left_enc is not None and right_enc is not None
        holds = decide_relation(left_enc, right_enc, op)
        if holds is None:
            status, kind, reason = ResultStatus.UNDECIDED, "derivation", "overlap"
        elif holds:
            status, kind, reason = ResultStatus.RESULT, "derivation", None
        else:
            status, kind, reason = ResultStatus.REFUTED, "counterexample", None

        payload = IntervalEvalOutput(
            expression=inputs.expression,
            is_relation=True,
            holds=holds,
            precision_bits=inputs.precision_bits,
            method=left_enc.method,
            status_reason=reason,
            **_side_fields(left_enc, right_enc),
        ).model_dump(mode="json")
        return InstrumentResult(
            output=attach_latex(
                payload, **latex_kwargs, **_side_latex(left_enc, right_enc)
            ),
            status=status,
            artifact_kind=kind,
        )


def _side_fields(
    left: Enclosure | None, right: Enclosure | None
) -> dict[str, str | None]:
    return {
        "left_lo": left.lo if left else None,
        "left_hi": left.hi if left else None,
        "right_lo": right.lo if right else None,
        "right_hi": right.hi if right else None,
    }


def _side_latex(
    left: Enclosure | None, right: Enclosure | None
) -> dict[str, str | None]:
    return {
        "left_enclosure_latex": enclosure_latex(left) if left else None,
        "right_enclosure_latex": enclosure_latex(right) if right else None,
    }


INTERVAL_EVAL = IntervalEval()
