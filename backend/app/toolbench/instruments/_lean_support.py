"""Lean 4 plumbing for ``lean.prove`` — optional toolchain, fail-closed honesty.

Prelude / ``Init`` is the default. ``mathlib=True`` is an explicit opt-in that
allows a closed Mathlib import set and typechecks through a bounded ``lake``
project. There is no trusted axiom besides what the Lean kernel already ships.
A supporting result is Grade A **only** when:

1. the checker actually typechecks the snippet (exit 0), and
2. the source contains no cheat constructs (``sorry`` / ``axiom`` / IO / …), and
3. the source declares at least one ``theorem`` / ``lemma`` / ``example``, and
4. if Mathlib was requested, a pre-built ``lake`` + Mathlib cache is present
   and the snippet's imports stay inside the allow-list.

Missing toolchain, missing Mathlib, soft timeout, and a rejected snippet are
honest ``undecided`` / ``failed`` — never a proof. A crash (signal death) is
*not* an outcome: the caller must raise so the write path mints nothing.

``lake`` is never allowed to fetch packages at check time (``--offline``).
"""

from __future__ import annotations

import json
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
DEFAULT_MATHLIB_LAKE = "/opt/opentheory/lean-mathlib"

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
    r"\bIO\.",
    r"\bSystem\.FilePath\b",
    r"\bLean\.Elab\.Command\.run\b",
    r"(?m)^\s*(?:builtin_)?initialize\b",
)

_BANNED_IDENT_RE = re.compile(
    r"\b(" + "|".join(re.escape(name) for name in _BANNED_IDENTIFIERS) + r")\b"
)
_BANNED_COMMAND_RES = tuple(re.compile(pat) for pat in _BANNED_COMMANDS)
_IMPORT_OCCURRENCE_RE = re.compile(
    r"(?:(?<=^)|(?<=\s))(?:public\s+)?import\s+([A-Za-z][A-Za-z0-9_.]*)"
)
_THEOREM_RE = re.compile(r"(?m)^\s*(theorem|lemma|example)\b")
_VERSION_RE = re.compile(r"(\d+\.\d+(?:\.\d+)?)")
_LAKEFILE_NAMES = ("lakefile.toml", "lakefile.lean")
_MATHLIB_PACKAGE_DIRS = (
    (".lake", "packages", "mathlib"),
    (".lake", "packages", "Mathlib"),
    ("lake-packages", "mathlib"),
)

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
    mathlib: bool = False
    mathlib_rev: str | None = None
    lake_used: bool = False


def lean_binary() -> str | None:
    """PATH lookup for ``lean``. ``lake`` is not a substitute for prelude checks."""
    return shutil.which("lean")


def lake_binary() -> str | None:
    return shutil.which("lake")


def toolchain_available() -> bool:
    return lean_binary() is not None


def mathlib_project_root(explicit: str | None = None) -> str | None:
    """Configured or conventional path of the pre-built Mathlib ``lake`` project."""
    if explicit:
        return explicit
    env = os.environ.get("OPENTHEORY_MATHLIB_LAKE") or os.environ.get(
        "TOOLBENCH_MATHLIB_LAKE"
    )
    if env:
        return env
    if os.path.isdir(DEFAULT_MATHLIB_LAKE):
        return DEFAULT_MATHLIB_LAKE
    return None


def mathlib_project_ready(root: str | None = None) -> bool:
    """True when ``root`` looks like a cached Mathlib lake project (no network needed)."""
    path = root if root is not None else mathlib_project_root()
    if not path or not os.path.isdir(path):
        return False
    has_lakefile = any(os.path.isfile(os.path.join(path, name)) for name in _LAKEFILE_NAMES)
    if not has_lakefile:
        return False
    return any(os.path.isdir(os.path.join(path, *parts)) for parts in _MATHLIB_PACKAGE_DIRS)


def mathlib_toolchain_available(
    *, lake_bin: str | None = None, mathlib_root: str | None = None
) -> bool:
    """``lake`` on PATH and a pre-built Mathlib cache. Missing either is not a proof."""
    lake = lake_bin if lake_bin is not None else lake_binary()
    return lake is not None and mathlib_project_ready(mathlib_project_root(mathlib_root))


def read_mathlib_rev(root: str | None = None) -> str | None:
    """Best-effort pin from ``lake-manifest.json``. ``None`` when absent or unreadable."""
    path = root if root is not None else mathlib_project_root()
    if not path:
        return None
    manifest = os.path.join(path, "lake-manifest.json")
    if not os.path.isfile(manifest):
        return None
    try:
        with open(manifest, encoding="utf-8") as handle:
            data = json.loads(handle.read())
    except (OSError, json.JSONDecodeError):
        return None
    packages = data.get("packages") or []
    if not isinstance(packages, list):
        return None
    for pkg in packages:
        if not isinstance(pkg, dict):
            continue
        name = str(pkg.get("name") or "").lower()
        if name in {"mathlib", "mathlib4"}:
            rev = pkg.get("rev") or pkg.get("inputRev") or pkg.get("inheritedRev")
            if isinstance(rev, str) and rev:
                return rev[:80]
    return None


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


def is_allowed_mathlib_import(module: str) -> bool:
    """Closed allow-list: ``Mathlib`` / ``Mathlib.*`` and ``Init`` / ``Init.*`` only."""
    return (
        module == "Mathlib"
        or module.startswith("Mathlib.")
        or module == "Init"
        or module.startswith("Init.")
    )


def listed_imports(source: str) -> tuple[str, ...]:
    """Module names mentioned in ``import`` occurrences, de-duplicated, source order."""
    found: list[str] = []
    for match in _IMPORT_OCCURRENCE_RE.finditer(source):
        name = match.group(1)
        if name not in found:
            found.append(name)
    return tuple(found)


def scan_banned(source: str, *, mathlib: bool = False) -> tuple[str, ...]:
    """Cheat / IO / disallowed-import constructs present in ``source`` (stable, de-duplicated)."""
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
    imports = listed_imports(source)
    if mathlib:
        for module in imports:
            if not is_allowed_mathlib_import(module) and module not in found:
                found.append(module)
    elif imports:
        if "import" not in found:
            found.append("import")
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
    lake_bin: str | None = None,
    mathlib: bool = False,
    mathlib_root: str | None = None,
) -> LeanCheck:
    """Classify ``source``. Never raises on a missing toolchain or a type-error.

    ``kind="crash"`` is the only non-recordable outcome — the instrument must raise
    so the chokepoint mints nothing.
    """
    banned = scan_banned(source, mathlib=mathlib)
    if banned:
        return LeanCheck(
            kind="failed",
            reason="rejected_constructs",
            banned_constructs=banned,
            diagnostics="source contains constructs that cannot earn a proof "
            f"({', '.join(banned)})",
            mathlib=mathlib,
        )
    if not has_theorem(source):
        return LeanCheck(
            kind="failed",
            reason="no_theorem",
            diagnostics="source must declare a theorem, lemma, or example — "
            "a typechecking empty file is not a proof",
            mathlib=mathlib,
        )

    if mathlib:
        return _check_mathlib(
            source,
            timeout_s=timeout_s,
            lean_bin=lean_bin,
            lake_bin=lake_bin,
            mathlib_root=mathlib_root,
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


def _check_mathlib(
    source: str,
    *,
    timeout_s: float,
    lean_bin: str | None,
    lake_bin: str | None,
    mathlib_root: str | None,
) -> LeanCheck:
    lake = lake_bin if lake_bin is not None else lake_binary()
    root = mathlib_project_root(mathlib_root)
    rev = read_mathlib_rev(root)
    if not lake or not mathlib_project_ready(root):
        return LeanCheck(
            kind="unavailable",
            reason="mathlib_unavailable",
            diagnostics="Mathlib / lake project is not installed on this runtime — "
            "optional toolchain; recorded as undecided, never a proof. "
            "Rebuild the image with INSTALL_LEAN=1 INSTALL_MATHLIB=1 "
            "(see docs/operations/deploy.md)",
            mathlib=True,
            mathlib_rev=rev,
        )
    assert root is not None  # ready ⇒ root is a directory
    version = detect_lean_version(lean_bin if lean_bin is not None else lean_binary())
    return _run_lake(
        source,
        lake_bin=lake,
        lean_bin=lean_bin,
        project_root=root,
        timeout_s=timeout_s,
        version=version,
        mathlib_rev=rev,
    )


def _materialize_overlay(tmp: str, project_root: str) -> None:
    """Copy the lakefile pin into ``tmp`` and symlink the cached ``.lake`` tree."""
    for name in (*_LAKEFILE_NAMES, "lake-manifest.json", "lean-toolchain"):
        src = os.path.join(project_root, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(tmp, name))
    cached = os.path.join(project_root, ".lake")
    if os.path.isdir(cached):
        os.symlink(cached, os.path.join(tmp, ".lake"), target_is_directory=True)


def _run_lake(
    source: str,
    *,
    lake_bin: str,
    lean_bin: str | None,
    project_root: str,
    timeout_s: float,
    version: str | None,
    mathlib_rev: str | None,
) -> LeanCheck:
    """Spawn ``lake --offline env lean`` on an overlay of the cached project."""
    lean = lean_bin if lean_bin is not None else (lean_binary() or "lean")
    with tempfile.TemporaryDirectory(prefix="ot-lake-") as tmp:
        try:
            _materialize_overlay(tmp, project_root)
        except OSError as exc:
            return LeanCheck(
                kind="unavailable",
                reason="mathlib_unavailable",
                diagnostics=f"Mathlib lake overlay could not be prepared: {exc}",
                lean_version=version,
                mathlib=True,
                mathlib_rev=mathlib_rev,
            )
        path = os.path.join(tmp, "Snippet.lean")
        _write_snippet(path, source)
        return _run_process(
            [lake_bin, "--offline", "env", lean, path],
            cwd=tmp,
            timeout_s=timeout_s,
            version=version,
            mathlib=True,
            mathlib_rev=mathlib_rev,
            lake_used=True,
        )


def _run_lean(
    source: str,
    *,
    binary: str,
    timeout_s: float,
    version: str | None,
) -> LeanCheck:
    """Spawn ``lean`` on a temp file; kill the process group on soft timeout."""
    with tempfile.TemporaryDirectory(prefix="ot-lean-") as tmp:
        path = os.path.join(tmp, "Snippet.lean")
        _write_snippet(path, source)
        return _run_process(
            [binary, path],
            cwd=tmp,
            timeout_s=timeout_s,
            version=version,
        )


def _write_snippet(path: str, source: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(source)
        if not source.endswith("\n"):
            handle.write("\n")


def _run_process(
    cmd: list[str],
    *,
    cwd: str,
    timeout_s: float,
    version: str | None,
    mathlib: bool = False,
    mathlib_rev: str | None = None,
    lake_used: bool = False,
) -> LeanCheck:
    budget = max(0.2, timeout_s)
    try:
        # New session so a hang can be SIGKILL'd as a group (grandchild-safe).
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
    except OSError as exc:
        reason = "mathlib_unavailable" if mathlib else "unavailable"
        tool = "lake" if mathlib else "lean"
        return LeanCheck(
            kind="unavailable",
            reason=reason,
            diagnostics=f"{tool} could not be executed: {exc}",
            lean_version=version,
            mathlib=mathlib,
            mathlib_rev=mathlib_rev,
            lake_used=lake_used,
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
            diagnostics=f"{cmd[0]} exceeded the {budget:.1f}s soft timeout",
            lean_version=version,
            mathlib=mathlib,
            mathlib_rev=mathlib_rev,
            lake_used=lake_used,
        )

    combined = _clip("\n".join(part for part in (stdout, stderr) if part))
    code = proc.returncode
    if code is None:
        return LeanCheck(
            kind="crash",
            reason="crash",
            diagnostics=combined or "lean exited without a status",
            lean_version=version,
            mathlib=mathlib,
            mathlib_rev=mathlib_rev,
            lake_used=lake_used,
        )
    if code < 0:
        return LeanCheck(
            kind="crash",
            reason="crash",
            diagnostics=combined or f"lean killed by signal {-code}",
            lean_version=version,
            exit_code=code,
            mathlib=mathlib,
            mathlib_rev=mathlib_rev,
            lake_used=lake_used,
        )
    if code != 0:
        return LeanCheck(
            kind="failed",
            reason="failed",
            diagnostics=combined or f"lean exited {code}",
            lean_version=version,
            exit_code=code,
            mathlib=mathlib,
            mathlib_rev=mathlib_rev,
            lake_used=lake_used,
        )
    return LeanCheck(
        kind="proved",
        reason=None,
        diagnostics=combined,
        lean_version=version,
        exit_code=0,
        mathlib=mathlib,
        mathlib_rev=mathlib_rev,
        lake_used=lake_used,
    )


def _kill_group(proc: subprocess.Popen[str]) -> None:
    """SIGKILL the child's process group; ignore races where it already exited."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except PermissionError:
        proc.kill()
