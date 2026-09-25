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
    is_allowed_mathlib_import,
    mathlib_project_ready,
    mathlib_toolchain_available,
    read_mathlib_rev,
    scan_banned,
    toolchain_available,
)
from app.toolbench.instruments.lean_prove import LEAN_PROVE, _result_from_check

_PROOF_SOURCE = "example : 1 + 1 = 2 := rfl"
_FAIL_SOURCE = "example : 1 + 1 = 3 := rfl"
_SORRY_SOURCE = "example : 1 + 1 = 2 := sorry"
_MATHLIB_SMOKE = (
    "import Mathlib.Data.Real.Basic\n"
    "import Mathlib.Tactic.NormNum\n"
    "example : (2 : ℝ) + 2 = 4 := by norm_num"
)
_MATHLIB_SORRY = "import Mathlib\nexample : True := sorry"
_MATHLIB_BANNED_IMPORT = "import Lean\nexample : True := trivial"

_LEAN_PRESENT = toolchain_available()
requires_lean = pytest.mark.skipif(
    not _LEAN_PRESENT,
    reason="lean binary not on PATH — optional toolchain; CI does not install it",
)
requires_mathlib = pytest.mark.skipif(
    not mathlib_toolchain_available(),
    reason="lake + Mathlib cache not present — optional toolchain; CI does not install it",
)


def _run(
    source: str,
    assumptions: dict[str, Any] | None = None,
    *,
    mathlib: bool = False,
):
    validated = LEAN_PROVE.InputModel.model_validate(
        {"source": source, "mathlib": mathlib}
    )
    return LEAN_PROVE.run(validated, assumptions or {})


def _write_executable(path: Path, body: str) -> str:
    path.write_text(body)
    path.chmod(0o755)
    return str(path)


# --- conformance + engine pin -------------------------------------------------------------------


def test_lean_prove_conforms_without_lean() -> None:
    """Missing toolchain is still a conforming instrument — example_inputs must not raise."""
    assert check_conformance(LEAN_PROVE, example_inputs={"source": _PROOF_SOURCE}) == []
    assert check_conformance(
        LEAN_PROVE, example_inputs={"source": _MATHLIB_SMOKE, "mathlib": True}
    ) == []


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
        lambda source, timeout_s, **_kwargs: LeanCheck(
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
        lambda source, timeout_s, **_kwargs: check,
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
        lambda source, timeout_s, **_kwargs: LeanCheck(
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


# --- Mathlib opt-in (0.26.0) --------------------------------------------------------------------


def _fake_mathlib_project(root: Path, *, rev: str = "deadbeef") -> Path:
    """A directory that looks like a cached Mathlib lake project (no real oleans)."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "lakefile.toml").write_text('name = "ot"\nrev = "v4.14.0"\n')
    (root / "lean-toolchain").write_text("leanprover/lean4:v4.14.0\n")
    (root / "lake-manifest.json").write_text(
        f'{{"version": "1.1.0", "packages": [{{"name": "mathlib", "rev": "{rev}"}}]}}'
    )
    pkg = root / ".lake" / "packages" / "mathlib"
    pkg.mkdir(parents=True)
    (pkg / "lakefile.lean").write_text("-- stub cache marker\n")
    return root


def _offline_lake_script(exit_code: int = 0, body: str | None = None) -> str:
    if body is not None:
        return body
    return (
        "#!/bin/sh\n"
        "off=\n"
        'for a in "$@"; do [ "$a" = "--offline" ] && off=1; done\n'
        '[ -n "$off" ] || { echo "refusing networked lake" >&2; exit 2; }\n'
        f"exit {exit_code}\n"
    )


def test_mathlib_import_without_opt_in_is_rejected() -> None:
    assert "import" in scan_banned(_MATHLIB_SMOKE)
    result = _run(_MATHLIB_SMOKE, mathlib=False)
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["outcome"] == "failed"
    assert result.output["proven"] is False
    assert result.output["status_reason"] == "rejected_constructs"
    assert result.output["mathlib"] is False


def test_mathlib_allow_list_accepts_mathlib_and_init() -> None:
    assert is_allowed_mathlib_import("Mathlib")
    assert is_allowed_mathlib_import("Mathlib.Data.Real.Basic")
    assert is_allowed_mathlib_import("Init.Data.Nat")
    assert not is_allowed_mathlib_import("Lean")
    assert not is_allowed_mathlib_import("Lake")
    assert not is_allowed_mathlib_import("MathlibX")
    assert scan_banned(_MATHLIB_SMOKE, mathlib=True) == ()
    assert scan_banned(_MATHLIB_BANNED_IMPORT, mathlib=True) == ("Lean",)


def test_mathlib_sorry_is_failed_even_when_opted_in() -> None:
    result = _run(_MATHLIB_SORRY, mathlib=True)
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["outcome"] == "failed"
    assert result.output["proven"] is False
    assert result.output["status_reason"] == "rejected_constructs"
    assert "sorry" in result.output["banned_constructs"]


@pytest.mark.parametrize(
    "source",
    [
        "import Mathlib\naxiom T : True\nexample : True := trivial",
        "import Mathlib\nexample : True := admit",
        "import Mathlib\n#eval 1\nexample : True := trivial",
        "import Mathlib\nexample : True := (IO.println \"x\" *> pure trivial)",
        "import Mathlib\ninitialize foo : Unit := pure ()\nexample : True := trivial",
        _MATHLIB_BANNED_IMPORT,
    ],
)
def test_mathlib_mode_still_rejects_banned_constructs(source: str) -> None:
    result = _run(source, mathlib=True)
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["outcome"] == "failed"
    assert result.output["proven"] is False
    assert result.output["status_reason"] == "rejected_constructs"


def test_mathlib_missing_toolchain_is_undecided() -> None:
    """Opt-in without lake/Mathlib cache is unavailable — never a proof."""
    result = _run(_MATHLIB_SMOKE, mathlib=True)
    if mathlib_toolchain_available():
        pytest.skip("real Mathlib present — covered by test_real_mathlib_proves_smoke")
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["outcome"] == "undecided"
    assert result.output["proven"] is False
    assert result.output["status_reason"] == "mathlib_unavailable"
    assert result.artifact_kind == "derivation"


def test_mathlib_skeleton_without_cache_is_not_ready(tmp_path: Path) -> None:
    """The committed lake scaffold is not a proof environment."""
    skeleton = tmp_path / "skeleton"
    skeleton.mkdir()
    (skeleton / "lakefile.toml").write_text('name = "ot"\n')
    assert mathlib_project_ready(str(skeleton)) is False


def test_mathlib_proved_via_fake_lake(tmp_path: Path) -> None:
    root = _fake_mathlib_project(tmp_path / "mathlib-lake")
    lake = _write_executable(tmp_path / "lake", _offline_lake_script(0))
    check = check_source(
        _MATHLIB_SMOKE,
        timeout_s=2,
        lake_bin=lake,
        mathlib=True,
        mathlib_root=str(root),
    )
    assert check.kind == "proved"
    assert check.lake_used is True
    assert check.mathlib is True
    assert check.mathlib_rev == "deadbeef"
    result = _result_from_check(_MATHLIB_SMOKE, check, mathlib=True)
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "proof"
    assert result.output["outcome"] == "proved"
    assert result.output["proven"] is True
    assert result.output["certificate"] == "lean-kernel+mathlib"
    assert result.output["mathlib"] is True
    assert result.output["lake_used"] is True
    assert result.output["mathlib_rev"] == "deadbeef"


def test_mathlib_failed_via_fake_lake(tmp_path: Path) -> None:
    root = _fake_mathlib_project(tmp_path / "mathlib-lake")
    lake = _write_executable(
        tmp_path / "lake",
        _offline_lake_script(
            body=(
                "#!/bin/sh\n"
                "echo 'error: type mismatch' >&2\n"
                "exit 1\n"
            )
        ),
    )
    check = check_source(
        _MATHLIB_SMOKE,
        timeout_s=2,
        lake_bin=lake,
        mathlib=True,
        mathlib_root=str(root),
    )
    assert check.kind == "failed"
    result = _result_from_check(_MATHLIB_SMOKE, check, mathlib=True)
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["outcome"] == "failed"
    assert result.output["proven"] is False


def test_mathlib_timeout_via_fake_lake_is_undecided(tmp_path: Path) -> None:
    root = _fake_mathlib_project(tmp_path / "mathlib-lake")
    lake = _write_executable(tmp_path / "lake", "#!/bin/sh\nsleep 30\n")
    check = check_source(
        _MATHLIB_SMOKE,
        timeout_s=0.25,
        lake_bin=lake,
        mathlib=True,
        mathlib_root=str(root),
    )
    assert check.kind == "timeout"
    result = _result_from_check(_MATHLIB_SMOKE, check, mathlib=True)
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["outcome"] == "undecided"
    assert result.output["status_reason"] == "timeout"
    assert result.output["proven"] is False


def test_mathlib_lake_is_invoked_offline(tmp_path: Path) -> None:
    """Grade A Mathlib checks must not fetch packages."""
    root = _fake_mathlib_project(tmp_path / "mathlib-lake")
    seen = tmp_path / "args.txt"
    lake = _write_executable(
        tmp_path / "lake",
        "#!/bin/sh\n"
        f'printf "%s\\n" "$*" > "{seen}"\n'
        "exit 0\n",
    )
    check = check_source(
        _MATHLIB_SMOKE,
        timeout_s=2,
        lake_bin=lake,
        mathlib=True,
        mathlib_root=str(root),
    )
    assert check.kind == "proved"
    assert "--offline" in seen.read_text()


def test_read_mathlib_rev_from_manifest(tmp_path: Path) -> None:
    root = _fake_mathlib_project(tmp_path / "mathlib-lake", rev="abc123def")
    assert read_mathlib_rev(str(root)) == "abc123def"


@requires_mathlib
def test_real_mathlib_proves_smoke() -> None:
    result = _run(_MATHLIB_SMOKE, mathlib=True)
    assert result.status is ResultStatus.RESULT
    assert result.artifact_kind == "proof"
    assert result.output["proven"] is True
    assert result.output["outcome"] == "proved"
    assert result.output["certificate"] == "lean-kernel+mathlib"
    assert result.output["mathlib"] is True
    assert result.output["lake_used"] is True


@requires_mathlib
def test_real_mathlib_rejects_false_equality() -> None:
    source = (
        "import Mathlib.Data.Real.Basic\n"
        "import Mathlib.Tactic.NormNum\n"
        "example : (2 : ℝ) + 2 = 5 := by norm_num"
    )
    result = _run(source, mathlib=True)
    assert result.status is ResultStatus.UNDECIDED
    assert result.output["outcome"] == "failed"
    assert result.output["proven"] is False

