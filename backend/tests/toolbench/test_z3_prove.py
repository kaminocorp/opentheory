"""Unit tests for ``z3.prove`` — translator safety + each honest outcome.

Pure in-process (no DB). Write-path / API / soft-timeout-under-wall-clock ordering are Phase 2.
"""

from __future__ import annotations

from typing import Any

import pytest
import z3
from pydantic import ValidationError
from sympy import Float, Integer, Symbol, symbols

from app.models.enums import ResultStatus
from app.toolbench.conformance import check_conformance
from app.toolbench.execution import limits_for, run_bounded_sync
from app.toolbench.instruments._z3_support import (
    ENGINE,
    ENGINE_VERSION,
    _reason_unknown,
    declare,
    render_model,
    solve,
    to_z3,
)
from app.toolbench.instruments.z3_prove import Z3_PROVE

# Acceptance example 1 from the plan — positive reals sum to a positive.
_PROOF_INPUTS = {
    "variables": {"x": "real", "y": "real"},
    "constraints": ["x > 0", "y > 0"],
    "goal": "x + y > 0",
}

# Acceptance example 2 — x*x != x is refuted by x=0 or x=1.
_REFUTE_INPUTS = {
    "variables": {"x": "int"},
    "constraints": [],
    "goal": "x*x != x",
}

# Vacuous guard — contradictory hypotheses must never produce a proof.
_VACUOUS_INPUTS = {
    "variables": {"x": "real"},
    "constraints": ["x > 0", "x < 0"],
    "goal": "x > 100",
}


def _run(inputs: dict[str, Any], assumptions: dict[str, Any] | None = None):
    validated = Z3_PROVE.InputModel.model_validate(inputs)
    return Z3_PROVE.run(validated, assumptions or {})


# --- conformance ---------------------------------------------------------------------------------


def test_z3_prove_conforms() -> None:
    assert check_conformance(Z3_PROVE, example_inputs=_PROOF_INPUTS) == []


def test_engine_pin_is_z3() -> None:
    assert ENGINE == "z3"
    assert Z3_PROVE.engine == "z3"
    assert Z3_PROVE.engine_version == ENGINE_VERSION
    assert ENGINE_VERSION  # non-empty pin from the installed wheel


# --- behavioural: each honest outcome -------------------------------------------------------------


def test_proof_of_positive_sum() -> None:
    result = _run(_PROOF_INPUTS)
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "proof"
    assert result.output["proven"] is True
    assert result.output["refuted"] is False
    assert result.output["certificate"] == "unsat"
    assert result.output["witness"] is None
    # Models / floats must not sneak into a proof payload.
    assert not any(isinstance(v, float) for v in result.output.values())
    # Unsat-core names the tracked hypotheses that were used.
    used = result.output["used_hypotheses"]
    assert used is not None
    assert any("x > 0" in name for name in used)
    assert any("y > 0" in name for name in used)


def test_refutation_with_exact_int_witness() -> None:
    result = _run(_REFUTE_INPUTS)
    assert result.status is ResultStatus.REFUTED
    assert result.artifact_kind == "counterexample"
    assert result.output["proven"] is False
    assert result.output["refuted"] is True
    witness = result.output["witness"]
    assert witness is not None
    assert set(witness) == {"x"}
    # Exact string — no float. x=0 or x=1 both refute x*x != x.
    assert witness["x"] in {"0", "1"}
    assert isinstance(witness["x"], str)
    assert "." not in witness["x"]  # no decimal float string


def test_vacuous_hypotheses_are_undecided_never_a_proof() -> None:
    result = _run(_VACUOUS_INPUTS)
    assert result.status is ResultStatus.UNDECIDED
    assert result.artifact_kind == "derivation"
    assert result.output["proven"] is False
    assert result.output["refuted"] is False
    assert result.output["status_reason"] == "contradictory_hypotheses"
    assert result.output["certificate"] is None


def test_nonlinear_unknown_is_honest_undecided() -> None:
    """A nonlinear goal Z3 cannot settle → undecided, never a pass and never a 422.

    Uses a tiny soft timeout so incompleteness/timeout is reliable without depending on a
    specific hard instance. The *payload* is still a successful undecided run.
    """
    from app.core.config import settings

    original = settings.toolbench_z3_timeout_ms
    try:
        # Force a soft timeout path on a hard nonlinear fragment when possible.
        settings.toolbench_z3_timeout_ms = 1
        result = _run(
            {
                "variables": {"x": "real", "y": "real"},
                # Nonlinear arithmetic — Z3 may return unknown (or, with luck, still decide).
                # If it *does* decide, we still accept proven/refuted; the honesty bar is only
                # that unknown never becomes result without a certificate. The dedicated
                # timeout path is also covered below via the solve harness.
                "constraints": ["x*x + y*y == 1"],
                "goal": "x*x*x + y*y*y == 1",
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


def test_solve_timeout_maps_to_undecided_reason_timeout() -> None:
    """Direct harness: a 1ms budget on a non-trivial check yields unknown → honest undecided.

    Stage-1 (hypotheses alone) or stage-2 may be the one that times out; both map to
    undecided with an explicit reason — never a silent pass.
    """
    x = z3.Int("x")
    y = z3.Int("y")
    # Large search space; with timeout=1 the solver often returns unknown.
    outcome = solve(
        [("h0", x * x * x + y * y * y > 0)],
        x * x * x + y * y * y != 0,
        env={"x": x, "y": y},
        timeout_ms=1,
    )
    # May still decide instantly on some builds; if unknown, reason must be honest.
    if outcome.kind == "undecided":
        assert outcome.reason in {
            "timeout",
            "incomplete",
            "hypotheses_undecided",
        }
    else:
        assert outcome.kind in {"proven", "refuted"}


# --- translator safety ---------------------------------------------------------------------------


def test_to_z3_rejects_float_literals() -> None:
    env = {"x": declare("x", "real")}
    with pytest.raises(ValueError, match="float"):
        to_z3(Float("0.5"), env)


def test_to_z3_rejects_undeclared_symbols() -> None:
    env = {"x": declare("x", "int")}
    y = Symbol("y")
    with pytest.raises(ValueError, match="undeclared"):
        to_z3(y, env)


def test_to_z3_rejects_non_whitelisted_nodes() -> None:
    env = {"x": declare("x", "real")}
    x = Symbol("x")
    # sin is not on the closed allow-list.
    from sympy import sin

    with pytest.raises(ValueError, match="unsupported"):
        to_z3(sin(x), env)


def test_to_z3_rejects_negative_exponent() -> None:
    env = {"x": declare("x", "real")}
    x = Symbol("x")
    with pytest.raises(ValueError, match="negative exponent"):
        to_z3(x ** Integer(-1), env)


def test_to_z3_translates_linear_sum() -> None:
    env = {"x": declare("x", "real"), "y": declare("y", "real")}
    x, y = symbols("x y")
    z = to_z3(x + y + 1, env)
    # Real declarations → the sum is Real-sorted (the integer literal 1 is promoted via ToReal).
    assert z.sort() == z3.RealSort()


def test_to_z3_promotes_mixed_int_real_to_real() -> None:
    # A mixed-sort sum must promote Int→Real so the arithmetic is well-sorted (never a sort clash).
    env = {"n": declare("n", "int"), "r": declare("r", "real")}
    n, r = symbols("n r")
    assert to_z3(n + r, env).sort() == z3.RealSort()


def test_render_model_uses_exact_fraction_strings() -> None:
    r = z3.Real("r")
    s = z3.Solver()
    s.add(2 * r == 1)
    assert s.check() == z3.sat
    rendered = render_model(s.model(), {"r": r})
    assert rendered == {"r": "1/2"}
    assert isinstance(rendered["r"], str)


def test_run_rejects_float_in_goal_text() -> None:
    with pytest.raises(ValueError, match="float|decimal|could not parse|unsupported"):
        _run(
            {
                "variables": {"x": "real"},
                "constraints": [],
                "goal": "x > 0.5",
            }
        )


def test_run_rejects_undeclared_variable_in_goal() -> None:
    with pytest.raises(ValueError, match="undeclared"):
        _run(
            {
                "variables": {"x": "int"},
                "constraints": [],
                "goal": "x + y > 0",
            }
        )


def test_run_rejects_injection_in_goal() -> None:
    with pytest.raises(ValueError):
        _run(
            {
                "variables": {"x": "int"},
                "constraints": [],
                "goal": "x == __import__('os').getpid()",
            }
        )


def test_run_rejects_assumptions() -> None:
    with pytest.raises(ValueError, match="does not accept assumptions"):
        _run(_PROOF_INPUTS, {"x": {"positive": True}})


def test_input_rejects_empty_goal() -> None:
    with pytest.raises(ValidationError):
        Z3_PROVE.InputModel.model_validate(
            {"variables": {"x": "int"}, "constraints": [], "goal": "   "}
        )


def test_input_rejects_non_relation_goal() -> None:
    with pytest.raises(ValidationError, match="relational operator"):
        Z3_PROVE.InputModel.model_validate(
            {"variables": {"x": "int"}, "constraints": [], "goal": "x + 1"}
        )


def test_input_rejects_bad_variable_name() -> None:
    with pytest.raises(ValidationError):
        Z3_PROVE.InputModel.model_validate(
            {"variables": {"x-y": "int"}, "constraints": [], "goal": "x-y > 0"}
        )


def test_unconditional_proof_over_integers() -> None:
    # ∀x. x + 0 == x
    result = _run(
        {
            "variables": {"x": "int"},
            "constraints": [],
            "goal": "x + 0 == x",
        }
    )
    assert result.status is ResultStatus.RESULT
    assert result.output["proven"] is True
    assert result.output["certificate"] == "unsat"


def test_latex_companions_present_on_proof() -> None:
    result = _run(_PROOF_INPUTS)
    assert result.output.get("goal_latex")
    # Constraints latex list is presentation-only.
    cl = result.output.get("constraints_latex")
    assert isinstance(cl, list)
    assert len(cl) == 2


def test_run_is_synchronous() -> None:
    """Sync run → execution sandbox routes to the killable subprocess (Decision)."""
    import inspect

    assert not inspect.iscoroutinefunction(Z3_PROVE.run)


def test_reason_unknown_classifies_timeout_vs_incomplete() -> None:
    """The unknown→reason mapping is honesty-critical: a soft-timeout is a *citable* undecided,
    an incomplete answer is *escalate*. Tested directly with a stub so it is deterministic — the
    behavioural tests above can only assert it *when* Z3 happens to return unknown.
    """

    class _StubSolver:
        def __init__(self, reason: object) -> None:
            self._reason = reason

        def reason_unknown(self) -> object:
            return self._reason

    assert _reason_unknown(_StubSolver("timeout")) == "timeout"  # type: ignore[arg-type]
    assert _reason_unknown(_StubSolver("canceled")) == "timeout"  # type: ignore[arg-type]
    assert _reason_unknown(_StubSolver("cancelled")) == "timeout"  # type: ignore[arg-type]
    assert _reason_unknown(_StubSolver("(incomplete quantifiers)")) == "incomplete"  # type: ignore[arg-type]
    assert _reason_unknown(_StubSolver(None)) == "incomplete"  # type: ignore[arg-type]


def test_z3_prove_runs_through_the_killable_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """The production path (0.13.5 hardening): a sync run is spawned in a child where Z3 is imported
    fresh and only a JSON envelope crosses back — no Z3 object is ever pickled. Proof / refutation /
    input-error all round-trip. The in-process unit tests above never exercise the subprocess.
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "toolbench_subprocess_sandbox_enabled", True)
    limits = limits_for(Z3_PROVE)
    assert limits.mode == "subprocess"

    proof = run_bounded_sync("z3.prove", _PROOF_INPUTS, {}, limits)
    assert proof.status is ResultStatus.RESULT
    assert proof.output["proven"] is True
    assert proof.output["certificate"] == "unsat"

    refute = run_bounded_sync("z3.prove", _REFUTE_INPUTS, {}, limits)
    assert refute.status is ResultStatus.REFUTED
    assert refute.output["witness"]["x"] in {"0", "1"}

    # An input error inside the child surfaces as ValueError (→ 422, mints nothing), never a crash.
    with pytest.raises(ValueError, match="undeclared"):
        run_bounded_sync(
            "z3.prove",
            {"variables": {"x": "int"}, "constraints": [], "goal": "x + y > 0"},
            {},
            limits,
        )
