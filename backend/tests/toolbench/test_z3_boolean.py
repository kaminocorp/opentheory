"""0.38.0 — boolean connectives + ``bool`` sort on ``z3.prove`` / ``z3.satisfy``.

Cases that ``split_relation`` could not express (``Implies(And(P, Q), P)``, mixed
arithmetic + propositional structure). Honesty contract is unchanged: Grade A /
``proven`` only on a real Z3 validity success; vacuous hypotheses stay undecided;
parse / If / injection failures raise (mint nothing). ForAll / Exists land in 0.39.0.
"""

from __future__ import annotations

from typing import Any

import pytest
import z3
from pydantic import ValidationError

from app.models.enums import ResultStatus
from app.toolbench.execution import limits_for, run_bounded_sync
from app.toolbench.instruments._z3_support import (
    RESERVED_NAMES,
    declare,
    formula_to_latex,
    formula_to_z3,
    render_model,
)
from app.toolbench.instruments.z3_prove import Z3_PROVE
from app.toolbench.instruments.z3_satisfy import Z3_SATISFY

# The motivating tautology: (P ∧ Q) → P. Impossible before 0.38.0.
_AND_ELIM_INPUTS = {
    "variables": {"P": "bool", "Q": "bool"},
    "constraints": [],
    "goal": "Implies(And(P, Q), P)",
}


def _prove(inputs: dict[str, Any], assumptions: dict[str, Any] | None = None):
    return Z3_PROVE.run(Z3_PROVE.InputModel.model_validate(inputs), assumptions or {})


def _satisfy(inputs: dict[str, Any], assumptions: dict[str, Any] | None = None):
    return Z3_SATISFY.run(Z3_SATISFY.InputModel.model_validate(inputs), assumptions or {})


# --- prove: tautologies that need connectives ----------------------------------------------------


def test_prove_and_elimination() -> None:
    result = _prove(_AND_ELIM_INPUTS)
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "proof"
    assert result.output["proven"] is True
    assert result.output["refuted"] is False
    assert result.output["certificate"] == "unsat"
    assert result.output["witness"] is None
    assert not any(isinstance(v, float) for v in result.output.values())


def test_prove_and_elimination_python_operators() -> None:
    """``and`` / implicit implication via Implies still closed-allow-list — no eval."""
    result = _prove(
        {
            "variables": {"P": "bool", "Q": "bool"},
            "constraints": [],
            "goal": "Implies(P and Q, P)",
        }
    )
    assert result.status is ResultStatus.RESULT
    assert result.output["proven"] is True


def test_prove_modus_ponens_under_hypotheses() -> None:
    result = _prove(
        {
            "variables": {"P": "bool", "Q": "bool"},
            "constraints": ["P", "Implies(P, Q)"],
            "goal": "Q",
        }
    )
    assert result.status is ResultStatus.RESULT
    assert result.output["proven"] is True
    used = result.output["used_hypotheses"]
    assert used is not None
    assert any("P" in name for name in used)


def test_prove_excluded_middle() -> None:
    result = _prove(
        {
            "variables": {"P": "bool"},
            "constraints": [],
            "goal": "Or(P, Not(P))",
        }
    )
    assert result.status is ResultStatus.RESULT
    assert result.output["proven"] is True


def test_prove_xor_and_equivalent() -> None:
    xor = _prove(
        {
            "variables": {"P": "bool"},
            "constraints": [],
            "goal": "Xor(P, Not(P))",
        }
    )
    assert xor.status is ResultStatus.RESULT
    iff = _prove(
        {
            "variables": {"P": "bool", "Q": "bool"},
            "constraints": ["Equivalent(P, Q)"],
            "goal": "Iff(P, Q)",
        }
    )
    assert iff.status is ResultStatus.RESULT
    assert iff.output["proven"] is True


def test_prove_true_is_unconditional() -> None:
    result = _prove({"variables": {"P": "bool"}, "constraints": [], "goal": "True"})
    assert result.status is ResultStatus.RESULT
    assert result.output["proven"] is True


def test_prove_mixed_arithmetic_and_bool() -> None:
    """And(x > 0, y > 0) → x + y > 0 — one formula, was previously two hypothesis rows."""
    result = _prove(
        {
            "variables": {"x": "real", "y": "real"},
            "constraints": [],
            "goal": "Implies(And(x > 0, y > 0), x + y > 0)",
        }
    )
    assert result.status is ResultStatus.RESULT
    assert result.output["proven"] is True


def test_prove_chained_comparison() -> None:
    result = _prove(
        {
            "variables": {"x": "real"},
            "constraints": ["0 < x", "x < 1"],
            "goal": "0 < x < 1",
        }
    )
    assert result.status is ResultStatus.RESULT
    assert result.output["proven"] is True


# --- prove: refutation / vacuous / honesty -------------------------------------------------------


def test_prove_false_goal_is_refuted() -> None:
    result = _prove({"variables": {"P": "bool"}, "constraints": [], "goal": "False"})
    assert result.status is ResultStatus.REFUTED
    assert result.artifact_kind == "counterexample"
    assert result.output["refuted"] is True
    witness = result.output["witness"]
    assert witness is not None
    assert witness["P"] in {"true", "false"}
    assert isinstance(witness["P"], str)


def test_prove_bare_bool_var_is_refuted() -> None:
    """∀P. P is false — counter-model P=false. A bool sort that 0.33.0 could not declare."""
    result = _prove({"variables": {"P": "bool"}, "constraints": [], "goal": "P"})
    assert result.status is ResultStatus.REFUTED
    assert result.output["witness"]["P"] == "false"


def test_prove_implies_without_hyps_is_refuted() -> None:
    result = _prove(
        {
            "variables": {"P": "bool", "Q": "bool"},
            "constraints": [],
            "goal": "Implies(P, Q)",
        }
    )
    assert result.status is ResultStatus.REFUTED
    witness = result.output["witness"]
    assert witness["P"] == "true"
    assert witness["Q"] == "false"


def test_vacuous_and_not_is_undecided_never_a_proof() -> None:
    """And(P, Not(P)) as a hypothesis must not prove an arbitrary goal (ex falso)."""
    result = _prove(
        {
            "variables": {"P": "bool"},
            "constraints": ["And(P, Not(P))"],
            "goal": "False",
        }
    )
    assert result.status is ResultStatus.UNDECIDED
    assert result.artifact_kind == "derivation"
    assert result.output["proven"] is False
    assert result.output["status_reason"] == "contradictory_hypotheses"
    assert result.output["certificate"] is None


# --- satisfy -------------------------------------------------------------------------------------


def test_satisfy_and_of_bools() -> None:
    result = _satisfy(
        {"variables": {"P": "bool", "Q": "bool"}, "constraints": ["And(P, Q)"]}
    )
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "model"
    model = result.output["model"]
    assert model == {"P": "true", "Q": "true"}
    assert not any(isinstance(v, float) for v in result.output.values())


def test_satisfy_and_p_not_p_is_unsat() -> None:
    result = _satisfy(
        {"variables": {"P": "bool"}, "constraints": ["And(P, Not(P))"]}
    )
    assert result.status is ResultStatus.REFUTED
    assert result.artifact_kind == "proof"
    assert result.output["unsatisfiable"] is True
    assert result.output["model"] is None
    assert result.output["certificate"] == "unsat"


def test_satisfy_or_has_a_model() -> None:
    result = _satisfy({"variables": {"P": "bool", "Q": "bool"}, "constraints": ["Or(P, Q)"]})
    assert result.status is ResultStatus.RESULT
    model = result.output["model"]
    assert model["P"] == "true" or model["Q"] == "true"


def test_satisfy_mixed_bool_and_real() -> None:
    result = _satisfy(
        {
            "variables": {"P": "bool", "x": "real"},
            "constraints": ["And(P, x > 0)", "x < 1"],
        }
    )
    assert result.status is ResultStatus.RESULT
    model = result.output["model"]
    assert model["P"] == "true"
    assert isinstance(model["x"], str)
    assert "." not in model["x"]


def test_satisfy_python_not() -> None:
    result = _satisfy({"variables": {"P": "bool"}, "constraints": ["not P"]})
    assert result.status is ResultStatus.RESULT
    assert result.output["model"]["P"] == "false"


# --- translator safety: closed allow-list, no false-proof path ------------------------------------


def test_wrong_case_forall_and_quantifier_stay_rejected() -> None:
    """0.39.0 adds ForAll/Exists; Forall / Quantifier / list binders stay closed-out."""
    with pytest.raises(ValidationError, match="out of scope|Forall|unsupported"):
        Z3_PROVE.InputModel.model_validate(
            {"variables": {"P": "bool"}, "constraints": [], "goal": "Forall(P, P)"}
        )
    with pytest.raises(ValidationError, match="out of scope|Quantifier|unsupported"):
        Z3_SATISFY.InputModel.model_validate(
            {"variables": {"P": "bool"}, "constraints": ["Quantifier(P, P)"]}
        )


def test_if_is_rejected() -> None:
    with pytest.raises(ValidationError, match="out of scope|If|unsupported"):
        Z3_PROVE.InputModel.model_validate(
            {"variables": {"P": "bool", "Q": "bool"}, "constraints": [], "goal": "If(P, Q, P)"}
        )


def test_reserved_variable_names_are_rejected() -> None:
    for name in ("And", "Or", "Not", "Implies", "True", "ForAll"):
        assert name in RESERVED_NAMES
        with pytest.raises(ValidationError, match="reserved"):
            Z3_PROVE.InputModel.model_validate(
                {"variables": {name: "bool"}, "constraints": [], "goal": "True"}
            )


def test_int_variable_is_not_a_formula() -> None:
    """A bare int name is not a boolean — raise, do not silently coerce (false-proof risk)."""
    with pytest.raises(ValueError, match="boolean"):
        _prove({"variables": {"x": "int"}, "constraints": [], "goal": "x"})


def test_bool_cannot_be_ordered() -> None:
    with pytest.raises(ValueError, match="ordered|boolean"):
        _prove({"variables": {"P": "bool", "Q": "bool"}, "constraints": [], "goal": "P < Q"})


def test_injection_still_rejected() -> None:
    with pytest.raises((ValueError, ValidationError)):
        _prove(
            {
                "variables": {"P": "bool"},
                "constraints": [],
                "goal": "P == __import__('os').getpid()",
            }
        )


def test_attribute_walk_still_rejected() -> None:
    with pytest.raises((ValueError, ValidationError)):
        _prove(
            {
                "variables": {"P": "bool"},
                "constraints": [],
                "goal": "P == (1).__class__",
            }
        )


def test_float_literal_still_rejected_inside_and() -> None:
    with pytest.raises((ValueError, ValidationError), match="float|decimal"):
        _prove(
            {
                "variables": {"x": "real", "P": "bool"},
                "constraints": [],
                "goal": "And(P, x > 0.5)",
            }
        )


def test_sin_still_rejected() -> None:
    with pytest.raises((ValueError, ValidationError), match="unsupported function|unsupported"):
        _prove(
            {
                "variables": {"x": "real"},
                "constraints": [],
                "goal": "sin(x) > 0",
            }
        )


def test_formula_to_z3_rejects_undeclared() -> None:
    env = {"P": declare("P", "bool")}
    with pytest.raises(ValueError, match="undeclared"):
        formula_to_z3("Implies(P, Q)", env)


def test_render_bool_model_uses_true_false_strings() -> None:
    p = z3.Bool("P")
    s = z3.Solver()
    s.add(p)
    assert s.check() == z3.sat
    rendered = render_model(s.model(), {"P": p})
    assert rendered == {"P": "true"}


def test_latex_companions_on_boolean_proof() -> None:
    result = _prove(_AND_ELIM_INPUTS)
    latex = result.output.get("goal_latex")
    assert latex
    assert r"\rightarrow" in latex or r"\land" in latex
    # Presentation-only helper stays a string, never a float.
    assert isinstance(latex, str)
    assert formula_to_latex("Implies(And(P, Q), P)") is not None


def test_existing_arithmetic_proof_still_works() -> None:
    """0.13.x acceptance example must not regress when the formula parser is the front door."""
    result = _prove(
        {
            "variables": {"x": "real", "y": "real"},
            "constraints": ["x > 0", "y > 0"],
            "goal": "x + y > 0",
        }
    )
    assert result.status is ResultStatus.RESULT
    assert result.output["certificate"] == "unsat"


def test_boolean_prove_runs_through_the_killable_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "toolbench_subprocess_sandbox_enabled", True)
    limits = limits_for(Z3_PROVE)
    assert limits.mode == "subprocess"

    proof = run_bounded_sync("z3.prove", _AND_ELIM_INPUTS, {}, limits)
    assert proof.status is ResultStatus.RESULT
    assert proof.output["proven"] is True

    with pytest.raises(ValueError, match="out of scope|If|unsupported"):
        run_bounded_sync(
            "z3.prove",
            {"variables": {"P": "bool", "Q": "bool"}, "constraints": [], "goal": "If(P, Q, P)"},
            {},
            limits,
        )
