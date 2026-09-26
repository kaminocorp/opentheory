# 0.38.0 — Boolean connectives for `z3.prove` / `z3.satisfy`

**Goal.** After shipped `0.33.0` `z3.satisfy` (`e3a07ea`) and shipped
`0.36.0` blame (`71a8929`, on `main`), the remaining cheap verifier-wave
follow-on is propositional structure. `split_relation` could only see a
single top-level `lhs OP rhs`. Agents and humans could not prove
`(P ∧ Q) → P` or satisfy `And(P, Q)`. Ship a closed allow-list of
boolean connectives and a `bool` sort through the existing instruments —
no parallel language, no `eval`, no false-proof path.

**Shape.** Same InputModel (`variables` + `constraints` + `goal`). Same
sandbox / wall-clock / soft-timeout. Same two-stage validity check
(vacuous-hypotheses guard still applies). A dedicated formula AST walker
in `_z3_support` — **not** a widening of the shared SymPy
`_reject_unsafe_source` gate. Sits on shipped `0.36.0`. **No schema, no
migration.** Independent of unmerged `0.36.1` / `0.36.2` / `0.37.0`.

## What shipped

- **`bool` sort.** `declare("P", "bool")` → `z3.Bool`. Models render
  `true` / `false` (exact strings, never a float). Reserved names
  (`And`, `Or`, `Not`, `Implies`, `Xor`, `Equivalent`, `Iff`, `True`,
  `False`, `ForAll`, `Exists`, …) cannot be declared as variables.
- **Closed connective allow-list.** `And`, `Or`, `Not`, `Implies`,
  `Xor`, `Equivalent` (`Iff` alias). Python `and` / `or` / `not` are
  accepted as the same operators. Chained comparisons (`0 < x < 1`)
  become a conjunction. Bare bool variables and `True` / `False` are
  formulas. Relational atoms still work (`x + y > 0`).
- **Dedicated formula parser.** AST allow-list walk, no `parse_expr`,
  no `eval`. Arithmetic leaves translate to Z3 directly. `sin`,
  attributes, subscripts, floats, and injection stay 422.
- **Honest outcomes unchanged.** `result | refuted | undecided`.
  Grade A / `proven` only on a real Z3 `unsat` of `H ∧ ¬goal` after the
  vacuous guard. `And(P, Not(P))` as a hypothesis is
  `contradictory_hypotheses`, never a proof of `False`. Timeout /
  `unknown` stays `undecided`.
- **Frontend.** `bool` on the sort dropdown; hints mention a relation
  *or* a boolean formula. Result cards already show `name=value` chips
  (`P=true`). No new chrome.
- **Write path.** Only through `run_instrument` → `create_checkpoint`.

## What did not change

- Vacuous-hypotheses guard, timeout→undecided, proof / counter-model /
  model / unsat contract.
- Shared SymPy parser used by `calc.eval` and the rest.
- `lean.prove`, campaigns, orchestrator, budget metering.
- Funder ≠ contributor ≠ validator. Account ≠ Actor.
- No Alembic revision.

## Honest caveats

- **Quantifiers are out of scope.** `ForAll` / `Exists` / `If` raise
  (422, mint nothing). That is later, not a silent skip.
- **No free-form Python.** The formula language is the closed
  connective set plus arithmetic / relations. `eval` is never called.
- **A sat model is still existence, not a universal proof.** Point
  `z3.prove` at a goal for validity.
- **Nonlinear terms may honestly return `undecided`.** Same as 0.13.x.
- Lean REPL / LeanDojo remain later.
- Does **not** claim `0.36.1` / `0.36.2` / `0.37.0` as shipped.

## Tests

- Unit (no DB): `(P ∧ Q) → P` proves; `Implies(P and Q, P)` proves;
  modus ponens; excluded middle; Xor / Equivalent; mixed
  `Implies(And(x > 0, y > 0), x + y > 0)`; chained `0 < x < 1`;
  `False` / bare `P` refute with `true`/`false` witnesses; vacuous
  `And(P, Not(P))` is undecided never a proof; satisfy `And(P, Q)` /
  `And(P, Not(P))` / mixed bool+real; quantifier / If / reserved
  names / int-as-formula / bool-ordered / injection / attribute /
  float-inside-And / `sin` all raise; 0.13.x arithmetic proof
  regression; killable-subprocess round-trip of the tautology.
- Existing `z3.prove` / `z3.satisfy` suites (relations, timeout
  honesty, vacuous guard, engine pin).
- Write-path (DB-gated): boolean tautology lands a `proof`;
  `And(P, Not(P))` unsat weakens as `proof` / no model.
- Grade matrix unchanged (`result` / `refuted` stay A).

## Verification

- `ruff check .` clean.
- Default pytest (no `TEST_DATABASE_URL`): **665 passed, 222 skipped**.
  Includes `(P ∧ Q) → P`, Python `and`/`or`/`not`, modus ponens,
  excluded middle, mixed arithmetic+bool, chained comparison, vacuous
  `And(P, Not(P))` never a proof, sat/unsat bool models, quantifier /
  If / injection / float / `sin` rejects, 0.13.x arithmetic regression,
  killable-subprocess tautology, and the existing `z3.prove` /
  `z3.satisfy` suites.
- Write-path boolean `run_instrument` tests are written and skip
  without Postgres.
- Frontend `typecheck` / `lint` / `build` clean (9/9 static pages).
  `npm test` **35 passed**.

## Unverified

- DB-gated write-path tests skip without `TEST_DATABASE_URL`.
- No pixel-level browser walk of the Instruments drive form (no
  signed-in session against a live backend in this environment).
