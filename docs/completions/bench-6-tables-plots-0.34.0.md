# 0.34.0 — Bench 6 tables & plots

**Goal.** After shipped `0.33.0` `z3.satisfy` (`e3a07ea`), ship the agreed Bench 6
*See & record* instruments so a researcher can build a falsification grid and
(optionally) look at a curve — without treating a picture as a proof.

**Shape.** Five human-first instruments on the existing spine: `table.create`,
`table.derive_column`, `table.render`, `plot.function`, `plot.points`. Same
`Instrument` protocol, code registry, conformance harness, `run_instrument` →
`create_checkpoint` chokepoint, sandbox dispatch, Instruments drive/show UI.
Sits on `0.33.0`. **No schema, no migration** — `Artifact.kind` is already a
free-form `String(80)`; `table` and `plot` fit.

`formula.render` is **not** reintroduced. KaTeX + `*_latex` already covers it.

## What shipped

- **`table.create`.** Typed rows/columns → a `table` artifact. Cells are exact
  integers / rationals / expressions, or opaque labels. A JSON float or a
  decimal token (`0.5`) is a 422 (mint nothing) — no silent promotion.
- **`table.derive_column`.** Add a computed column. This is compute, not
  display. Exact substitution, same honesty as `calc.eval`. A relation that
  fails on a row is `refuted` + `artifact_kind="counterexample"` with a
  witness row. Every row holding is `result` (finite support). A row that
  cannot be settled is `undecided` unless another row already refuted.
  Extra label columns that the expression does not name pass through.
- **`table.render`.** Same exact-cell table plus a markdown serialization the
  workspace can show. Display only.
- **`plot.function`.** `y = f(x)` over a closed domain → Vega-Lite v5 spec
  (not a raster) plus the sampled points. Numeric, `approximate: true`.
  Fewer than two real samples → honest `undecided`, never a fabricated curve.
- **`plot.points`.** Scatter / line from computed points → Vega-Lite spec.
- **Grade matrix (honest).**
  - `table.create` / `table.render` / `plot.*`: `None` on every cell.
    A container, a rendering, or a picture is not evidence.
  - `table.derive_column`: `result` → **C** (finite exact support),
    `refuted` → **B** (exact witness), `undecided` → `None`.
- **Frontend.** Quiet Instruments drive forms (sentence case, no AI chrome)
  and result cards: HTML table; SVG from the recorded points; plots captioned
  *Visualization only — not evidence.* Assumptions stay on `table.create`,
  `table.derive_column`, and `plot.function`; gated off for `table.render`
  and `plot.points`.

## What did not change

- `z3.prove` / `z3.satisfy` / `lean.prove` contracts.
- Campaigns, orchestrator, budget metering.
- Funder ≠ contributor ≠ validator. Account ≠ Actor.
- No Alembic revision.

## Honest caveats

- **A plot is optional viz.** Tables are the primary falsification grid.
  Never treat a Vega-Lite spec as Grade-A evidence.
- **A value-only derived column** (no relation) still scores `result` / C if
  pointed at a claim — that is finite compute, not a check. Prefer a relation
  (`d == a + b`) when the run is meant as evidence.
- **Every row holding is not a proof** of a universal. Same honesty as
  `counterexample.search` "none found".
- **Inline tables only.** Instruments do not fetch a prior `table.create`
  artifact by id — the caller supplies columns + rows. Same typed-input
  contract as the rest of the bench.
- **No `formula.render`.** Still covered by `*_latex` + KaTeX.
- **No browser eyeball** of the Instruments walk in this environment.

## Tests

- Unit (no DB): conformance; exact-cell canonicalize (`2/4` → `1/2`);
  reject JSON float and `0.5`; label pass-through; derive `a**2+b**2`;
  Pythagoras holds; `d == a+b` refutes on 3-4-5 with a witness; mixed
  false+undecided is refuted; empty table cannot derive; render markdown;
  `y=x²` Vega-Lite spec; `sqrt(x)` on a negative domain is undecided;
  plot points from exact strings; killable-subprocess round-trips.
- Write-path (DB-gated): `table.create` lands `table`; derive-column
  refute weakens a linked claim as `counterexample`; `plot.function`
  lands `plot` with `approximate: true`.
- Grade / planner: matrix cells; `table.derive_column` is on
  `raise_path(None)` / `raise_path(C)` and not on `raise_path(B)`;
  create / render / plots never appear on a raise path.

## Verification

- `ruff check .` clean.
- Default pytest (no `TEST_DATABASE_URL`): **602 passed, 209 skipped**.
  Includes exact-cell canonicalize / float reject, derive-column
  Pythagoras / sum-of-legs witness, plot Vega-Lite spec, negative-domain
  undecided, killable-subprocess round-trips, grade-matrix / planner
  raise path, and the existing `z3.satisfy` suite.
- Write-path `table.create` / derive-column refute / `plot.function`
  `run_instrument` tests are written and skip without Postgres.
- Frontend `typecheck` / `lint` / `build` clean (9/9 static pages).
  `npm test` **29 passed**.

## Unverified

- DB-gated write-path tests skip without `TEST_DATABASE_URL`.
- No pixel-level browser walk of the Instruments drive/show surfaces.
- No live Instruments walk against opentheory.vercel.app.
