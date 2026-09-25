"""``z3.satisfy`` — machine-checked model-finding under linear (and honest nonlinear) arithmetic.

Given typed variables and a set of top-level relational constraints, ask Z3 whether a
concrete assignment exists:

- **``result``** (``artifact_kind="model"``) — ``sat``: a concrete assignment of the declared
  variables (exact ints / rationals as strings).
- **``refuted``** (``artifact_kind="proof"``) — ``unsat``: no model exists. The satisfiability
  question is answered no; this is not a fabricated assignment.
- **``undecided``** (``artifact_kind="derivation"``) — ``unknown``, timeout, or solver
  incompleteness.

Unlike ``z3.prove``, there is no goal and no vacuous-hypotheses guard: ``unsat`` *is* the
honest no-model outcome. Top-level relations only in v1 — no boolean-connective parser,
no quantifiers.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.config import settings
from app.models.enums import ResultStatus
from app.toolbench.adapter import InstrumentResult
from app.toolbench.instruments._sympy_support import (
    attach_latex,
    relation_to_latex,
    split_relation,
)
from app.toolbench.instruments._z3_support import (
    ENGINE,
    ENGINE_VERSION,
    declare,
    relation_to_z3,
    satisfy,
    symbol_flags_for,
)

_MAX_VAR_NAME_LEN = 32
_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MAX_CONSTRAINTS = 16
_MAX_RELATION_LEN = 500


class Z3SatisfyInput(BaseModel):
    variables: dict[str, Literal["int", "real"]] = Field(
        min_length=1,
        max_length=8,
        description="Declared free variables and their sorts (int or real).",
    )
    constraints: list[str] = Field(
        default_factory=list,
        max_length=_MAX_CONSTRAINTS,
        description=(
            "Constraints — each a single top-level relation (lhs OP rhs). Conjoined. "
            "Empty means any assignment of the declared sorts is a model."
        ),
    )

    @field_validator("variables")
    @classmethod
    def _variable_names_are_safe(
        cls, value: dict[str, Literal["int", "real"]]
    ) -> dict[str, Literal["int", "real"]]:
        for name in value:
            if len(name) > _MAX_VAR_NAME_LEN:
                raise ValueError(
                    f"variable name too long ({len(name)} > {_MAX_VAR_NAME_LEN}): {name!r}"
                )
            if not _VAR_NAME_RE.match(name):
                raise ValueError(
                    f"invalid variable name {name!r} — use a simple identifier "
                    r"(e.g. x, y1, side_a)"
                )
        return value

    @field_validator("constraints")
    @classmethod
    def _constraints_are_bounded(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            text = item.strip()
            if not text:
                raise ValueError("constraints must not contain blank entries")
            if len(text) > _MAX_RELATION_LEN:
                raise ValueError(
                    f"constraint too long ({len(text)} > {_MAX_RELATION_LEN} characters)"
                )
            cleaned.append(text)
        return cleaned

    @model_validator(mode="after")
    def _constraints_are_relational(self) -> Z3SatisfyInput:
        for c in self.constraints:
            if split_relation(c) is None:
                raise ValueError(
                    f"constraint must contain a top-level relational operator: {c!r}"
                )
        return self


class Z3SatisfyOutput(BaseModel):
    variables: dict[str, str]
    constraints: list[str]
    satisfied: bool
    unsatisfiable: bool
    status_reason: str | None = None
    model: dict[str, str] | None = None
    certificate: str | None = None
    used_constraints: list[str] | None = None
    # render hints only — excluded from content hashes by the write-path latex stripper
    constraints_latex: list[str] | None = None


class Z3Satisfy:
    """Machine-checked model-finding over quantifier-free linear (honest nonlinear) arithmetic."""

    name = "z3.satisfy"
    namespace = "z3"
    version = "0.1.0"
    engine = ENGINE
    engine_version = ENGINE_VERSION
    description = (
        "Find a concrete model of typed linear-arithmetic constraints via Z3. "
        "sat yields an exact assignment; unsat is a machine-checked proof that no model "
        "exists; unknown is honest undecided — never a fabricated model."
    )
    InputModel = Z3SatisfyInput
    OutputModel = Z3SatisfyOutput

    def run(self, inputs: Z3SatisfyInput, assumptions: dict[str, Any]) -> InstrumentResult:
        if assumptions:
            raise ValueError("z3.satisfy does not accept assumptions in v1")

        flags = symbol_flags_for(dict(inputs.variables))
        env = {name: declare(name, sort) for name, sort in inputs.variables.items()}

        pairs: list[tuple[str, Any]] = []
        for index, constraint in enumerate(inputs.constraints):
            track = f"c{index}:{constraint}"
            pairs.append((track, relation_to_z3(constraint, env, flags)))

        outcome = satisfy(
            pairs,
            env=env,
            timeout_ms=settings.toolbench_z3_timeout_ms,
        )

        variables_out = {name: sort for name, sort in inputs.variables.items()}
        latex_kwargs = _latex_hints(inputs, flags)

        if outcome.kind == "sat":
            payload = Z3SatisfyOutput(
                variables=variables_out,
                constraints=list(inputs.constraints),
                satisfied=True,
                unsatisfiable=False,
                model=outcome.model,
            ).model_dump(mode="json")
            return InstrumentResult(
                output=attach_latex(payload, **latex_kwargs),
                status=ResultStatus.RESULT,
                artifact_kind="model",
            )

        if outcome.kind == "unsat":
            payload = Z3SatisfyOutput(
                variables=variables_out,
                constraints=list(inputs.constraints),
                satisfied=False,
                unsatisfiable=True,
                certificate=outcome.certificate,
                used_constraints=outcome.used_constraints,
            ).model_dump(mode="json")
            return InstrumentResult(
                output=attach_latex(payload, **latex_kwargs),
                status=ResultStatus.REFUTED,
                artifact_kind="proof",
            )

        payload = Z3SatisfyOutput(
            variables=variables_out,
            constraints=list(inputs.constraints),
            satisfied=False,
            unsatisfiable=False,
            status_reason=outcome.reason,
        ).model_dump(mode="json")
        return InstrumentResult(
            output=attach_latex(payload, **latex_kwargs),
            status=ResultStatus.UNDECIDED,
            artifact_kind="derivation",
        )


def _latex_hints(
    inputs: Z3SatisfyInput, flags: dict[str, dict[str, bool]]
) -> dict[str, str | list[str] | None]:
    constraints_l: list[str] = []
    for c in inputs.constraints:
        cl = relation_to_latex(c, flags)
        constraints_l.append(cl if cl is not None else c)
    return {
        "constraints_latex": constraints_l if constraints_l else None,
    }


Z3_SATISFY = Z3Satisfy()
