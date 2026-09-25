"""``lean.prove`` — kernel-checked Lean 4 snippet (optional toolchain).

Accepts a bounded Lean 4 snippet. A supporting ``result`` is a *proof*
(``artifact_kind="proof"``) only when the installed ``lean`` binary typechecks
the snippet and the source has no cheat constructs. Everything else is honest:

- **failed** (status ``undecided``) — type error, ``sorry`` / ``axiom``, no theorem.
  A failed check is **not** a refutation of the claim.
- **undecided** — missing toolchain or soft timeout.
- A crash / sandbox kill is an exception: the write path mints nothing.

Lean is optional. If ``lean`` is not on PATH the instrument still conforms and
returns ``undecided`` / ``unavailable`` — ``z3.prove`` and the rest keep working.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.models.enums import ResultStatus
from app.toolbench.adapter import InstrumentResult
from app.toolbench.instruments._lean_support import (
    ENGINE,
    LeanCheck,
    check_source,
    engine_version,
)

_MAX_SOURCE_LEN = 8000
_MAX_LINES = 200


class LeanProveInput(BaseModel):
    source: str = Field(
        min_length=1,
        max_length=_MAX_SOURCE_LEN,
        description=(
            "A bounded Lean 4 snippet. v1 is prelude/Init only — no imports, no "
            "Mathlib, no sorry/axiom/opaque/unsafe/IO. Must declare a theorem, "
            "lemma, or example."
        ),
    )

    @field_validator("source")
    @classmethod
    def _source_is_bounded(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("source must not be empty")
        lines = text.count("\n") + 1
        if lines > _MAX_LINES:
            raise ValueError(f"source too long ({lines} > {_MAX_LINES} lines)")
        if len(text) > _MAX_SOURCE_LEN:
            raise ValueError(
                f"source too long ({len(text)} > {_MAX_SOURCE_LEN} characters)"
            )
        return text


class LeanProveOutput(BaseModel):
    source: str
    outcome: Literal["proved", "failed", "undecided"]
    proven: bool
    status_reason: str | None = None
    banned_constructs: list[str] | None = None
    diagnostics: str | None = None
    lean_version: str | None = None
    certificate: str | None = None


class LeanProve:
    """Kernel-checked Lean 4 snippet. Optional toolchain; never fakes a proof."""

    name = "lean.prove"
    namespace = "lean"
    version = "0.1.0"
    engine = ENGINE
    engine_version = engine_version()
    description = (
        "Typecheck a bounded Lean 4 snippet with the kernel. A supporting result "
        "is a machine-checked proof (Grade A) only when lean accepts the file and "
        "the source has no sorry/axiom/IO. Missing lean, timeout, or a failed "
        "check are honest undecided — never a pass. Optional toolchain: no lean "
        "on PATH does not break other instruments."
    )
    InputModel = LeanProveInput
    OutputModel = LeanProveOutput

    def run(self, inputs: LeanProveInput, assumptions: dict[str, Any]) -> InstrumentResult:
        if assumptions:
            raise ValueError("lean.prove does not accept assumptions in v1")

        timeout_s = _soft_timeout_s()
        check = check_source(inputs.source, timeout_s=timeout_s)
        if check.kind == "crash":
            # Fail closed: a dead checker is not an outcome. Mint nothing.
            raise RuntimeError(
                check.diagnostics or "lean process crashed; no result recorded"
            )
        return _result_from_check(inputs.source, check)


def _soft_timeout_s() -> float:
    """Lean's internal budget, kept strictly under the subprocess wall-clock.

    A hang that ignores this still hits the sandbox kill (422, mints nothing).
    The soft budget exists so ordinary slow typechecks become citable ``undecided``.
    """
    soft = settings.toolbench_lean_timeout_ms / 1000.0
    wall = settings.toolbench_wall_timeout_s
    # Leave a 2s margin under the wall so the instrument can return undecided.
    return min(soft, max(0.5, wall - 2.0))


def _result_from_check(source: str, check: LeanCheck) -> InstrumentResult:
    if check.kind == "proved":
        payload = LeanProveOutput(
            source=source,
            outcome="proved",
            proven=True,
            certificate="lean-kernel",
            lean_version=check.lean_version,
            diagnostics=check.diagnostics or None,
        ).model_dump(mode="json")
        return InstrumentResult(
            output=payload,
            status=ResultStatus.RESULT,
            artifact_kind="proof",
        )

    if check.kind == "failed":
        payload = LeanProveOutput(
            source=source,
            outcome="failed",
            proven=False,
            status_reason=check.reason or "failed",
            banned_constructs=list(check.banned_constructs) or None,
            diagnostics=check.diagnostics or None,
            lean_version=check.lean_version,
        ).model_dump(mode="json")
        return InstrumentResult(
            output=payload,
            status=ResultStatus.UNDECIDED,
            artifact_kind="derivation",
        )

    # timeout / unavailable (and any future non-proof kind) — never a pass
    payload = LeanProveOutput(
        source=source,
        outcome="undecided",
        proven=False,
        status_reason=check.reason or check.kind,
        diagnostics=check.diagnostics or None,
        lean_version=check.lean_version,
    ).model_dump(mode="json")
    return InstrumentResult(
        output=payload,
        status=ResultStatus.UNDECIDED,
        artifact_kind="derivation",
    )


LEAN_PROVE = LeanProve()
