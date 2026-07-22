"""``z3.prove`` — machine-checked validity under linear (and honest nonlinear) arithmetic.

Given typed variables, a set of top-level relational hypotheses, and a goal relation, assert
``hypotheses ∧ ¬goal`` in Z3 and return one of the three honest outcomes:

- **``result``** (``artifact_kind="proof"``) — ``unsat``: the goal is entailed for all assignments
  (when the hypotheses themselves are satisfiable — see the vacuous-proof guard).
- **``refuted``** (``artifact_kind="counterexample"``) — ``sat``: a concrete counter-model.
- **``undecided``** (``artifact_kind="derivation"``) — ``unknown``, contradictory hypotheses, or
  hypotheses the solver could not decide.

Unlike ``counterexample.search``, a supporting ``result`` here is a *proof*, not weak support.
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
    solve,
    symbol_flags_for,
)

_MAX_VAR_NAME_LEN = 32
_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MAX_CONSTRAINTS = 16
_MAX_RELATION_LEN = 500


class Z3ProveInput(BaseModel):
    variables: dict[str, Literal["int", "real"]] = Field(
        min_length=1,
        max_length=8,
        description="Declared free variables and their sorts (int or real).",
    )
    constraints: list[str] = Field(
        default_factory=list,
        max_length=_MAX_CONSTRAINTS,
        description=(
            "Hypotheses — each a single top-level relation (lhs OP rhs). Conjoined. "
            "Empty means prove the goal unconditionally over the declared sorts."
        ),
    )
    goal: str = Field(
        min_length=1,
        max_length=_MAX_RELATION_LEN,
        description="The relation to prove under the hypotheses (top-level OP).",
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

    @field_validator("goal")
    @classmethod
    def _goal_is_stripped(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("goal must not be empty")
        return text

    @model_validator(mode="after")
    def _goal_is_relational(self) -> Z3ProveInput:
        # Cheap structural check at validation time; full parse still happens in run.
        if split_relation(self.goal) is None:
            raise ValueError("goal must contain a top-level relational operator")
        for c in self.constraints:
            if split_relation(c) is None:
                raise ValueError(
                    f"constraint must contain a top-level relational operator: {c!r}"
                )
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
    """Machine-checked validity over quantifier-free linear (and honest nonlinear) arithmetic."""

    name = "z3.prove"
    namespace = "z3"
    version = "0.1.0"
    engine = ENGINE
    engine_version = ENGINE_VERSION
    description = (
        "Prove a relational goal under typed linear-arithmetic hypotheses via Z3. "
        "unsat is a machine-checked proof (when hypotheses are satisfiable); sat yields a "
        "concrete counter-model; unknown is honest undecided — never a pass."
    )
    InputModel = Z3ProveInput
    OutputModel = Z3ProveOutput

    def run(self, inputs: Z3ProveInput, assumptions: dict[str, Any]) -> InstrumentResult:
        if assumptions:
            raise ValueError("z3.prove does not accept assumptions in v1")

        flags = symbol_flags_for(dict(inputs.variables))
        env = {name: declare(name, sort) for name, sort in inputs.variables.items()}

        # Translate goal + constraints through the hardened parser + closed allow-list.
        goal_z3 = relation_to_z3(inputs.goal, env, flags)
        hyp_pairs: list[tuple[str, Any]] = []
        for index, constraint in enumerate(inputs.constraints):
            # Track names are stable labels for the unsat-core (index + original text).
            track = f"h{index}:{constraint}"
            hyp_pairs.append((track, relation_to_z3(constraint, env, flags)))

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
        latex_kwargs = _latex_hints(inputs, flags)

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


def _latex_hints(
    inputs: Z3ProveInput, flags: dict[str, dict[str, bool]]
) -> dict[str, str | list[str] | None]:
    goal_l = relation_to_latex(inputs.goal, flags)
    constraints_l: list[str] = []
    for c in inputs.constraints:
        cl = relation_to_latex(c, flags)
        constraints_l.append(cl if cl is not None else c)
    return {
        "goal_latex": goal_l,
        "constraints_latex": constraints_l if constraints_l else None,
    }


Z3_PROVE = Z3Prove()
