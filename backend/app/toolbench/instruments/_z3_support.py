"""Shared Z3 plumbing for ``z3.prove`` and ``z3.satisfy``.

Mirrors :mod:`app.toolbench.instruments._sympy_support` in role:

- **Engine pin.** ``ENGINE`` / ``ENGINE_VERSION`` are read from the installed Z3 at import and
  stamped into every blame tuple (reproducibility contract).
- **Closed allow-list translator.** ``to_z3`` maps a *whitelist* of SymPy node types to Z3.
  No string round-trip, no ``eval``. Undeclared symbols, ``Float`` literals, and any
  non-whitelisted node raise ``ValueError`` (→ write path mints nothing, 422).
- **Formula parser (0.38.0).** ``formula_to_z3`` walks a *second* closed AST allow-list —
  relational atoms, bool variables, and ``And`` / ``Or`` / ``Not`` / ``Implies`` / ``Xor`` /
  ``Equivalent`` — without ``parse_expr`` or ``eval``. Quantifiers stay rejected. The
  ``0.9.7`` ``parse_expr``-is-``eval`` lesson is not re-learned: the shared SymPy gate is
  not widened.
- **Relation bridge.** ``relation_to_z3`` still reuses the hardened ``split_relation`` +
  ``parse`` gate for a single top-level relation (the 0.13.x path).
- **Two-stage validity solver.** ``solve`` first checks hypotheses alone (vacuous-proof guard),
  then ``H ∧ ¬goal``. Soft timeout under the subprocess wall-clock so a hard problem returns
  ``unknown`` → honest ``undecided`` rather than a sandbox kill.
- **One-stage model-finder.** ``satisfy`` asserts the constraints as-is (no goal, no vacuous
  guard — ``unsat`` *is* the honest no-model outcome) and returns a concrete assignment on
  ``sat``. Same soft-timeout honesty as ``solve``.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

import z3
from sympy import Add, Basic, Float, Integer, Mul, Pow, Rational, Symbol
from sympy.core.expr import Expr

from app.toolbench.instruments._sympy_support import parse, split_relation

ENGINE = "z3"
ENGINE_VERSION = z3.get_version_string()

SORTS = frozenset({"int", "real", "bool"})

# Names an agent or human may not declare as variables — they are the formula language.
_CONNECTIVE_FUNCS = frozenset({"And", "Or", "Not", "Implies", "Xor", "Equivalent", "Iff"})
_BANNED_FUNCS = frozenset({"ForAll", "Exists", "Forall", "Quantifier", "If"})
RESERVED_NAMES = _CONNECTIVE_FUNCS | _BANNED_FUNCS | frozenset({"True", "False"})

# Relational op → Z3 boolean constructor over two terms of matching sort.
_OP_TO_Z3 = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
}

_COMPARE_OPS: dict[type[ast.cmpop], str] = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
}

# Closed AST allow-list for QF boolean formulas. Attribute access, subscripting, lambdas,
# comprehensions, and string/bytes literals are absent — the same eval-escape class the
# shared SymPy gate closes, applied here without ever calling ``parse_expr``.
_ALLOWED_FORMULA_AST = frozenset(
    {
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Call,
        ast.Name,
        ast.Load,
        ast.Constant,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Pow,
        ast.BitXor,
        ast.UAdd,
        ast.USub,
        ast.Compare,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.BoolOp,
        ast.And,
        ast.Or,
        ast.Not,
    }
)
_MAX_FORMULA_AST_NODES = 500
_MAX_POW_EXPONENT = 1000

# Presentation-only connective TeX. Never hashed (``*_latex`` is stripped).
_CONNECTIVE_LATEX = {
    "And": r"\land",
    "Or": r"\lor",
    "Not": r"\neg",
    "Implies": r"\rightarrow",
    "Xor": r"\oplus",
    "Equivalent": r"\leftrightarrow",
    "Iff": r"\leftrightarrow",
}
_COMPARE_LATEX = {
    "==": "=",
    "!=": r"\neq",
    "<=": r"\leq",
    ">=": r"\geq",
    "<": "<",
    ">": ">",
}


def declare(name: str, sort: str) -> z3.ExprRef:
    """Bind ``name`` to a Z3 constant of the declared sort (``int`` / ``real`` / ``bool``)."""
    if sort not in SORTS:
        raise ValueError(f"unknown sort {sort!r} (allowed: {sorted(SORTS)})")
    if name in RESERVED_NAMES:
        raise ValueError(
            f"variable name {name!r} is reserved for the formula language "
            f"(connectives / True / False / quantifiers)"
        )
    if sort == "int":
        return z3.Int(name)
    if sort == "bool":
        return z3.Bool(name)
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


def _contains(node: ast.AST, types: type | tuple[type, ...]) -> bool:
    return any(isinstance(child, types) for child in ast.walk(node))


def _parse_formula_ast(text: str) -> ast.Expression:
    """Parse ``text`` as an eval-expression and reject anything off the formula allow-list."""
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"could not parse {text!r}: {exc}") from exc

    nodes = list(ast.walk(tree))
    if len(nodes) > _MAX_FORMULA_AST_NODES:
        raise ValueError("formula is too complex")
    for node in nodes:
        if type(node) not in _ALLOWED_FORMULA_AST:
            raise ValueError(
                f"unsupported syntax ({type(node).__name__}) — only arithmetic, "
                "relations, and And/Or/Not/Implies/Xor/Equivalent are permitted"
            )
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise ValueError(f"name {node.id!r} is not allowed")
        if isinstance(node, ast.Call):
            if node.keywords:
                raise ValueError("keyword arguments are not allowed")
            if not isinstance(node.func, ast.Name):
                raise ValueError("only direct calls to named connectives are allowed")
            if node.func.id in _BANNED_FUNCS:
                raise ValueError(
                    f"{node.func.id} is out of scope for 0.38.0 — quantifiers / If stay later"
                )
            if node.func.id not in _CONNECTIVE_FUNCS:
                raise ValueError(
                    f"unsupported function {node.func.id!r} — only "
                    "And, Or, Not, Implies, Xor, Equivalent (Iff) are allowed"
                )
        if isinstance(node, ast.Constant) and not isinstance(node.value, int | bool):
            # bool is a subclass of int — accepted above. floats / strings / None / complex go here.
            if isinstance(node.value, float):
                raise ValueError(
                    "float literals are not allowed — use exact rationals (e.g. 1/2), "
                    "never decimals"
                )
            raise ValueError("only integer and boolean literals are allowed")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow | ast.BitXor):
            exponent = node.right
            if (
                isinstance(exponent, ast.Constant)
                and isinstance(exponent.value, int)
                and not isinstance(exponent.value, bool)
                and abs(exponent.value) > _MAX_POW_EXPONENT
            ):
                raise ValueError(f"exponent too large (> {_MAX_POW_EXPONENT})")
            if _contains(exponent, ast.Pow | ast.BitXor) and not _contains(exponent, ast.Name):
                raise ValueError("exponent is a numeric power tower (too large to evaluate)")
    return tree


def _is_bool_root(node: ast.AST) -> bool:
    """Whether ``node`` is shaped like a boolean formula (not a bare arithmetic expression)."""
    if isinstance(node, ast.Compare | ast.BoolOp):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return True
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _CONNECTIVE_FUNCS
    ):
        return True
    if isinstance(node, ast.Name):
        return True
    return isinstance(node, ast.Constant) and isinstance(node.value, bool)


def assert_formula_shape(text: str) -> None:
    """Raise unless ``text`` is a relation or a boolean formula — not bare arithmetic.

    The cheap validation-time gate. Full sort checking still happens in ``formula_to_z3``.
    """
    tree = _parse_formula_ast(text)
    if not _is_bool_root(tree.body):
        raise ValueError(
            "must be a relation or boolean formula "
            "(And/Or/Not/Implies/Xor/Equivalent), not a bare arithmetic expression"
        )


def _sort_of(expr: z3.ExprRef) -> z3.SortRef:
    return expr.sort()


def _is_bool_expr(expr: z3.ExprRef) -> bool:
    return _sort_of(expr) == z3.BoolSort()


def _is_arith_expr(expr: z3.ExprRef) -> bool:
    return _sort_of(expr) in {z3.IntSort(), z3.RealSort()}


def _require_bool(expr: z3.ExprRef, where: str) -> z3.BoolRef:
    if not _is_bool_expr(expr):
        raise ValueError(f"{where} must be boolean, got sort {_sort_of(expr)}")
    return expr  # type: ignore[return-value]


def _require_arith(expr: z3.ExprRef, where: str) -> z3.ExprRef:
    if not _is_arith_expr(expr):
        raise ValueError(f"{where} must be int or real, got sort {_sort_of(expr)}")
    return expr


def _lookup(name: str, env: dict[str, z3.ExprRef]) -> z3.ExprRef:
    if name not in env:
        raise ValueError(f"undeclared variable {name!r}")
    return env[name]


def _arith_ast_to_z3(node: ast.AST, env: dict[str, z3.ExprRef]) -> z3.ExprRef:
    """Translate an arithmetic AST subtree to Z3. Bool-sorted leaves raise."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, int):
            raise ValueError("arithmetic term expected an integer or rational, not a boolean")
        return z3.IntVal(node.value)

    if isinstance(node, ast.Name):
        if node.id in {"True", "False"}:
            raise ValueError(f"{node.id} is boolean — not allowed in arithmetic")
        expr = _lookup(node.id, env)
        return _require_arith(expr, node.id)

    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.UAdd):
            return _arith_ast_to_z3(node.operand, env)
        if isinstance(node.op, ast.USub):
            return -_arith_ast_to_z3(node.operand, env)
        raise ValueError("only unary +/− are allowed in arithmetic")

    if isinstance(node, ast.BinOp):
        left = _arith_ast_to_z3(node.left, env)
        if isinstance(node.op, ast.Pow | ast.BitXor):
            if not (
                isinstance(node.right, ast.Constant)
                and isinstance(node.right.value, int)
                and not isinstance(node.right.value, bool)
            ):
                raise ValueError(
                    "exponent must be a non-negative integer constant "
                    f"(got {ast.dump(node.right, annotate_fields=False)})"
                )
            exp_n = int(node.right.value)
            if exp_n < 0:
                raise ValueError(f"negative exponents are not allowed in v1 (got **{exp_n})")
            return left**exp_n
        right = _arith_ast_to_z3(node.right, env)
        left, right = _align_sorts(left, right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            # Exact rational division — promote ints so 1/2 is Real, matching the SymPy path.
            if left.sort() == z3.IntSort():
                left = z3.ToReal(left)
            if right.sort() == z3.IntSort():
                right = z3.ToReal(right)
            return left / right
        raise ValueError(f"unsupported arithmetic operator {type(node.op).__name__}")

    raise ValueError(
        f"unsupported arithmetic node {type(node).__name__} — only integer/rational "
        "literals, declared int/real symbols, +, -, *, /, and non-negative integer powers"
    )


def _bool_shaped(node: ast.AST, env: dict[str, z3.ExprRef]) -> bool:
    """Conservative: True when the node must be read as boolean."""
    if isinstance(node, ast.Compare | ast.BoolOp):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return True
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _CONNECTIVE_FUNCS
    ):
        return True
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return True
    if isinstance(node, ast.Name):
        if node.id in {"True", "False"}:
            return True
        if node.id in env:
            return _is_bool_expr(env[node.id])
    return False


def _formula_ast_to_z3(node: ast.AST, env: dict[str, z3.ExprRef]) -> z3.BoolRef:
    """Translate a boolean AST subtree to a Z3 boolean."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return z3.BoolVal(node.value)
        raise ValueError("a bare integer is not a boolean formula")

    if isinstance(node, ast.Name):
        if node.id == "True":
            return z3.BoolVal(True)
        if node.id == "False":
            return z3.BoolVal(False)
        expr = _lookup(node.id, env)
        return _require_bool(expr, node.id)

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return z3.Not(_formula_ast_to_z3(node.operand, env))

    if isinstance(node, ast.BoolOp):
        args = [_formula_ast_to_z3(elt, env) for elt in node.values]
        if not args:
            raise ValueError("boolean connective needs at least one argument")
        if isinstance(node.op, ast.And):
            return z3.And(*args)
        if isinstance(node.op, ast.Or):
            return z3.Or(*args)
        raise ValueError(f"unsupported boolean operator {type(node.op).__name__}")

    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        name = node.func.id
        args = [_formula_ast_to_z3(arg, env) for arg in node.args]
        if name == "And":
            if len(args) < 1:
                raise ValueError("And needs at least one argument")
            return z3.And(*args)
        if name == "Or":
            if len(args) < 1:
                raise ValueError("Or needs at least one argument")
            return z3.Or(*args)
        if name == "Not":
            if len(args) != 1:
                raise ValueError("Not takes exactly one argument")
            return z3.Not(args[0])
        if name == "Implies":
            if len(args) != 2:
                raise ValueError("Implies takes exactly two arguments")
            return z3.Implies(args[0], args[1])
        if name == "Xor":
            if len(args) != 2:
                raise ValueError("Xor takes exactly two arguments")
            return z3.Xor(args[0], args[1])
        if name in {"Equivalent", "Iff"}:
            if len(args) != 2:
                raise ValueError(f"{name} takes exactly two arguments")
            return args[0] == args[1]
        raise ValueError(f"unsupported function {name!r}")

    if isinstance(node, ast.Compare):
        return _compare_ast_to_z3(node, env)

    raise ValueError(
        f"unsupported formula node {type(node).__name__} — only relations, bool variables, "
        "and And/Or/Not/Implies/Xor/Equivalent are allowed"
    )


def _compare_ast_to_z3(node: ast.Compare, env: dict[str, z3.ExprRef]) -> z3.BoolRef:
    """Translate a (possibly chained) comparison. ``==`` / ``!=`` accept bool or arithmetic."""
    operands = [node.left, *node.comparators]
    parts: list[z3.BoolRef] = []
    for left_node, op_node, right_node in zip(
        operands[:-1], node.ops, operands[1:], strict=True
    ):
        op = _COMPARE_OPS.get(type(op_node))
        if op is None:
            raise ValueError(f"unsupported comparison {type(op_node).__name__}")
        left_bool = _bool_shaped(left_node, env)
        right_bool = _bool_shaped(right_node, env)
        if left_bool or right_bool:
            if op not in {"==", "!="}:
                raise ValueError(f"boolean values cannot be ordered with {op!r}")
            left = _formula_ast_to_z3(left_node, env)
            right = _formula_ast_to_z3(right_node, env)
        else:
            left = _arith_ast_to_z3(left_node, env)
            right = _arith_ast_to_z3(right_node, env)
            left, right = _align_sorts(left, right)
            if op in {"<", "<=", ">", ">="}:
                _require_arith(left, "comparison operand")
                _require_arith(right, "comparison operand")
        parts.append(_OP_TO_Z3[op](left, right))
    if len(parts) == 1:
        return parts[0]
    return z3.And(*parts)


def formula_to_z3(text: str, env: dict[str, z3.ExprRef]) -> z3.BoolRef:
    """Parse a quantifier-free boolean formula and translate it to Z3.

    Accepts a top-level relation (``x + y > 0``), a connective tree
    (``Implies(And(P, Q), P)``), Python ``and`` / ``or`` / ``not``, a declared
    bool variable, or ``True`` / ``False``. No ``eval``, no ``parse_expr``.
    """
    tree = _parse_formula_ast(text)
    if not _is_bool_root(tree.body):
        raise ValueError(
            "must be a relation or boolean formula "
            "(And/Or/Not/Implies/Xor/Equivalent), not a bare arithmetic expression"
        )
    return _formula_ast_to_z3(tree.body, env)


def _arith_ast_to_latex(node: ast.AST) -> str:
    if isinstance(node, ast.Constant):
        return str(node.value)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return f"-{_arith_ast_to_latex(node.operand)}"
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd):
        return _arith_ast_to_latex(node.operand)
    if isinstance(node, ast.BinOp):
        left = _arith_ast_to_latex(node.left)
        right = _arith_ast_to_latex(node.right)
        if isinstance(node.op, ast.Add):
            return f"{left} + {right}"
        if isinstance(node.op, ast.Sub):
            return f"{left} - {right}"
        if isinstance(node.op, ast.Mult):
            return f"{left} \\cdot {right}"
        if isinstance(node.op, ast.Div):
            return rf"\frac{{{left}}}{{{right}}}"
        if isinstance(node.op, ast.Pow | ast.BitXor):
            return f"{left}^{{{right}}}"
    return ast.dump(node, annotate_fields=False)


def _formula_ast_to_latex(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return r"\top" if node.value else r"\bot"
    if isinstance(node, ast.Name):
        if node.id == "True":
            return r"\top"
        if node.id == "False":
            return r"\bot"
        return node.id
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return rf"\neg {_formula_ast_to_latex(node.operand)}"
    if isinstance(node, ast.BoolOp):
        op = r"\land" if isinstance(node.op, ast.And) else r"\lor"
        return f" {op} ".join(f"({_formula_ast_to_latex(v)})" for v in node.values)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        op = _CONNECTIVE_LATEX.get(node.func.id, node.func.id)
        rendered = [_formula_ast_to_latex(arg) for arg in node.args]
        if node.func.id == "Not" and len(rendered) == 1:
            return rf"{op} {rendered[0]}"
        return f" {op} ".join(f"({part})" for part in rendered)
    if isinstance(node, ast.Compare):
        pieces = [_arith_or_bool_latex(node.left)]
        for op_node, rhs in zip(node.ops, node.comparators, strict=True):
            op = _COMPARE_OPS.get(type(op_node), "?")
            pieces.append(_COMPARE_LATEX.get(op, op))
            pieces.append(_arith_or_bool_latex(rhs))
        return " ".join(pieces)
    return _arith_ast_to_latex(node)


def _arith_or_bool_latex(node: ast.AST) -> str:
    if _is_bool_root(node) and not isinstance(node, ast.Name):
        return _formula_ast_to_latex(node)
    if isinstance(node, ast.Name):
        return node.id
    return _arith_ast_to_latex(node)


def formula_to_latex(text: str) -> str | None:
    """Presentation-only LaTeX for a formula. ``None`` when conversion fails."""
    try:
        tree = _parse_formula_ast(text)
        return _formula_ast_to_latex(tree.body)
    except Exception:  # noqa: BLE001 — presentation-only; the source string remains authoritative
        return None


def _render_model_value(val: z3.ExprRef) -> str:
    """Render a Z3 model value as an exact string (int, ``p/q``, or ``true``/``false``)."""
    if val.sort() == z3.BoolSort():
        if z3.is_true(val):
            return "true"
        if z3.is_false(val):
            return "false"
        return val.sexpr() if hasattr(val, "sexpr") else str(val)
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


@dataclass(frozen=True)
class SatisfyOutcome:
    """Result of a one-stage model-finding check (``z3.satisfy``)."""

    kind: Literal["sat", "unsat", "undecided"]
    model: dict[str, str] | None = None
    reason: str | None = None
    certificate: str | None = None
    used_constraints: list[str] | None = None


def satisfy(
    constraints: list[tuple[str, z3.BoolRef]],
    *,
    env: dict[str, z3.ExprRef],
    timeout_ms: int,
) -> SatisfyOutcome:
    """One-stage check: is there a model of ``constraints``?

    ``constraints`` are ``(track_name, formula)`` pairs — track names appear in the unsat-core
    when the set is unsatisfiable, so a reader sees which constraints actually conflict.

    Unlike :func:`solve`, there is no vacuous-hypotheses guard and no negated goal. ``unsat``
    here means *no model exists* (honest ``refuted``), not a proof of a universal. ``unknown``
    / timeout stays ``undecided`` — never a fabricated assignment.
    """
    if timeout_ms < 1:
        raise ValueError("timeout_ms must be >= 1")

    solver = z3.Solver()
    solver.set("timeout", timeout_ms)
    for name, formula in constraints:
        solver.assert_and_track(formula, name)
    check = solver.check()

    if check == z3.sat:
        model = solver.model()
        return SatisfyOutcome(kind="sat", model=render_model(model, env))

    if check == z3.unsat:
        core = solver.unsat_core()
        used = sorted({str(c) for c in core})
        return SatisfyOutcome(
            kind="unsat",
            certificate="unsat",
            used_constraints=used or None,
        )

    return SatisfyOutcome(kind="undecided", reason=_reason_unknown(solver))


def symbol_flags_for(variables: dict[str, str]) -> dict[str, dict[str, bool]]:
    """SymPy parse flags for declared variables (int → integer, real → real).

    ``bool`` variables are omitted — they are not arithmetic symbols and are not
    fed through the shared SymPy parser.
    """
    out: dict[str, dict[str, bool]] = {}
    for name, sort in variables.items():
        if sort == "int":
            out[name] = {"integer": True}
        elif sort == "real":
            out[name] = {"real": True}
        elif sort == "bool":
            continue
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
Z3SortName = Literal["int", "real", "bool"]
