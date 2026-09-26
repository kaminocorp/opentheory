# 0.35.0 — `interval.eval` (proven enclosures)

**Goal.** Ship the Calculate-bench stretch originally listed as optional
`0.10.6+` in `docs/plans/maths-toolbox.md` / `roadmap-next-steps.md`.
The old falsify-and-render-0.10 appendix B is gone; this line re-specs
from those docs. An interval is a **proven enclosure**, not a float
dressed as exact, and it must never stamp Grade A by itself.

**Shape.** One human-first instrument on the existing spine:
`interval.eval`. Same `Instrument` protocol, code registry, conformance
harness, `run_instrument` → `create_checkpoint` chokepoint, sandbox
dispatch, Instruments drive/show UI. Sits on shipped `0.34.0`
(`a7cd946`, #19 squash-merged). On `main` as `1ca7116` (#20 squash).
**No schema, no migration** —
`Artifact.kind` already holds `derivation` / `counterexample`.

`formula.render` is **not** reintroduced.

## What shipped

- **`interval.eval`.** Closed-form real expression → proven `[lo, hi]`.
  Optional `precision_bits` (default 64, 16–1024). Engine is
  **python-flint / Arb** when the locked wheel imports; **mpmath.iv**
  (already a SymPy dependency) if the C extension fails; both missing
  → honest `undecided`. Soft timeout under the subprocess wall, same
  pattern as Z3 / Lean.
- **Honest outcomes.**
  - Successful enclosure → `result`, `artifact_kind="derivation"`,
    bounds as exact int / `p/q` or directed decimals, plus
    `precision_bits` + `method`. Blame tuple records tool / version /
    inputs.
  - Cannot enclose / timeout / free symbols / non-real / unsupported →
    `undecided`. Never a fabricated bound.
  - A relation the enclosure *definitively* falsifies (interval
    entirely off the claimed value) → `refuted`,
    `artifact_kind="counterexample"`. Overlap of a claimed equality is
    `undecided` / `overlap` — not a pretended certainty.
- **Exact / enclosure honesty.** Float literals are a 422 (mint
  nothing). No Python `float` in the payload. An exact rational
  (`1/3+1/6`) is a singleton `1/2`.
- **Grade matrix.**
  - `result` → **C** (numeric-with-bound; not exact symbolic B, not
    kernel/SMT A).
  - `refuted` → **B** (proven miss of that relation).
  - `undecided` → `None`.
  Never Grade A from an interval alone.
- **Frontend.** Quiet drive form (expression + working precision).
  Result card labelled *Enclosure · proven bound* — not a proof badge.
  Assumptions gated off.

## What did not change

- `z3.prove` / `z3.satisfy` / `lean.prove` / Bench 6 contracts.
- Campaigns, orchestrator, budget metering.
- Funder ≠ contributor ≠ validator. Account ≠ Actor.
- No Alembic revision.

## Honest caveats

- **An enclosure is not a proof.** Grade C on a supporting run is
  load-bearing. Point `z3.prove` / `lean.prove` at a goal for Grade A.
- **`sqrt(2) == sqrt(2)` is undecided.** Two inexact balls of the same
  irrational overlap; the instrument will not pretend they are equal.
  Exact singleton match (`2+2 == 4`) may `result`.
- **High precision makes nearby rationals refute.** A 15-digit
  truncation of √2 is *outside* a 64-bit Arb ball, so
  `sqrt(2) == 141421356237309/10^14` is an honest `refuted`, not
  overlap. That is the enclosure working.
- **python-flint is required in the lockfile** (~10 MiB manylinux
  wheel — smaller than `z3-solver`). If the extension fails to import
  at runtime, mpmath.iv is the fallback; if that fails too, the
  instrument still conforms and returns `undecided`. CI does not need
  a huge image.
- **v1 rejects assumptions** and free symbols (undecided). No
  boolean-connective parser.
- **No browser eyeball** of the Instruments walk in this environment.

## Tests

- Unit (no DB): conformance; √2 enclosure (no float); exact `1/2`
  singleton; `pi > 3` holds; `sqrt(2) == 2` refutes; `sqrt(2) == sqrt(2)`
  overlaps → undecided; free symbols / `sqrt(-1)` undecided; timeout
  budget 0; float literal / injection / assumptions raise; precision
  bounds; killable-subprocess round-trip.
- Write-path (DB-gated): enclosure lands `derivation` with the engine
  pin; `sqrt(2) == 2` weakens a linked claim as `counterexample`.
- Grade / planner: matrix cells; `interval.eval` is on
  `raise_path(None)` / `raise_path(C)` and not on `raise_path(B)` or
  the A-path.

## Verification

- `ruff check .` clean.
- Default pytest (no `TEST_DATABASE_URL`): **626 passed, 211 skipped**.
  Includes √2 enclosure (no float), exact `1/2` singleton, `pi > 3`,
  `sqrt(2) == 2` refute, `sqrt(2) == sqrt(2)` overlap → undecided,
  free symbols / `sqrt(-1)` / timeout, float-literal reject,
  killable-subprocess round-trip, grade-matrix / planner raise path,
  and the existing `0.33.0` / `0.34.0` suites.
- Write-path `interval.eval` `run_instrument` tests are written and
  skip without Postgres.
- Frontend `typecheck` / `lint` / `build` clean (9/9 static pages).
  `npm test` **29 passed**.

## Unverified

- DB-gated write-path tests skip without Postgres.
- No pixel-level browser walk of the Instruments drive/show surfaces.
- No live Instruments walk against opentheory.vercel.app.
