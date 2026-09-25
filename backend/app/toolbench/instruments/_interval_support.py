"""Interval / ball evaluation — proven enclosures for ``interval.eval``.

Prefers **python-flint** (Arb ball arithmetic). Falls back to ``mpmath.iv``
(already a SymPy dependency) if the C extension fails to import, so a missing
or broken wheel is honest ``undecided`` / degrade rather than a boot failure.

Bounds are strings: exact integers / ``p/q`` when the ball is an exact rational,
otherwise a directed decimal enclosure from Arb's ``mid_rad_10exp`` (or the
mpmath interval endpoints converted the same way). **Never** a Python ``float``.

A relation is decided only when the two enclosures are disjoint or are the same
exact singleton. Overlap is ``None`` (the instrument records ``undecided``).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Literal

import mpmath
import sympy
from sympy.core.expr import Expr

# --- engine pin ----------------------------------------------------------------------------------

ENGINE_ARB = "python-flint"
ENGINE_IV = "mpmath.iv"
ENGINE_UNAVAILABLE = "unavailable"
METHOD_ARB = "arb"
METHOD_IV = "mpmath.iv"

_FLINT: Any | None
_FLINT_IMPORT_ERROR: str | None
try:
    import flint as _flint_mod

    _FLINT = _flint_mod
    _FLINT_IMPORT_ERROR = None
except ImportError as exc:  # pragma: no cover — wheel present in the locked env
    _FLINT = None
    _FLINT_IMPORT_ERROR = str(exc)


def flint_available() -> bool:
    return _FLINT is not None


def engine_pin() -> tuple[str, str]:
    """``(engine, engine_version)`` for the blame tuple — what will actually run."""
    if _FLINT is not None:
        return ENGINE_ARB, getattr(_FLINT, "__version__", "unknown")
    return ENGINE_IV, mpmath.__version__


ENGINE, ENGINE_VERSION = engine_pin()


# --- outcomes ------------------------------------------------------------------------------------

Reason = Literal[
    "unavailable",
    "timeout",
    "free_symbols",
    "unsupported",
    "non_real",
    "domain",
    "overlap",
]


@dataclass(frozen=True, slots=True)
class Enclosure:
    """A closed real interval that is guaranteed to contain the true value."""

    lo: str
    hi: str
    precision_bits: int
    method: str
    lo_frac: Fraction
    hi_frac: Fraction


@dataclass(frozen=True, slots=True)
class EvalOutcome:
    kind: Literal["enclosed", "undecided"]
    enclosure: Enclosure | None = None
    reason: str | None = None


class _CannotEnclose(Exception):
    """Internal: walk failed for an honest (non-input) reason."""

    def __init__(self, reason: Reason) -> None:
        super().__init__(reason)
        self.reason = reason


# --- public evaluate -----------------------------------------------------------------------------


def enclose(
    expr: Expr,
    *,
    precision_bits: int,
    timeout_ms: int,
    now: Any = time.monotonic,
) -> EvalOutcome:
    """Enclose ``expr`` at ``precision_bits``. Timeout / domain / symbols → undecided."""
    if expr.free_symbols:
        return EvalOutcome(kind="undecided", reason="free_symbols")
    started = now()
    if timeout_ms <= 0:
        return EvalOutcome(kind="undecided", reason="timeout")
    try:
        if _FLINT is not None:
            enclosure = _enclose_arb(expr, precision_bits)
        else:
            enclosure = _enclose_iv(expr, precision_bits)
    except _CannotEnclose as exc:
        return EvalOutcome(kind="undecided", reason=exc.reason)
    if (now() - started) * 1000 > timeout_ms:
        return EvalOutcome(kind="undecided", reason="timeout")
    return EvalOutcome(kind="enclosed", enclosure=enclosure)


def decide_relation(left: Enclosure, right: Enclosure, op: str) -> bool | None:
    """Decide ``left op right`` from two enclosures → True / False / None (overlap)."""
    a0, a1 = left.lo_frac, left.hi_frac
    b0, b1 = right.lo_frac, right.hi_frac
    disjoint = a1 < b0 or b1 < a0
    exact_equal = a0 == a1 == b0 == b1

    if op == "==":
        if exact_equal:
            return True
        if disjoint:
            return False
        return None
    if op == "!=":
        if exact_equal:
            return False
        if disjoint:
            return True
        return None
    if op == "<":
        if a1 < b0:
            return True
        if a0 >= b1:
            return False
        return None
    if op == "<=":
        if a1 <= b0:
            return True
        if a0 > b1:
            return False
        return None
    if op == ">":
        if a0 > b1:
            return True
        if a1 <= b0:
            return False
        return None
    if op == ">=":
        if a0 >= b1:
            return True
        if a1 < b0:
            return False
        return None
    raise ValueError(f"unknown relational operator {op!r}")


# --- python-flint / Arb --------------------------------------------------------------------------

_MAX_FACTORIAL = 20
_MAX_ROOT_INDEX = 32


def _enclose_arb(expr: Expr, precision_bits: int) -> Enclosure:
    flint = _FLINT
    assert flint is not None
    with flint.ctx.workprec(precision_bits):
        ball = _expr_to_arb(expr, flint)
        if not ball.is_finite() or ball.is_nan():
            raise _CannotEnclose("domain")
        return _arb_to_enclosure(ball, precision_bits)


def _expr_to_arb(expr: Expr, flint: Any) -> Any:
    _reject_float_literal(expr)
    if expr == sympy.I or expr.is_infinite:
        raise _CannotEnclose("non_real")
    if expr.is_Integer:
        return flint.arb(int(expr))
    if expr.is_Rational:
        numer, denom = expr.as_numer_denom()
        return flint.arb(flint.fmpq(int(numer), int(denom)))
    if expr == sympy.pi:
        return flint.arb.pi()
    if expr == sympy.E:
        return flint.arb(0).const_e()
    if expr.is_Add:
        acc = flint.arb(0)
        for arg in expr.args:
            acc += _expr_to_arb(arg, flint)
        return acc
    if expr.is_Mul:
        acc = flint.arb(1)
        for arg in expr.args:
            acc *= _expr_to_arb(arg, flint)
        return acc
    if expr.is_Pow:
        base = _expr_to_arb(expr.args[0], flint)
        exponent = _expr_to_arb(expr.args[1], flint)
        return base**exponent
    if expr.is_Function:
        return _arb_call(expr, flint)
    raise _CannotEnclose("unsupported")


def _arb_call(expr: Expr, flint: Any) -> Any:
    args = [_expr_to_arb(arg, flint) for arg in expr.args]
    func = expr.func
    if func is sympy.sqrt:
        return args[0].sqrt()
    if func is sympy.cbrt:
        return args[0].root(3)
    if func is sympy.root:
        index = _exact_small_int(args[1], limit=_MAX_ROOT_INDEX)
        if index is None or index == 0:
            raise _CannotEnclose("unsupported")
        return args[0].root(index)
    if func is sympy.exp:
        return args[0].exp()
    if func in (sympy.log, sympy.ln):
        return args[0].log()
    if func is sympy.sin:
        return args[0].sin()
    if func is sympy.cos:
        return args[0].cos()
    if func is sympy.tan:
        return args[0].tan()
    if func is sympy.asin:
        return args[0].asin()
    if func is sympy.acos:
        return args[0].acos()
    if func is sympy.atan:
        return args[0].atan()
    if func is sympy.atan2:
        return args[0].atan2(args[1])
    if func is sympy.sinh:
        return args[0].sinh()
    if func is sympy.cosh:
        return args[0].cosh()
    if func is sympy.tanh:
        return args[0].tanh()
    if func is sympy.Abs:
        return abs(args[0])
    if func is sympy.factorial:
        n = _exact_small_int(args[0], limit=_MAX_FACTORIAL)
        if n is None or n < 0:
            raise _CannotEnclose("unsupported")
        return flint.arb(n).fac()
    if func is sympy.gamma:
        return args[0].gamma()
    raise _CannotEnclose("unsupported")


def _exact_small_int(ball: Any, *, limit: int) -> int | None:
    if not (ball.is_exact() and ball.is_integer()):
        return None
    value = int(ball.unique_fmpz())
    if abs(value) > limit:
        return None
    return value


def _arb_to_enclosure(ball: Any, precision_bits: int) -> Enclosure:
    if ball.is_exact():
        if ball.is_integer():
            n = int(ball.unique_fmpz())
            frac = Fraction(n)
            text = str(n)
            return Enclosure(
                lo=text,
                hi=text,
                precision_bits=precision_bits,
                method=METHOD_ARB,
                lo_frac=frac,
                hi_frac=frac,
            )
        try:
            q = ball.fmpq()
            frac = Fraction(int(q.p), int(q.q)) if hasattr(q, "p") else Fraction(str(q))
            text = _fraction_text(frac)
            return Enclosure(
                lo=text,
                hi=text,
                precision_bits=precision_bits,
                method=METHOD_ARB,
                lo_frac=frac,
                hi_frac=frac,
            )
        except (ValueError, AttributeError, TypeError):
            pass

    digits = _decimal_digits(precision_bits)
    mid, rad, exp = ball.mid_rad_10exp(digits)
    mid_i, rad_i, exp_i = int(mid), int(rad), int(exp)
    lo_frac = _man_exp_fraction(mid_i - rad_i, exp_i)
    hi_frac = _man_exp_fraction(mid_i + rad_i, exp_i)
    return Enclosure(
        lo=_decimal_from_man_exp(mid_i - rad_i, exp_i),
        hi=_decimal_from_man_exp(mid_i + rad_i, exp_i),
        precision_bits=precision_bits,
        method=METHOD_ARB,
        lo_frac=lo_frac,
        hi_frac=hi_frac,
    )


# --- mpmath.iv fallback --------------------------------------------------------------------------


def _enclose_iv(expr: Expr, precision_bits: int) -> Enclosure:
    from mpmath import iv

    digits = _decimal_digits(precision_bits) + 8
    old = iv.dps
    try:
        iv.dps = digits
        interval = _expr_to_iv(expr, iv)
        if getattr(iv, "isnan", lambda _x: False)(interval):
            raise _CannotEnclose("domain")
        lo_frac = _iv_endpoint_fraction(interval.a)
        hi_frac = _iv_endpoint_fraction(interval.b)
    except mpmath.libmp.ComplexResult as exc:
        raise _CannotEnclose("non_real") from exc
    finally:
        iv.dps = old
    return Enclosure(
        lo=_bound_text(lo_frac, digits=_decimal_digits(precision_bits), upper=False),
        hi=_bound_text(hi_frac, digits=_decimal_digits(precision_bits), upper=True),
        precision_bits=precision_bits,
        method=METHOD_IV,
        lo_frac=lo_frac,
        hi_frac=hi_frac,
    )


def _expr_to_iv(expr: Expr, iv: Any) -> Any:
    _reject_float_literal(expr)
    if expr == sympy.I or expr.is_infinite:
        raise _CannotEnclose("non_real")
    if expr.is_Integer:
        return iv.mpf(int(expr))
    if expr.is_Rational:
        numer, denom = expr.as_numer_denom()
        return iv.mpf(int(numer)) / iv.mpf(int(denom))
    if expr == sympy.pi:
        return iv.pi
    if expr == sympy.E:
        return iv.e
    if expr.is_Add:
        acc = iv.mpf(0)
        for arg in expr.args:
            acc += _expr_to_iv(arg, iv)
        return acc
    if expr.is_Mul:
        acc = iv.mpf(1)
        for arg in expr.args:
            acc *= _expr_to_iv(arg, iv)
        return acc
    if expr.is_Pow:
        return _expr_to_iv(expr.args[0], iv) ** _expr_to_iv(expr.args[1], iv)
    if expr.is_Function:
        return _iv_call(expr, iv)
    raise _CannotEnclose("unsupported")


def _iv_call(expr: Expr, iv: Any) -> Any:
    args = [_expr_to_iv(arg, iv) for arg in expr.args]
    func = expr.func
    mapping = {
        sympy.sqrt: iv.sqrt,
        sympy.exp: iv.exp,
        sympy.log: iv.log,
        sympy.ln: iv.ln if hasattr(iv, "ln") else iv.log,
        sympy.sin: iv.sin,
        sympy.cos: iv.cos,
        sympy.tan: iv.tan,
        sympy.asin: iv.asin,
        sympy.acos: iv.acos,
        sympy.atan: iv.atan,
        sympy.sinh: iv.sinh,
        sympy.cosh: iv.cosh,
        sympy.tanh: iv.tanh,
        sympy.Abs: abs,
        sympy.gamma: iv.gamma,
    }
    if func in mapping:
        return mapping[func](args[0])
    if func is sympy.atan2:
        return iv.atan2(args[0], args[1])
    if func is sympy.cbrt:
        return args[0] ** (iv.mpf(1) / iv.mpf(3))
    if func is sympy.root:
        return args[0] ** (iv.mpf(1) / args[1])
    if func is sympy.factorial:
        return iv.factorial(args[0])
    raise _CannotEnclose("unsupported")


def _iv_endpoint_fraction(endpoint: Any) -> Fraction:
    """Exact dyadic rational for an ``ivmpf`` endpoint (uses the raw ``_mpi_`` tuple)."""
    lo, _hi = endpoint._mpi_
    return _mpf_tuple_to_fraction(lo)


def _mpf_tuple_to_fraction(raw: tuple[int, int, int, int]) -> Fraction:
    sign, man, exp, _bc = raw
    if man == 0:
        return Fraction(0)
    if exp >= 0:
        value = Fraction(man << exp)
    else:
        value = Fraction(man, 1 << (-exp))
    return -value if sign else value


# --- formatting ----------------------------------------------------------------------------------


def _decimal_digits(precision_bits: int) -> int:
    # floor(bits * log10(2)) — the decimal digits that precision honestly supports.
    return max(2, (precision_bits * 30103) // 100000)


def _man_exp_fraction(man: int, exp: int) -> Fraction:
    if exp >= 0:
        return Fraction(man) * (Fraction(10) ** exp)
    return Fraction(man, 10 ** (-exp))


def _decimal_from_man_exp(man: int, exp: int) -> str:
    """Exact decimal literal for ``man * 10**exp`` — no float."""
    if man == 0:
        return "0"
    sign = "-" if man < 0 else ""
    digits = str(abs(man))
    if exp >= 0:
        return sign + digits + ("0" * exp)
    point = len(digits) + exp
    if point > 0:
        return sign + digits[:point] + "." + digits[point:]
    return sign + "0." + ("0" * (-point)) + digits


def _fraction_text(frac: Fraction) -> str:
    frac = Fraction(frac.numerator, frac.denominator)
    if frac.denominator == 1:
        return str(frac.numerator)
    return f"{frac.numerator}/{frac.denominator}"


def _bound_text(frac: Fraction, *, digits: int, upper: bool) -> str:
    """Directed decimal (or exact p/q) for an mpmath fallback endpoint."""
    if frac.denominator == 1:
        return str(frac.numerator)
    if frac.denominator <= 10_000 and abs(frac.numerator) <= 10**12:
        return _fraction_text(frac)
    from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, localcontext

    with localcontext() as ctx:
        ctx.prec = digits + 12
        value = Decimal(frac.numerator) / Decimal(frac.denominator)
        quant = Decimal(10) ** -digits
        rounding = ROUND_CEILING if upper else ROUND_FLOOR
        rounded = value.quantize(quant, rounding=rounding)
    text = format(rounded, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _reject_float_literal(expr: Expr) -> None:
    """A decimal token is not an exact input — raise (mint nothing), never enclose it."""
    if expr.is_Float:
        raise ValueError(
            "decimal/float literals are not accepted — use exact rationals (1/2, 22/7)"
        )
    for arg in expr.args:
        if getattr(arg, "is_Float", False):
            raise ValueError(
                "decimal/float literals are not accepted — use exact rationals (1/2, 22/7)"
            )
        if arg.args:
            _reject_float_literal(arg)


def enclosure_latex(enclosure: Enclosure) -> str:
    """KaTeX companion for ``[lo, hi]`` — presentation only."""
    return rf"\left[{_latex_num(enclosure.lo)}, {_latex_num(enclosure.hi)}\right]"


def _latex_num(text: str) -> str:
    if "/" in text and not text.startswith("-"):
        p, q = text.split("/", 1)
        return rf"\frac{{{p}}}{{{q}}}"
    if "/" in text and text.startswith("-"):
        p, q = text[1:].split("/", 1)
        return rf"-\frac{{{p}}}{{{q}}}"
    return text
