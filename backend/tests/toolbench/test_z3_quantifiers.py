"""0.39.0 — first-order ForAll / Exists on ``z3.prove`` / ``z3.satisfy``.

Extends the 0.38.0 closed formula AST (no ``eval``, no shared-SymPy-gate widening).
Honesty contract is unchanged: Grade A / ``proven`` only on a real Z3 validity
success; vacuous hypotheses stay undecided; parse / If / injection failures raise
(mint nothing).
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.models.enums import ResultStatus
from app.toolbench.execution import limits_for, run_bounded_sync
from app.toolbench.instruments._z3_support import formula_to_latex
from app.toolbench.instruments.z3_prove import Z3_PROVE
from app.toolbench.instruments.z3_satisfy import Z3_SATISFY

# Motivating tautology: ∀x. x + 0 = x. Impossible before 0.39.0 as an explicit quantifier.
_FORALL_IDENTITY_INPUTS = {
    "variables": {"x": "int"},
    "constraints": [],
    "goal": "ForAll(x, x + 0 == x)",
}


def _prove(inputs: dict[str, Any], assumptions: dict[str, Any] | None = None):
    return Z3_PROVE.run(Z3_PROVE.InputModel.model_validate(inputs), assumptions or {})


def _satisfy(inputs: dict[str, Any], assumptions: dict[str, Any] | None = None):
    return Z3_SATISFY.run(Z3_SATISFY.InputModel.model_validate(inputs), assumptions or {})


# --- prove: happy path ---------------------------------------------------------------------------


def test_prove_forall_identity() -> None:
    result = _prove(_FORALL_IDENTITY_INPUTS)
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "proof"
    assert result.output["proven"] is True
    assert result.output["refuted"] is False
    assert result.output["certificate"] == "unsat"
    assert result.output["witness"] is None
    assert not any(isinstance(v, float) for v in result.output.values())


def test_prove_forall_successor_exists() -> None:
    """∀x. ∃y. y = x + 1 — alternating quantifiers Z3 can close over ints."""
    result = _prove(
        {
            "variables": {"x": "int", "y": "int"},
            "constraints": [],
            "goal": "ForAll(x, Exists(y, y == x + 1))",
        }
    )
    assert result.status is ResultStatus.RESULT
    assert result.output["proven"] is True


def test_prove_forall_positive_successor() -> None:
    result = _prove(
        {
            "variables": {"x": "int"},
            "constraints": [],
            "goal": "ForAll(x, Implies(x > 0, x + 1 > 1))",
        }
    )
    assert result.status is ResultStatus.RESULT
    assert result.output["proven"] is True


def test_prove_forall_excluded_middle() -> None:
    result = _prove(
        {
            "variables": {"P": "bool"},
            "constraints": [],
            "goal": "ForAll(P, Or(P, Not(P)))",
        }
    )
    assert result.status is ResultStatus.RESULT
    assert result.output["proven"] is True


def test_prove_multi_binder_commutativity() -> None:
    result = _prove(
        {
            "variables": {"x": "int", "y": "int"},
            "constraints": [],
            "goal": "ForAll(x, y, x + y == y + x)",
        }
    )
    assert result.status is ResultStatus.RESULT
    assert result.output["proven"] is True


def test_prove_forall_under_hypothesis() -> None:
    result = _prove(
        {
            "variables": {"x": "int"},
            "constraints": ["ForAll(x, x * x >= 0)"],
            "goal": "ForAll(x, Implies(x == 2, x * x >= 0))",
        }
    )
    assert result.status is ResultStatus.RESULT
    assert result.output["proven"] is True


# --- prove: refuted / vacuous --------------------------------------------------------------------


def test_prove_forall_positive_is_refuted() -> None:
    """∀x. x > 0 is false over the integers — sat of the negation, never a proof."""
    result = _prove(
        {
            "variables": {"x": "int"},
            "constraints": [],
            "goal": "ForAll(x, x > 0)",
        }
    )
    assert result.status is ResultStatus.REFUTED
    assert result.artifact_kind == "counterexample"
    assert result.output["refuted"] is True
    assert result.output["proven"] is False
    witness = result.output["witness"]
    assert witness is not None
    assert isinstance(witness["x"], str)
    assert "." not in witness["x"]


def test_prove_exists_least_integer_is_refuted() -> None:
    """∃x. ∀y. y > x — no least integer. Closed false sentence."""
    result = _prove(
        {
            "variables": {"x": "int", "y": "int"},
            "constraints": [],
            "goal": "Exists(x, ForAll(y, y > x))",
        }
    )
    assert result.status is ResultStatus.REFUTED
    assert result.output["refuted"] is True


def test_prove_exists_contradiction_is_refuted() -> None:
    result = _prove(
        {
            "variables": {"x": "int"},
            "constraints": [],
            "goal": "Exists(x, And(x > 0, x < 0))",
        }
    )
    assert result.status is ResultStatus.REFUTED
    assert result.output["refuted"] is True


def test_vacuous_forall_false_is_undecided_never_a_proof() -> None:
    """∀x. (x > 0 ∧ x < 0) as a hypothesis is a false sentence — never ex falso."""
    result = _prove(
        {
            "variables": {"x": "int"},
            "constraints": ["ForAll(x, And(x > 0, x < 0))"],
            "goal": "True",
        }
    )
    assert result.status is ResultStatus.UNDECIDED
    assert result.artifact_kind == "derivation"
    assert result.output["proven"] is False
    assert result.output["status_reason"] == "contradictory_hypotheses"
    assert result.output["certificate"] is None


# --- satisfy -------------------------------------------------------------------------------------


def test_satisfy_exists_open_interval() -> None:
    result = _satisfy(
        {
            "variables": {"x": "int"},
            "constraints": ["Exists(x, And(x > 1, x < 3))"],
        }
    )
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "model"
    model = result.output["model"]
    assert model is not None
    assert isinstance(model["x"], str)
    assert not any(isinstance(v, float) for v in result.output.values())


def test_satisfy_exists_contradiction_is_unsat() -> None:
    result = _satisfy(
        {
            "variables": {"x": "int"},
            "constraints": ["Exists(x, And(x > 0, x < 0))"],
        }
    )
    assert result.status is ResultStatus.REFUTED
    assert result.artifact_kind == "proof"
    assert result.output["unsatisfiable"] is True
    assert result.output["model"] is None
    assert result.output["certificate"] == "unsat"


def test_satisfy_forall_positive_is_unsat() -> None:
    result = _satisfy(
        {
            "variables": {"x": "int"},
            "constraints": ["ForAll(x, x > 0)"],
        }
    )
    assert result.status is ResultStatus.REFUTED
    assert result.output["unsatisfiable"] is True


def test_satisfy_forall_square_nonneg_is_sat() -> None:
    """∀x. x² ≥ 0 is a true closed sentence — sat, never undecided-as-failure."""
    result = _satisfy(
        {
            "variables": {"x": "int"},
            "constraints": ["ForAll(x, x * x >= 0)"],
        }
    )
    assert result.status is ResultStatus.RESULT
    assert result.output["satisfied"] is True


def test_satisfy_mixed_free_and_bound() -> None:
    result = _satisfy(
        {
            "variables": {"P": "bool", "x": "int"},
            "constraints": ["Implies(P, Exists(x, x > 0))"],
        }
    )
    assert result.status is ResultStatus.RESULT
    model = result.output["model"]
    assert model["P"] in {"true", "false"}


# --- undecided honesty ---------------------------------------------------------------------------


def test_quantified_nonlinear_unknown_is_honest_undecided() -> None:
    """A quantified nonlinear fragment may be unknown — never a fabricated proof or model."""
    from app.core.config import settings

    original = settings.toolbench_z3_timeout_ms
    try:
        settings.toolbench_z3_timeout_ms = 1
        result = _prove(
            {
                "variables": {"x": "int", "y": "int"},
                "constraints": [],
                "goal": "ForAll(x, Exists(y, x * x * x + y * y * y == 3))",
            }
        )
    finally:
        settings.toolbench_z3_timeout_ms = original

    assert result.status in {
        ResultStatus.UNDECIDED,
        ResultStatus.RESULT,
        ResultStatus.REFUTED,
    }
    if result.status is ResultStatus.UNDECIDED:
        assert result.output["proven"] is False
        assert result.output["status_reason"] in {
            "timeout",
            "incomplete",
            "hypotheses_undecided",
        }


# --- translator safety ---------------------------------------------------------------------------


def test_if_still_rejected() -> None:
    with pytest.raises(ValidationError, match="out of scope|If|unsupported"):
        Z3_PROVE.InputModel.model_validate(
            {"variables": {"P": "bool", "Q": "bool"}, "constraints": [], "goal": "If(P, Q, P)"}
        )


def test_list_binder_still_rejected() -> None:
    """Lists stay off the AST allow-list — binders are bare names, not ForAll([x], …)."""
    with pytest.raises(ValidationError, match="unsupported syntax|List"):
        Z3_PROVE.InputModel.model_validate(
            {
                "variables": {"x": "int"},
                "constraints": [],
                "goal": "ForAll([x], x + 0 == x)",
            }
        )


def test_non_name_binder_is_rejected() -> None:
    with pytest.raises((ValueError, ValidationError), match="binder|unsupported"):
        _prove(
            {
                "variables": {"x": "int"},
                "constraints": [],
                "goal": "ForAll(x + 1, x > 0)",
            }
        )


def test_forall_without_body_is_rejected() -> None:
    with pytest.raises((ValueError, ValidationError), match="binder|body|unsupported"):
        _prove({"variables": {"x": "int"}, "constraints": [], "goal": "ForAll(x)"})


def test_undeclared_binder_is_rejected() -> None:
    with pytest.raises(ValueError, match="undeclared"):
        _prove(
            {
                "variables": {"x": "int"},
                "constraints": [],
                "goal": "ForAll(z, z + 0 == z)",
            }
        )


def test_duplicate_binder_is_rejected() -> None:
    with pytest.raises((ValueError, ValidationError), match="duplicate"):
        _prove(
            {
                "variables": {"x": "int"},
                "constraints": [],
                "goal": "ForAll(x, x, x + 0 == x)",
            }
        )


def test_injection_still_rejected_inside_forall() -> None:
    with pytest.raises((ValueError, ValidationError)):
        _prove(
            {
                "variables": {"x": "int"},
                "constraints": [],
                "goal": "ForAll(x, x == __import__('os').getpid())",
            }
        )


def test_boolean_and_elim_still_works() -> None:
    """0.38.0 tautology must not regress when quantifiers join the allow-list."""
    result = _prove(
        {
            "variables": {"P": "bool", "Q": "bool"},
            "constraints": [],
            "goal": "Implies(And(P, Q), P)",
        }
    )
    assert result.status is ResultStatus.RESULT
    assert result.output["proven"] is True


def test_arithmetic_proof_still_works() -> None:
    result = _prove(
        {
            "variables": {"x": "real", "y": "real"},
            "constraints": ["x > 0", "y > 0"],
            "goal": "x + y > 0",
        }
    )
    assert result.status is ResultStatus.RESULT
    assert result.output["certificate"] == "unsat"


def test_latex_companions_on_forall_proof() -> None:
    result = _prove(_FORALL_IDENTITY_INPUTS)
    latex = result.output.get("goal_latex")
    assert latex
    assert r"\forall" in latex
    assert isinstance(latex, str)
    assert formula_to_latex("ForAll(x, x + 0 == x)") is not None


def test_forall_prove_runs_through_the_killable_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "toolbench_subprocess_sandbox_enabled", True)
    limits = limits_for(Z3_PROVE)
    assert limits.mode == "subprocess"

    proof = run_bounded_sync("z3.prove", _FORALL_IDENTITY_INPUTS, {}, limits)
    assert proof.status is ResultStatus.RESULT
    assert proof.output["proven"] is True

    with pytest.raises(ValueError, match="out of scope|If|unsupported"):
        run_bounded_sync(
            "z3.prove",
            {"variables": {"P": "bool", "Q": "bool"}, "constraints": [], "goal": "If(P, Q, P)"},
            {},
            limits,
        )
