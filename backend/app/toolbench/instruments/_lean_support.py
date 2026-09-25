"""Lean 4 plumbing for ``lean.prove`` — optional toolchain, fail-closed honesty.

v1 is prelude / ``Init`` only. There is no Mathlib import graph, no ``lake``
project, and no trusted axiom besides what the Lean kernel already ships. A
supporting result is Grade A **only** when:

1. the ``lean`` binary actually typechecks the snippet (exit 0), and
2. the source contains no cheat constructs (``sorry`` / ``axiom`` / IO / …), and
3. the source declares at least one ``theorem`` / ``lemma`` / ``example``.

Missing toolchain, soft timeout, and a rejected snippet are honest
``undecided`` / ``failed`` — never a proof. A crash (signal death) is *not* an
outcome: the caller must raise so the write path mints nothing.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Literal

ENGINE = "lean4"
ENGINE_VERSION_UNAVAILABLE = "optional"

# Soft-timeout default lives in Settings; this module only classifies a finished run.
_DIAGNOSTICS_CAP = 2000

# Identifier cheats + kernel-bypass + IO. Fail closed: comments/strings that mention
# these words also reject (understating rigor is recoverable).
_BANNED_IDENTIFIERS = (
    "sorry",
    "admit",
    "axiom",
    "opaque",
    "unsafe",
    "extern",
    "implemented_by",
    "native_decide",
    "partial",
)
_BANNED_COMMANDS = (
    r"#eval!?",
    r"#run\b",
    r"#check_failure\b",
    r"\bimport\b",
    r"\bIO\.",
    r"\bSystem\.FilePath\b",
    r"\bLean\.Elab\.Command\.run\b",
)

_BANNED_IDENT_RE = re.compile(
    r"\b(" + "|".join(re.escape(name) for name in _BANNED_IDENTIFIERS) + r")\b"
)
_BANNED_COMMAND_RES = tuple(re.compile(pat) for pat in _BANNED_COMMANDS)
_THEOREM_RE = re.compile(r"(?m)^\s*(theorem|lemma|example)\b")
_VERSION_RE = re.compile(r"(\d+\.\d+(?:\.\d+)?)")


LeanKind = Literal["proved", "failed", "timeout", "unavailable", "crash"]


@dataclass(frozen=True, slots=True)
class LeanCheck:
    """Classification of one snippet. ``kind="crash"`` must not be recorded as a result."""

    kind: LeanKind
    reason: str | None = None
    banned_constructs: tuple[str, ...] = ()
    diagnostics: str = ""
    lean_version: str | None = None
    exit_code: int | None = None
    extra: dict[str, str] = field(default_factory=dict)


def lean_binary() -> str | None:
    """PATH lookup for ``lean``. ``lake`` is not required in v1 and is not a substitute."""
    return shutil.which("lean")


def lake_binary() -> str | None:
    return shutil.which("lake")


def toolchain_available() -> bool:
    return lean_binary() is not None


def detect_lean_version(binary: str | None = None) -> str | None:
    """Best-effort ``lean --version`` pin. ``None`` when the binary is missing or hangs."""
    path = binary if binary is not None else lean_binary()
    if not path:
        return None
    try:
        completed = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (completed.stdout or completed.stderr or "").strip()
    if not text:
        return None
    match = _VERSION_RE.search(text)
    return match.group(1) if match else text.splitlines()[0][:80]


def engine_version() -> str:
    """Catalog pin: the installed Lean version, or ``optional`` when the binary is absent."""
    return detect_lean_version() or ENGINE_VERSION_UNAVAILABLE


def scan_banned(source: str) -> tuple[str, ...]:
    """Cheat / IO constructs present in ``source`` (stable, de-duplicated)."""
    found: list[str] = []
    for match in _BANNED_IDENT_RE.finditer(source):
        token = match.group(1)
        if token not in found:
            found.append(token)
    for pattern in _BANNED_COMMAND_RES:
        hit = pattern.search(source)
        if hit:
            token = hit.group(0).strip()
            if token not in found:
                found.append(token)
    return tuple(found)


def has_theorem(source: str) -> bool:
    """True when the snippet declares something that can be a proof."""
    return _THEOREM_RE.search(source) is not None


def _clip(text: str) -> str:
    stripped = text.strip()
    if len(stripped) <= _DIAGNOSTICS_CAP:
        return stripped
    return stripped[:_DIAGNOSTICS_CAP] + "…"


def check_source(
    source: str,
    *,
    timeout_s: float,
    lean_bin: str | None = None,
) -> LeanCheck:
    """Classify ``source``. Never raises on a missing toolchain or a type-error.

    ``kind="crash"`` is the only non-recordable outcome — the instrument must raise
    so the chokepoint mints nothing.
    """
    banned = scan_banned(source)
    if banned:
        return LeanCheck(
            kind="failed",
            reason="rejected_constructs",
            banned_constructs=banned,
            diagnostics="source contains constructs that cannot earn a proof "
            f"({', '.join(banned)})",
        )
    if not has_theorem(source):
        return LeanCheck(
            kind="failed",
            reason="no_theorem",
            diagnostics="source must declare a theorem, lemma, or example — "
            "a typechecking empty file is not a proof",
        )

    binary = lean_bin if lean_bin is not None else lean_binary()
    if not binary:
        return LeanCheck(
            kind="unavailable",
            reason="unavailable",
            diagnostics="lean binary not on PATH — optional toolchain; "
            "other instruments are unaffected",
        )

    version = detect_lean_version(binary)
    return _run_lean(source, binary=binary, timeout_s=timeout_s, version=version)


def _run_lean(
    source: str,
    *,
    binary: str,
    timeout_s: float,
    version: str | None,
) -> LeanCheck:
    """Spawn ``lean`` on a temp file; kill the process group on soft timeout."""
    budget = max(0.2, timeout_s)
    with tempfile.TemporaryDirectory(prefix="ot-lean-") as tmp:
        path = os.path.join(tmp, "Snippet.lean")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(source)
            if not source.endswith("\n"):
                handle.write("\n")
        try:
            # New session so a hang can be SIGKILL'd as a group (grandchild-safe).
            proc = subprocess.Popen(
                [binary, path],
                cwd=tmp,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
        except OSError as exc:
            return LeanCheck(
                kind="unavailable",
                reason="unavailable",
                diagnostics=f"lean could not be executed: {exc}",
                lean_version=version,
            )
        try:
            stdout, stderr = proc.communicate(timeout=budget)
        except subprocess.TimeoutExpired:
            _kill_group(proc)
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            return LeanCheck(
                kind="timeout",
                reason="timeout",
                diagnostics=f"lean exceeded the {budget:.1f}s soft timeout",
                lean_version=version,
            )

        combined = _clip("\n".join(part for part in (stdout, stderr) if part))
        code = proc.returncode
        if code is None:
            return LeanCheck(
                kind="crash",
                reason="crash",
                diagnostics=combined or "lean exited without a status",
                lean_version=version,
            )
        if code < 0:
            return LeanCheck(
                kind="crash",
                reason="crash",
                diagnostics=combined or f"lean killed by signal {-code}",
                lean_version=version,
                exit_code=code,
            )
        if code != 0:
            return LeanCheck(
                kind="failed",
                reason="failed",
                diagnostics=combined or f"lean exited {code}",
                lean_version=version,
                exit_code=code,
            )
        return LeanCheck(
            kind="proved",
            reason=None,
            diagnostics=combined,
            lean_version=version,
            exit_code=0,
        )


def _kill_group(proc: subprocess.Popen[str]) -> None:
    """SIGKILL the child's process group; ignore races where it already exited."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except PermissionError:
        proc.kill()
