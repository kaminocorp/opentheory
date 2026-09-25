"""Unit tests for ``lean.prove`` — optional toolchain, honest outcomes, no fake proofs.

Pure in-process (no DB). Proved / failed-with-real-lean paths that need a ``lean``
binary are gated; CI stays green without installing Lean. Fake binaries cover
timeout, type-error failure, crash (raises), and a successful typecheck.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.models.enums import EvidenceGrade, ResultStatus
from app.toolbench.conformance import check_conformance
from app.toolbench.grading import grade_for
from app.toolbench.instruments._lean_support import (
    ENGINE,
    ENGINE_VERSION_UNAVAILABLE,
    LeanCheck,
    check_source,
    has_theorem,
    scan_banned,
    toolchain_available,
)
from app.toolbench.instruments.lean_prove import LEAN_PROVE, _result_from_check

_PROOF_SOURCE = "example : 1 + 1 = 2 := rfl"
_FAIL_SOURCE = "example : 1 + 1 = 3 := rfl"
_SORRY_SOURCE = "example : 1 + 1 = 2 := sorry"

_LEAN_PRESENT = toolchain_available()
requires_lean = pytest.mark.skipif(
    not _LEAN_PRESENT,
    reason="lean binary not on PATH — optional toolchain; CI does not install it",
)


def _run(source: str, assumptions: dict[str, Any] | None = None):
    validated = LEAN_PROVE.InputModel.model_validate({"source": source})
    return LEAN_PROVE.run(validated, assumptions or {})


def _write_executable(path: Path, body: str) -> str:
    path.write_text(body)
    path.chmod(0o755)
    return str(path)


# --- conformance + engine pin -------------------------------------------------------------------


def test_lean_prove_conforms_without_lean() -> None:
    """Missing toolchain is still a conforming instrument — example_inputs must not raise."""
    assert check_conformance(LEAN_PROVE, example_inputs={"source": _PROOF_SOURCE}) == []


def test_engine_pin_is_lean4() -> None:
    assert LEAN_PROVE.engine == ENGINE == "lean4"
    assert LEAN_PROVE.engine_version  # non-empty catalog pin (version or "optional")
    if not _LEAN_PRESENT:
        assert LEAN_PROVE.engine_version == ENGINE_VERSION_UNAVAILABLE


def test_grade_a_only_on_result() -> None:
    assert grade_for("lean.prove", ResultStatus.RESULT) is EvidenceGrade.A
    assert grade_for("lean.prove", ResultStatus.UNDECIDED) is None
    assert grade_for("lean.prove", ResultStatus.REFUTED) is None


# --- input validation ---------------------------------------------------------------------------


def test_empty_source_rejected() -> None:
    with pytest.raises(ValidationError):
        LEAN_PROVE.InputModel.model_validate({"source": "   "})


def test_source_line_cap() -> None:
    with pytest.raises(ValidationError, match="lines"):
        LEAN_PROVE.InputModel.model_validate({"source": "\n".join(["--"] * 201)})


def test_assumptions_rejected() -> None:
    with pytest.raises(ValueError, match="assumptions"):
        _run(_PROOF_SOURCE, assumptions={"foo": True})


# --- banned constructs / no theorem (no lean required) ------------------------------------------


def test_sorry_is_failed_never_a_proof() -> None:
    result = _run(_SORRY_SOURCE)
    assert result.status is ResultStatus.UNDECIDED
    assert result.artifact_kind == "derivation"
    assert result.output["outcome"] == "failed"
    assert result.output["proven"] is False
    assert result.output["status_reason"] == "rejected_constructs"
    assert "sorry" in result.output["banned_constructs"]


@pytest.mark.parametrize(
    "source",
    [
        "axiom T : True",
        "example : True := admit",
        "opaque n : Nat",
        "unsafe def f : Nat := 1\nexample : True := trivial",
        "example : True := by native_decide",
        "#eval 1 + 1\nexample : True := trivial",
        "import Mathlib\nexample : True := trivial",
        "example : True := (IO.println \"x\" *> pure trivial)",
    ],
)
def test_banned_constructs_never_prove(source: str) -> None:
    assert scan_banned(source)
    result = _run(source)
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["outcome"] == "failed"
    assert result.output["proven"] is False
    assert result.output["status_reason"] == "rejected_constructs"


def test_comment_only_file_is_not_a_proof() -> None:
    result = _run("-- just a comment")
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["outcome"] == "failed"
    assert result.output["status_reason"] == "no_theorem"
    assert has_theorem("-- just a comment") is False


def test_has_theorem_recognises_example() -> None:
    assert has_theorem(_PROOF_SOURCE) is True
    assert has_theorem("def n : Nat := 1") is False


# --- missing toolchain --------------------------------------------------------------------------


def test_missing_toolchain_is_undecided_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.toolbench.instruments.lean_prove.check_source",
        lambda source, timeout_s, lean_bin=None: LeanCheck(
            kind="unavailable",
            reason="unavailable",
            diagnostics="lean binary not on PATH",
        ),
    )
    result = _run(_PROOF_SOURCE)
    assert result.status is ResultStatus.UNDECIDED
    assert result.artifact_kind == "derivation"
    assert result.output["outcome"] == "undecided"
    assert result.output["proven"] is False
    assert result.output["status_reason"] == "unavailable"


def test_real_missing_or_present_toolchain_is_honest() -> None:
    """Whatever this host has: never mint a proof without a real typecheck."""
    result = _run(_PROOF_SOURCE)
    if not _LEAN_PRESENT:
        assert result.status is ResultStatus.UNDECIDED
        assert result.output["outcome"] == "undecided"
        assert result.output["status_reason"] == "unavailable"
        assert result.output["proven"] is False
    else:
        assert result.status is ResultStatus.RESULT
        assert result.output["outcome"] == "proved"
        assert result.output["proven"] is True
        assert result.artifact_kind == "proof"


# --- fake binaries: timeout / failed / proved / crash -------------------------------------------


def test_timeout_via_fake_binary_is_undecided(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _write_executable(tmp_path / "lean", "#!/bin/sh\nsleep 30\n")
    monkeypatch.setattr(
        "app.toolbench.instruments._lean_support.lean_binary", lambda: fake
    )
    check = check_source(_PROOF_SOURCE, timeout_s=0.25, lean_bin=fake)
    assert check.kind == "timeout"
    assert check.reason == "timeout"

    monkeypatch.setattr(
        "app.toolbench.instruments.lean_prove.check_source",
        lambda source, timeout_s, lean_bin=None: check,
    )
    result = _run(_PROOF_SOURCE)
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["outcome"] == "undecided"
    assert result.output["status_reason"] == "timeout"
    assert result.output["proven"] is False


def test_failed_typecheck_via_fake_binary(tmp_path: Path) -> None:
    fake = _write_executable(
        tmp_path / "lean",
        "#!/bin/sh\necho 'error: type mismatch' >&2\nexit 1\n",
    )
    check = check_source(_FAIL_SOURCE, timeout_s=2, lean_bin=fake)
    assert check.kind == "failed"
    assert check.reason == "failed"
    result = _result_from_check(_FAIL_SOURCE, check)
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["outcome"] == "failed"
    assert result.output["proven"] is False


def test_proved_via_fake_binary(tmp_path: Path) -> None:
    fake = _write_executable(tmp_path / "lean", "#!/bin/sh\nexit 0\n")
    # --version is the same binary; exit 0 with empty stdout is fine.
    check = check_source(_PROOF_SOURCE, timeout_s=2, lean_bin=fake)
    assert check.kind == "proved"
    result = _result_from_check(_PROOF_SOURCE, check)
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "proof"
    assert result.output["outcome"] == "proved"
    assert result.output["proven"] is True
    assert result.output["certificate"] == "lean-kernel"


def test_crash_via_fake_binary_is_not_a_result(tmp_path: Path) -> None:
    fake = _write_executable(tmp_path / "lean", "#!/bin/sh\nkill -s KILL $$\n")
    check = check_source(_PROOF_SOURCE, timeout_s=2, lean_bin=fake)
    assert check.kind == "crash"


def test_instrument_raises_on_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.toolbench.instruments.lean_prove.check_source",
        lambda source, timeout_s, lean_bin=None: LeanCheck(
            kind="crash",
            reason="crash",
            diagnostics="lean killed by signal 9",
        ),
    )
    with pytest.raises(RuntimeError, match="crashed|killed"):
        _run(_PROOF_SOURCE)


# --- real lean (skipped in CI) ------------------------------------------------------------------


@requires_lean
def test_real_lean_proves_rfl() -> None:
    result = _run(_PROOF_SOURCE)
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "proof"
    assert result.output["proven"] is True
    assert result.output["outcome"] == "proved"
    assert result.output["certificate"] == "lean-kernel"


@requires_lean
def test_real_lean_rejects_false_equality() -> None:
    result = _run(_FAIL_SOURCE)
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["outcome"] == "failed"
    assert result.output["proven"] is False
    assert result.output["status_reason"] == "failed"

