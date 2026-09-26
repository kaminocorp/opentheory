# 0.39.0 — First-order quantifiers for `z3.prove` / `z3.satisfy`

**Goal.** After shipped `0.38.0` boolean connectives (`e0e118b`, #28)
on current `main`, the remaining cheap verifier-wave follow-on is
first-order structure. The 0.38.0 walker rejected `ForAll` / `Exists`
on purpose. Agents and humans could not prove `∀x. x + 0 = x` or
satisfy `Exists(x, And(x > 1, x < 3))` as quantified sentences. Ship
those two binders through the existing instruments — no parallel
language, no `eval`, no false-proof path, no sandbox widening.

**Shape.** Same InputModel (`variables` + `constraints` + `goal`).
Same sandbox / wall-clock / soft-timeout. Same two-stage validity
check (vacuous-hypotheses guard still applies). The dedicated formula
AST walker in `_z3_support` grows `ForAll` / `Exists` as named
calls — **not** a widening of the shared SymPy `_reject_unsafe_source`
gate, and **not** `ast.List` / `ast.Lambda` binders.
**No schema, no migration.**

## What shipped

- **`ForAll` / `Exists`.** Binders are declared `Name`s; sort comes
  from `variables`. `ForAll(x, body)`, `Exists(x, body)`, multi-binder
  `ForAll(x, y, body)`, and nesting are in. Models of declared names
  stay exact strings (`true` / `false` / int / `p/q`).
- **Still reserved.** `ForAll` / `Exists` cannot be declared as
  variable names (already reserved in 0.38.0). `If` / `Quantifier` /
  `Forall` stay rejected.
- **Dedicated formula parser, same security model.** AST allow-list
  walk, no `parse_expr`, no `eval`. No new node types for binders.
  `sin`, attributes, subscripts, floats, list binders, and injection
  stay 422.
- **Honest outcomes unchanged.** `result | refuted | undecided`.
  Grade A / `proven` only on a real Z3 `unsat` of `H ∧ ¬goal` after
  the vacuous guard. A false quantified hypothesis is
  `contradictory_hypotheses`, never a proof of `True`. Timeout /
  `unknown` stays `undecided`.
- **Frontend.** Hints mention ForAll/Exists. Result cards already
  show `name=value` chips. No new chrome.
- **Write path.** Only through `run_instrument` → `create_checkpoint`.

## What did not change

- Vacuous-hypotheses guard, timeout→undecided, proof / counter-model /
  model / unsat contract.
- Shared SymPy parser used by `calc.eval` and the rest.
- `lean.prove`, campaigns, orchestrator, budget metering.
- Funder ≠ contributor ≠ validator. Account ≠ Actor.
- Append-only ledger guards. No Alembic revision.

## Honest caveats

- **A closed quantified sentence is a sentence.** `Exists(x, x > 0)`
  as a satisfy constraint is sat because the sentence is true; the
  rendered `x` is a declared-constant completion, not a skolem
  witness extracted from the binder. Use a free constraint
  (`x > 0`) when the assignment *is* the point.
- **`If` / ite stay out.** That is later, not a silent skip.
- **Nonlinear / alternating fragments may honestly return
  `undecided`.** Same as 0.13.x / 0.38.0.
- Lean REPL / LeanDojo remain later.

## Tests

- Unit (no DB): `ForAll(x, x + 0 == x)` proves; successor
  `ForAll(x, Exists(y, y == x + 1))`; positive-successor implication;
  bool `ForAll(P, Or(P, Not(P)))`; multi-binder commutativity;
  `ForAll(x, x > 0)` / `Exists(x, ForAll(y, y > x))` / contradictory
  `Exists` refute; vacuous `ForAll(x, And(x > 0, x < 0))` is
  undecided never a proof; satisfy `Exists` sat / unsat / true
  `ForAll(x, x*x >= 0)`; mixed free+bound; quantified nonlinear
  timeout honesty; `If` / list binder / non-name binder / missing
  body / undeclared / duplicate / injection reject; 0.38.0 and-elim
  and 0.13.x arithmetic regressions; killable-subprocess identity.
- Existing `z3.prove` / `z3.satisfy` / `z3.boolean` suites.
- Write-path (DB-gated): forall identity lands a `proof`;
  contradictory `Exists` unsat weakens as `proof` / no model.
  Helpers now use `tests/principals.py` so `_thread` is a member
  write (pre-existing 403 on `main` after `0.36.1`).

## Verification

- `ruff check .` clean.
- Default pytest (no `TEST_DATABASE_URL`): **722 passed, 227 skipped**.
  Includes `ForAll(x, x + 0 == x)`, successor `ForAll`/`Exists`, bool
  `ForAll(P, Or(P, Not(P)))`, multi-binder commutativity, `ForAll(x, x > 0)`
  / least-integer / contradictory `Exists` refutations, vacuous false
  `ForAll` never a proof, sat/unsat quantified models, `If` / list binder
  / injection rejects, 0.38.0 and-elim and 0.13.x arithmetic regressions,
  killable-subprocess identity, and the existing `z3.prove` /
  `z3.satisfy` / `z3.boolean` suites.
- Write-path quantifier `run_instrument` tests ran in CI.
- Frontend `typecheck` / `lint` / `build` clean (9/9 static pages).
  `npm test` **55 passed**.
- GitHub Actions CI on this branch: **945 passed, 4 skipped**
  (Postgres write-path included). Frontend job green. Vercel preview
  green.

## Unverified

- No pixel-level browser walk of the Instruments drive form (no
  signed-in session against a live backend in this environment).
