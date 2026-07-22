"""Shared Z3 plumbing for ``z3.prove`` — the security-critical translator + solver harness.

Mirrors :mod:`app.toolbench.instruments._sympy_support` in role:

- **Engine pin.** ``ENGINE`` / ``ENGINE_VERSION`` are read from the installed Z3 at import and
  stamped into every blame tuple (reproducibility contract).
- **Closed allow-list translator.** ``to_z3`` maps a *whitelist* of SymPy node types to Z3.
  No string round-trip, no ``eval``. Undeclared symbols, ``Float`` literals, and any
  non-whitelisted node raise ``ValueError`` (→ write path mints nothing, 422).
- **Relation bridge.** ``relation_to_z3`` reuses the hardened ``split_relation`` + ``parse`` gate
  so the ``0.9.7`` ``parse_expr``-is-``eval`` lesson is inherited, not re-learned.
- **Two-stage solver.** ``solve`` first checks hypotheses alone (vacuous-proof guard), then
  ``H ∧ ¬goal``. Soft timeout under the subprocess wall-clock so a hard problem returns
  ``unknown`` → honest ``undecided`` rather than a sandbox kill.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

import z3
from sympy import Add, Basic, Float, Integer, Mul, Pow, Rational, Symbol
from sympy.core.expr import Expr

from app.toolbench.instruments._sympy_support import parse, split_relation

ENGINE = "z3"
ENGINE_VERSION = z3.get_version_string()

SORTS = frozenset({"int", "real"})

# Relational op → Z3 boolean constructor over two arithmetic terms.
_OP_TO_Z3 = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
}


def declare(name: str, sort: str) -> z3.ExprRef:
    """Bind ``name`` to a Z3 constant of the declared sort (``int`` / ``real``)."""
    if sort not in SORTS:
        raise ValueError(f"unknown sort {sort!r} (allowed: {sorted(SORTS)})")
    if sort == "int":
        return z3.Int(name)
    return z3.Real(name)


def _align_sorts(left: z3.ExprRef, right: z3.ExprRef) -> tuple[z3.ExprRef, z3.ExprRef]:
    """Promote Int→Real when operands disagree so mixed arithmetic is well-sorted."""
    ls, rs = left.sort(), right.sort()
    if ls == rs:
        return left, right
    if ls == z3.IntSort() and rs == z3.RealSort():
        return z3.ToReal(left), right
    if ls == z3.RealSort() and rs == z3.IntSort():
        return left, z3.ToReal(right)
    raise ValueError(f"cannot combine Z3 sorts {ls} and {rs}")


def to_z3(expr: Expr | Basic, env: dict[str, z3.ExprRef]) -> z3.ExprRef:
    """Translate a SymPy expression to Z3 via a closed allow-list of node types.

    Raises ``ValueError`` on ``Float``, undeclared symbols, or any non-whitelisted node.
    Nonlinear terms (e.g. ``x*y``, ``x**2``) are *permitted* — Z3 accepts them and may
    honestly return ``unknown`` on the undecidable fragment.
    """
    if isinstance(expr, Float):
        raise ValueError(
            "float literals are not allowed — use exact rationals (e.g. 1/2), never decimals"
        )

    # Integer is a Rational subclass in SymPy — check Integer first.
    if isinstance(expr, Integer):
        return z3.IntVal(int(expr))

    if isinstance(expr, Rational):
        # Exact p/q — never float. RealVal accepts a fraction string.
        return z3.RealVal(f"{expr.p}/{expr.q}")

    if isinstance(expr, Symbol):
        name = str(expr)
        if name not in env:
            raise ValueError(f"undeclared variable {name!r}")
        return env[name]

    if isinstance(expr, Add):
        args = [to_z3(arg, env) for arg in expr.args]
        acc = args[0]
        for term in args[1:]:
            a, b = _align_sorts(acc, term)
            acc = a + b
        return acc

    if isinstance(expr, Mul):
        args = [to_z3(arg, env) for arg in expr.args]
        acc = args[0]
        for factor in args[1:]:
            a, b = _align_sorts(acc, factor)
            acc = a * b
        return acc

    if isinstance(expr, Pow):
        base_expr, exp_expr = expr.args
        if not isinstance(exp_expr, Integer):
            raise ValueError(
                "exponent must be a non-negative integer constant "
                f"(got {exp_expr!r})"
            )
        exp_n = int(exp_expr)
        if exp_n < 0:
            raise ValueError(
                f"negative exponents are not allowed in v1 (got **{exp_n})"
            )
        base = to_z3(base_expr, env)
        # z3py: Expr ** int works for both Int and Real bases.
        return base**exp_n

    raise ValueError(
        f"unsupported expression node {type(expr).__name__} — only integer/rational "
        "literals, declared symbols, +, *, and non-negative integer powers are allowed"
    )


def relation_to_z3(
    text: str,
    env: dict[str, z3.ExprRef],
    symbol_flags: dict[str, dict[str, bool]],
) -> z3.BoolRef:
    """Parse a top-level relation through the hardened gate and translate to a Z3 boolean."""
    parts = split_relation(text)
    if parts is None:
        raise ValueError("relation must contain a top-level relational operator")
    left_text, op, right_text = parts
    if op not in _OP_TO_Z3:
        raise ValueError(f"unsupported relational operator {op!r}")
    left = to_z3(parse(left_text, symbol_flags), env)
    right = to_z3(parse(right_text, symbol_flags), env)
    left, right = _align_sorts(left, right)
    return _OP_TO_Z3[op](left, right)


def _render_model_value(val: z3.ExprRef) -> str:
    """Render a Z3 model value as an exact string (int or ``p/q``), never a float."""
    if z3.is_int_value(val):
        return str(val.as_long())
    if z3.is_rational_value(val):
        # RatNumRef: prefer as_fraction when available; fall back to num/den.
        if hasattr(val, "as_fraction"):
            frac: Fraction = val.as_fraction()
            if frac.denominator == 1:
                return str(frac.numerator)
            return f"{frac.numerator}/{frac.denominator}"
        num = val.numerator_as_long()
        den = val.denominator_as_long()
        if den == 1:
            return str(num)
        return f"{num}/{den}"
    # Algebraic / other — string form is still exact (no float coercion).
    return val.sexpr() if hasattr(val, "sexpr") else str(val)


def render_model(model: z3.ModelRef, env: dict[str, z3.ExprRef]) -> dict[str, str]:
    """Project a Z3 model onto the declared variables as exact strings, sorted by name."""
    out: dict[str, str] = {}
    for name in sorted(env):
        const = env[name]
        interpreted = model.eval(const, model_completion=True)
        out[name] = _render_model_value(interpreted)
    return out


@dataclass(frozen=True)
class SolveOutcome:
    """Result of the two-stage validity check."""

    kind: Literal["proven", "refuted", "undecided"]
    model: dict[str, str] | None = None
    reason: str | None = None
    certificate: str | None = None
    used_hypotheses: list[str] | None = None


def _reason_unknown(solver: z3.Solver) -> str:
    raw = solver.reason_unknown()
    text = str(raw).lower() if raw is not None else ""
    if "timeout" in text or "canceled" in text or "cancelled" in text:
        return "timeout"
    return "incomplete"


def solve(
    hypotheses: list[tuple[str, z3.BoolRef]],
    goal: z3.BoolRef,
    *,
    env: dict[str, z3.ExprRef],
    timeout_ms: int,
) -> SolveOutcome:
    """Two-stage check: hypotheses-sat guard, then ``H ∧ ¬goal``.

    ``hypotheses`` are ``(track_name, formula)`` pairs — track names appear in the unsat-core
    when the goal is proven, so a reader sees which hypotheses the proof actually used.

    Vacuous guard: if the hypotheses alone are ``unsat``, return ``undecided`` with
    ``contradictory_hypotheses`` — never a ``proven`` (ex falso).
    """
    if timeout_ms < 1:
        raise ValueError("timeout_ms must be >= 1")

    # --- stage 1: hypotheses alone -----------------------------------------------------------
    if hypotheses:
        hyp_solver = z3.Solver()
        hyp_solver.set("timeout", timeout_ms)
        for _name, formula in hypotheses:
            hyp_solver.add(formula)
        hyp_check = hyp_solver.check()
        if hyp_check == z3.unsat:
            return SolveOutcome(kind="undecided", reason="contradictory_hypotheses")
        if hyp_check == z3.unknown:
            return SolveOutcome(
                kind="undecided",
                reason="hypotheses_undecided",
            )
        # sat — proceed

    # --- stage 2: H ∧ ¬goal ------------------------------------------------------------------
    solver = z3.Solver()
    solver.set("timeout", timeout_ms)
    for name, formula in hypotheses:
        solver.assert_and_track(formula, name)
    # Negated goal is not a hypothesis — plain assert (not tracked as a used hyp).
    solver.add(z3.Not(goal))
    check = solver.check()

    if check == z3.unsat:
        core = solver.unsat_core()
        used = sorted({str(c) for c in core})
        return SolveOutcome(
            kind="proven",
            certificate="unsat",
            used_hypotheses=used or None,
        )

    if check == z3.sat:
        model = solver.model()
        return SolveOutcome(kind="refuted", model=render_model(model, env))

    # unknown
    return SolveOutcome(kind="undecided", reason=_reason_unknown(solver))


def symbol_flags_for(variables: dict[str, str]) -> dict[str, dict[str, bool]]:
    """SymPy parse flags for declared variables (int → integer, real → real)."""
    out: dict[str, dict[str, bool]] = {}
    for name, sort in variables.items():
        if sort == "int":
            out[name] = {"integer": True}
        elif sort == "real":
            out[name] = {"real": True}
        else:
            raise ValueError(f"unknown sort {sort!r} for {name!r}")
    return out


def free_symbol_names(*exprs: Expr | Basic) -> frozenset[str]:
    """Union of free symbol names across parsed expressions."""
    names: set[str] = set()
    for expr in exprs:
        names.update(str(s) for s in expr.free_symbols)
    return frozenset(names)


# Re-export a tiny typing helper so the instrument can annotate without importing z3 elsewhere.
Z3Env = dict[str, z3.ExprRef]
