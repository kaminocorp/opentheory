"""``z3.prove`` — machine-checked validity under linear (and honest nonlinear) arithmetic.

Given typed variables (``int`` / ``real`` / ``bool``), hypotheses, and a goal — each a
relation or a quantifier-free boolean formula — assert ``hypotheses ∧ ¬goal`` in Z3 and
return one of the three honest outcomes:

- **``result``** (``artifact_kind="proof"``) — ``unsat``: the goal is entailed for all assignments
  (when the hypotheses themselves are satisfiable — see the vacuous-proof guard).
- **``refuted``** (``artifact_kind="counterexample"``) — ``sat``: a concrete counter-model.
- **``undecided``** (``artifact_kind="derivation"``) — ``unknown``, contradictory hypotheses, or
  hypotheses the solver could not decide.

Unlike ``counterexample.search``, a supporting ``result`` here is a *proof*, not weak support.
Quantifiers stay out of scope.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.config import settings
from app.models.enums import ResultStatus
from app.toolbench.adapter import InstrumentResult
from app.toolbench.instruments._sympy_support import attach_latex
from app.toolbench.instruments._z3_support import (
    ENGINE,
    ENGINE_VERSION,
    RESERVED_NAMES,
    Z3SortName,
    assert_formula_shape,
    declare,
    formula_to_latex,
    formula_to_z3,
    solve,
)

_MAX_VAR_NAME_LEN = 32
_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MAX_CONSTRAINTS = 16
_MAX_RELATION_LEN = 500


class Z3ProveInput(BaseModel):
    variables: dict[str, Z3SortName] = Field(
        min_length=1,
        max_length=8,
        description="Declared free variables and their sorts (int, real, or bool).",
    )
    constraints: list[str] = Field(
        default_factory=list,
        max_length=_MAX_CONSTRAINTS,
        description=(
            "Hypotheses — each a relation or a boolean formula "
            "(And/Or/Not/Implies/Xor/Equivalent). Conjoined. "
            "Empty means prove the goal unconditionally over the declared sorts."
        ),
    )
    goal: str = Field(
        min_length=1,
        max_length=_MAX_RELATION_LEN,
        description=(
            "The relation or boolean formula to prove under the hypotheses "
            "(e.g. x + y > 0, or Implies(And(P, Q), P))."
        ),
    )

    @field_validator("variables")
    @classmethod
    def _variable_names_are_safe(cls, value: dict[str, Z3SortName]) -> dict[str, Z3SortName]:
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
            if name in RESERVED_NAMES:
                raise ValueError(
                    f"variable name {name!r} is reserved for the formula language"
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

    @field_validator("goal")
    @classmethod
    def _goal_is_stripped(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("goal must not be empty")
        return text

    @model_validator(mode="after")
    def _goal_is_a_formula(self) -> Z3ProveInput:
        # Cheap structural check at validation time; full sort checking still happens in run.
        try:
            assert_formula_shape(self.goal)
        except ValueError as exc:
            raise ValueError(f"goal {exc}") from exc
        for c in self.constraints:
            try:
                assert_formula_shape(c)
            except ValueError as exc:
                raise ValueError(f"constraint {c!r}: {exc}") from exc
        return self


class Z3ProveOutput(BaseModel):
    goal: str
    variables: dict[str, str]
    constraints: list[str]
    proven: bool
    refuted: bool
    status_reason: str | None = None
    witness: dict[str, str] | None = None
    certificate: str | None = None
    used_hypotheses: list[str] | None = None
    # render hints only — excluded from content hashes by the write-path latex stripper
    goal_latex: str | None = None
    constraints_latex: list[str] | None = None


class Z3Prove:
    """Machine-checked validity over quantifier-free arithmetic and propositional connectives."""

    name = "z3.prove"
    namespace = "z3"
    version = "0.2.0"
    engine = ENGINE
    engine_version = ENGINE_VERSION
    description = (
        "Prove a relation or boolean formula under typed hypotheses via Z3. "
        "Sorts: int, real, bool. Connectives: And, Or, Not, Implies, Xor, Equivalent. "
        "unsat is a machine-checked proof (when hypotheses are satisfiable); sat yields a "
        "concrete counter-model; unknown is honest undecided — never a pass. "
        "Quantifiers are out of scope."
    )
    InputModel = Z3ProveInput
    OutputModel = Z3ProveOutput

    def run(self, inputs: Z3ProveInput, assumptions: dict[str, Any]) -> InstrumentResult:
        if assumptions:
            raise ValueError("z3.prove does not accept assumptions in v1")

        env = {name: declare(name, sort) for name, sort in inputs.variables.items()}

        # Translate goal + constraints through the closed formula allow-list (no eval).
        goal_z3 = formula_to_z3(inputs.goal, env)
        hyp_pairs: list[tuple[str, Any]] = []
        for index, constraint in enumerate(inputs.constraints):
            # Track names are stable labels for the unsat-core (index + original text).
            track = f"h{index}:{constraint}"
            hyp_pairs.append((track, formula_to_z3(constraint, env)))

        # By here every free symbol is a declared variable: relation_to_z3 → to_z3 (above) raises on
        # any symbol not in ``env`` as the goal/constraints are translated. Unused *declared*
        # variables are allowed — they only widen the quantified space for a validity check (unlike
        # counterexample.search, which searches a grid over every declared var).
        outcome = solve(
            hyp_pairs,
            goal_z3,
            env=env,
            timeout_ms=settings.toolbench_z3_timeout_ms,
        )

        variables_out = {name: sort for name, sort in inputs.variables.items()}
        latex_kwargs = _latex_hints(inputs)

        if outcome.kind == "proven":
            payload = Z3ProveOutput(
                goal=inputs.goal,
                variables=variables_out,
                constraints=list(inputs.constraints),
                proven=True,
                refuted=False,
                certificate=outcome.certificate,
                used_hypotheses=outcome.used_hypotheses,
            ).model_dump(mode="json")
            return InstrumentResult(
                output=attach_latex(payload, **latex_kwargs),
                status=ResultStatus.RESULT,
                artifact_kind="proof",
            )

        if outcome.kind == "refuted":
            payload = Z3ProveOutput(
                goal=inputs.goal,
                variables=variables_out,
                constraints=list(inputs.constraints),
                proven=False,
                refuted=True,
                witness=outcome.model,
            ).model_dump(mode="json")
            return InstrumentResult(
                output=attach_latex(payload, **latex_kwargs),
                status=ResultStatus.REFUTED,
                artifact_kind="counterexample",
            )

        # undecided
        payload = Z3ProveOutput(
            goal=inputs.goal,
            variables=variables_out,
            constraints=list(inputs.constraints),
            proven=False,
            refuted=False,
            status_reason=outcome.reason,
        ).model_dump(mode="json")
        return InstrumentResult(
            output=attach_latex(payload, **latex_kwargs),
            status=ResultStatus.UNDECIDED,
            artifact_kind="derivation",
        )


def _latex_hints(inputs: Z3ProveInput) -> dict[str, str | list[str] | None]:
    goal_l = formula_to_latex(inputs.goal)
    constraints_l: list[str] = []
    for c in inputs.constraints:
        cl = formula_to_latex(c)
        constraints_l.append(cl if cl is not None else c)
    return {
        "goal_latex": goal_l,
        "constraints_latex": constraints_l if constraints_l else None,
    }


Z3_PROVE = Z3Prove()
