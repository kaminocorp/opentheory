"""Shared SymPy plumbing for the Tier-0 in-process instruments (Phase 4).

Three concerns live here so the instruments themselves stay thin:

- **The engine pin.** ``ENGINE`` / ``ENGINE_VERSION`` are read from the installed SymPy at import
  and stamped into every blame tuple, so a recorded result names the exact engine that produced it
  (the reproducibility contract — the write-path test asserts it lands verbatim).
- **A safe parser.** ``parse`` turns a text expression into a SymPy object through ``parse_expr``.
  ``parse_expr`` compiles to ``eval``, and a namespace allow-list (``_SAFE_NAMESPACE``) alone does
  **not** sandbox it: an allow-listed object leaks the real builtins via ``sqrt.__globals__`` and an
  attribute/subscript walk reaches ``object.__subclasses__`` — i.e. arbitrary code execution. So
  before ``parse_expr`` ever sees the text, ``_reject_unsafe_source`` validates its AST against a
  strict allow-list (arithmetic + calls to bare math names only; **no** attribute access,
  subscripting, dunder names, or comprehensions), which removes the eval-escape class entirely, and
  applies size/exponent caps against the cheapest resource bombs — including (0.9.8) a numeric
  **power tower** (``2**(2**30)``), which the constant-exponent cap misses because the exponent is
  itself an expression. What remains deferred to the execution sandbox (``agent-research-tools.md``
  §6) is a *hard CPU/memory bound* on the remaining legal-but-expensive inputs (chiefly a
  ``factorial`` / ``gamma`` of a huge argument); the write path mitigates that by running these
  synchronous instruments off the event loop, so such a case degrades one worker thread rather than
  freezing the process — but a single huge-integer allocation can still OOM the worker, so the hard
  bound is a genuine prerequisite for an untrusted/agent caller. Phase 6 gates runs to members.
- **Assumptions → SymPy symbols.** ``symbol_assumptions`` reads the free-form assumption map the
  ledger records and pulls out the *per-symbol* SymPy assumptions (``{"x": {"positive": true}}``),
  so a result can be computed *under* them (``Symbol('x', positive=True)``) — the plumbing that lets
  ``expr.compare`` prove ``√(x²) = x`` only when ``x > 0``. Contextual keys (``{"angle": 90}``) are
  left alone; a *misspelled* SymPy predicate fails loud (a silently-ignored assumption would record
  a misleading unconditional result the append-only ledger could never edit out).
"""

import ast

import sympy
from sympy import Symbol
from sympy.core.expr import Expr
from sympy.parsing.sympy_parser import (
    convert_xor,
    parse_expr,
    standard_transformations,
)

ENGINE = "sympy"
ENGINE_VERSION = sympy.__version__

# The names an expression may reference. ``Symbol`` / ``Integer`` / ``Float`` / ``Rational`` are the
# constructors ``parse_expr``'s own transformations emit into the code it evaluates, so they must be
# present; the rest is a curated math surface. Anything else in the input becomes a free symbol (or
# fails to resolve) rather than reaching an arbitrary attribute.
_ALLOWED_NAMES = (
    # constructors the parser's transformations emit
    "Symbol", "Integer", "Float", "Rational",
    # constants
    "pi", "E", "I", "oo",
    # roots / powers / logs
    "sqrt", "cbrt", "root", "exp", "log", "ln",
    # trig + inverse + hyperbolic
    "sin", "cos", "tan", "cot", "sec", "csc",
    "asin", "acos", "atan", "atan2",
    "sinh", "cosh", "tanh",
    # misc scalar functions
    "Abs", "sign", "floor", "ceiling", "factorial", "gamma", "Min", "Max",
)  # fmt: skip
_SAFE_NAMESPACE = {name: getattr(sympy, name) for name in _ALLOWED_NAMES}

# ``convert_xor`` lets ``^`` mean exponentiation alongside ``**`` (a mathematician's habit); the
# standard set supplies auto-number, auto-symbol, and factorial notation.
_TRANSFORMS = standard_transformations + (convert_xor,)

# The SymPy assumption predicates we accept on a symbol. Kept to the well-known, JSON-friendly
# booleans; an unrecognized key is a caller error (fail loud), never silently dropped.
SYMPY_ASSUMPTION_KEYS = frozenset(
    {
        "real", "integer", "rational", "irrational", "positive", "negative",
        "nonnegative", "nonpositive", "nonzero", "zero", "even", "odd",
        "prime", "composite", "complex", "imaginary", "finite", "infinite",
        "commutative",
    }  # fmt: skip
)


def symbol_assumptions(assumptions: dict[str, object]) -> dict[str, dict[str, bool]]:
    """Extract the per-symbol SymPy assumptions from the free-form assumption map.

    An entry whose value is a ``dict`` is read as symbol assumptions (``{"x": {"positive": true}}``)
    — every predicate is validated against :data:`SYMPY_ASSUMPTION_KEYS` and must be a boolean.
    Entries whose value is *not* a dict are contextual provenance (e.g. ``{"angle": 90}``), ignored
    here — they still ride on the recorded Evidence/Artifact, just not as SymPy symbol flags.
    """
    out: dict[str, dict[str, bool]] = {}
    for name, value in assumptions.items():
        if not isinstance(value, dict):
            continue  # contextual assumption, not a per-symbol SymPy flag
        flags: dict[str, bool] = {}
        for predicate, on in value.items():
            if predicate not in SYMPY_ASSUMPTION_KEYS:
                raise ValueError(
                    f"unknown SymPy assumption {predicate!r} on symbol {name!r} "
                    f"(known: {sorted(SYMPY_ASSUMPTION_KEYS)})"
                )
            if not isinstance(on, bool):
                raise ValueError(
                    f"assumption {predicate!r} on symbol {name!r} must be true/false"
                )
            flags[predicate] = on
        if flags:
            out[name] = flags
    return out


# --- the source-safety gate (run before ``parse_expr``'s ``eval``) -------------------------------
# Only these AST node types may appear in an input expression: arithmetic over numeric literals and
# calls to bare (math) names. Attribute access, subscripting, comprehensions, lambdas, and every
# other construct are absent — which is what forecloses the ``eval`` escape (``sqrt.__globals__`` /
# ``(1).__class__.__mro__[-1].__subclasses__()``) a namespace allow-list cannot.
_ALLOWED_AST_NODES = frozenset(
    {
        ast.Expression,
        ast.BinOp, ast.UnaryOp, ast.Call, ast.Name, ast.Load, ast.Constant,
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.BitXor,
        ast.UAdd, ast.USub,
    }  # fmt: skip
)
_MAX_SOURCE_LEN = 1000  # raw expression length
_MAX_AST_NODES = 500  # structural size
_MAX_POW_EXPONENT = 1000  # a constant exponent ('**' / '^') — stops the cheapest 2**huge bomb


def _contains(node: ast.AST, types: type | tuple[type, ...]) -> bool:
    """Whether ``node`` (or any descendant) is one of ``types``."""
    return any(isinstance(child, types) for child in ast.walk(node))


def _reject_unsafe_source(text: str) -> None:
    """Raise ``ValueError`` unless ``text`` is a safe, bounded arithmetic expression.

    A strict AST allow-list applied *before* ``parse_expr`` (which compiles to ``eval``): attribute
    access, subscripting, dunder names, calls to a non-name target, and non-numeric literals are all
    rejected, so the eval-escape vectors never reach ``eval``. Size and constant-exponent caps
    reject the cheapest resource bombs. (A hard bound on legal-but-expensive expressions — power
    towers, huge ``factorial`` — is the deferred sandbox's job; see the module docstring.)
    """
    if len(text) > _MAX_SOURCE_LEN:
        raise ValueError(f"expression too long ({len(text)} > {_MAX_SOURCE_LEN} characters)")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"could not parse {text!r}: {exc}") from exc

    nodes = list(ast.walk(tree))
    if len(nodes) > _MAX_AST_NODES:
        raise ValueError("expression is too complex")
    for node in nodes:
        if type(node) not in _ALLOWED_AST_NODES:
            raise ValueError(
                f"unsupported syntax ({type(node).__name__}) — only arithmetic over numbers and "
                "calls to the allowed math functions are permitted"
            )
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise ValueError(f"name {node.id!r} is not allowed")
        if isinstance(node, ast.Call):
            if node.keywords:
                raise ValueError("keyword arguments are not allowed")
            if not isinstance(node.func, ast.Name):
                raise ValueError("only direct calls to named functions are allowed")
        if isinstance(node, ast.Constant) and not isinstance(node.value, int | float | complex):
            raise ValueError("only numeric literals are allowed")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow | ast.BitXor):
            exponent = node.right
            if (
                isinstance(exponent, ast.Constant)
                and isinstance(exponent.value, int)
                and abs(exponent.value) > _MAX_POW_EXPONENT
            ):
                raise ValueError(f"exponent too large (> {_MAX_POW_EXPONENT})")
            # A *numeric* power used as an exponent is a power tower (``2**(2**30)``): the constant
            # cap above never sees it (the exponent is a BinOp, not a literal), yet it evaluates to
            # an astronomically large integer that OOMs the worker. Reject it. A *symbolic* exponent
            # (``2**(2**n)``) stays symbolic in SymPy — no giant int — so it is left alone; the
            # discriminator is the absence of any name in the exponent subtree. (A huge
            # ``factorial``/``gamma`` argument is a different bomb, still deferred to the sandbox —
            # see the module docstring.)
            if _contains(exponent, ast.Pow | ast.BitXor) and not _contains(exponent, ast.Name):
                raise ValueError("exponent is a numeric power tower (too large to evaluate)")


def parse(text: str, assumptions: dict[str, dict[str, bool]]) -> Expr:
    """Parse ``text`` to a SymPy expression, binding named symbols to their assumptions.

    ``assumptions`` is the *per-symbol* map from :func:`symbol_assumptions`; each name is pre-bound
    as an assumption-carrying ``Symbol`` so a symbol used in ``text`` is created *under* its flags.
    The text is first run through :func:`_reject_unsafe_source` (the eval-escape gate); any parse
    failure is re-raised as a plain ``ValueError`` (the write path turns that into a 422: the
    instrument did not run, so nothing is minted).
    """
    _reject_unsafe_source(text)
    local = {name: Symbol(name, **flags) for name, flags in assumptions.items()}
    try:
        return parse_expr(
            text,
            local_dict=local,
            global_dict=_SAFE_NAMESPACE,
            transformations=_TRANSFORMS,
            evaluate=True,
        )
    except Exception as exc:  # noqa: BLE001 — a parse boundary: any failure is "could not parse"
        raise ValueError(f"could not parse {text!r}: {exc}") from exc
