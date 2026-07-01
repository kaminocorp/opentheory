"""Shared SymPy plumbing for the Tier-0 in-process instruments (Phase 4).

Three concerns live here so the instruments themselves stay thin:

- **The engine pin.** ``ENGINE`` / ``ENGINE_VERSION`` are read from the installed SymPy at import
  and stamped into every blame tuple, so a recorded result names the exact engine that produced it
  (the reproducibility contract — the write-path test asserts it lands verbatim).
- **A curated-namespace parser.** ``parse`` turns a text expression into a SymPy object through
  ``parse_expr`` restricted to an allow-list of math names (``_SAFE_NAMESPACE``). This is *not* a
  security sandbox — it is a cheap, honest reduction of the obvious ``__import__('os')`` /
  attribute-walk vectors, because a bare ``sympify`` ``eval``s against the whole SymPy namespace.
  The real resource/exec sandbox is the deferred execution substrate (``agent-research-tools.md``
  §6); until then these instruments are human-invokable and Phase 6 gates them to project members.
- **Assumptions → SymPy symbols.** ``symbol_assumptions`` reads the free-form assumption map the
  ledger records and pulls out the *per-symbol* SymPy assumptions (``{"x": {"positive": true}}``),
  so a result can be computed *under* them (``Symbol('x', positive=True)``) — the plumbing that lets
  ``expr.compare`` prove ``√(x²) = x`` only when ``x > 0``. Contextual keys (``{"angle": 90}``) are
  left alone; a *misspelled* SymPy predicate fails loud (a silently-ignored assumption would record
  a misleading unconditional result the append-only ledger could never edit out).
"""

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


def parse(text: str, assumptions: dict[str, dict[str, bool]]) -> Expr:
    """Parse ``text`` to a SymPy expression, binding named symbols to their assumptions.

    ``assumptions`` is the *per-symbol* map from :func:`symbol_assumptions`; each name is pre-bound
    as an assumption-carrying ``Symbol`` so a symbol used in ``text`` is created *under* its flags.
    Any parse failure is re-raised as a plain ``ValueError`` (the write path turns that into a 422:
    the instrument did not run, so nothing is minted).
    """
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
