# 0.33.0 — `z3.satisfy` (model-finding)

**Goal.** `z3.prove` answers "is the goal entailed?" and returns a proof,
a counter-model, or honest `undecided`. The deferred verifier-wave
follow-on is the dual: **is there a model of these constraints?** Ship
that as a first-class instrument on the same spine — no new mint path,
no parser expansion, no migration.

**Shape.** Reuse `_z3_support` (`declare`, `relation_to_z3`, the closed
allow-list translator, `render_model`, soft-timeout). Add a one-stage
`satisfy` harness that asserts the constraints as-is. Register
`z3.satisfy` in the catalog. Quiet Instruments drive form + result
card. Sits on shipped `0.32.0`. **No schema, no migration.**

## What shipped

- **`z3.satisfy`.** Typed variables + top-level relational constraints.
  Same bounds as `z3.prove` (name regex, max 8 vars, max 16
  constraints, 500-char relations). Sync `run` → killable subprocess.
- **Honest outcomes.**
  - `sat` → `result`, `artifact_kind="model"`, exact assignment
    (ints / `p/q` strings, never a float).
  - `unsat` → `refuted`, `artifact_kind="proof"`, certificate `"unsat"`
    plus the unsat-core of named constraints. No fabricated model.
  - `unknown` / timeout → `undecided`, `artifact_kind="derivation"`,
    reason `timeout` or `incomplete`.
- **No vacuous-proof guard.** There is no goal. `unsat` *is* the honest
  no-model outcome — unlike `z3.prove`, where contradictory hypotheses
  must not count as a proof of an arbitrary goal.
- **Write path.** Only through `run_instrument`. Parse / undeclared /
  float / injection failures raise (422, mint nothing). A genuine
  `unknown` is a successful recorded run.
- **Grade matrix.** `result` and `refuted` are Grade A (SMT-backed
  existence / unsatisfiability). `undecided` is `None`. The planner
  raise path now names `lean.prove`, `z3.prove`, `z3.satisfy`.
- **Frontend.** Drive form (variables + constraints, sentence case).
  Result cards: model assignment, unsatisfiable / no model, undecided
  (warn, never a pass). Assumptions gated off.

## What did not change

- `z3.prove` — vacuous-hypotheses guard, timeout→undecided, proof /
  counter-model contract untouched.
- `lean.prove`, campaigns, orchestrator, budget metering.
- Funder ≠ contributor ≠ validator. Account ≠ Actor.
- No Alembic revision.

## Honest caveats

- **No boolean connectives.** Each constraint is still a single
  top-level relation via `split_relation`. In-string `And` / `Or` /
  `Not` / `Implies` and a `bool` sort need a parser beyond v1.
- **No quantifiers.** Free variables only. `∀` / `∃` stay later.
- **Nonlinear terms are permitted** and may honestly return
  `undecided`. That is not a 422 and not a fake model.
- **Empty constraints are trivially `sat`.** Any assignment of the
  declared sorts is a model; Z3 completes defaults. Recorded as a
  real `result`, not refused.
- **A sat model is existence, not a universal proof.** Grade A here
  means SMT-backed, same engine as `z3.prove`'s counter-model — it
  does not mean "the constraints hold for all assignments." Point
  `z3.prove` at a goal for validity.
- Lean REPL / LeanDojo remain later.

## Tests

- Unit (no DB): conformance; sat model (exact rationals, `x+y==1`);
  unsat (`x>0` ∧ `x<0`) never carries a model; empty constraints
  trivially sat; timeout/unknown honesty; translator safety (float,
  undeclared, injection, assumptions, blank / non-relational /
  bad names); killable-subprocess round-trip.
- Write-path (DB-gated): sat lands a `model` artifact with the Z3
  engine pin; unsat weakens a linked claim as `proof` / `weaken`,
  `model` is null.
- Grade / planner: matrix cells; `instruments_reaching(A)` and
  `raise_path(B)` include `z3.satisfy`; prompt / planner copy
  updated.
- `z3.prove` regression suite unchanged.

## Verification

Recorded in the PR after the verification pass.

## Unverified

- DB-gated write-path tests skip without `TEST_DATABASE_URL`.
- No pixel-level browser walk of the Instruments drive form (no
  signed-in session against a live backend in this environment).
