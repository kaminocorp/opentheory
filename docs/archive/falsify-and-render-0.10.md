# `0.10.x` — Falsify & Render (Toolbench Wave 2)

> **Status — completed (`0.10.5`, 2026-07-02).** All six phases shipped; see
> `docs/completions/falsify-render-phase-*.md` and `docs/changelog.md`. **What comes next:**
> `docs/executing/execution-sandbox-0.11.md` (then `0.12.x` agent loop per
> `docs/plans/roadmap-next-steps.md`).

> Extend the shipped toolbench (`0.9.1`–`0.9.9`) with the **next Tier-0 instruments and render
> surfaces** needed for the flagship math demo in `docs/plans/agent-research-tools.md` §5 — a theorem
> *emerging* from claim pressure, not asserted. This plan turns the agreed Bench 4 + Bench 6 slices
> from `docs/plans/maths-toolbox.md` into methodical, shippable phases on top of the existing
> provenance spine (`docs/completions/toolbench-provenance-and-first-instruments.md`).

## Prerequisite (closed)

The **`0.9.x` DB-backed ledger-invariant gate** is closed: the full backend suite (`229` tests) runs
green against a throwaway Postgres (`TEST_DATABASE_URL`). Re-run that gate before merging each
`0.10.x` slice if ledger-touching code changes.

## Goal

A human (later an agent on the same API) can:

1. **Falsify a universal claim cheaply** — run `counterexample.search` over a bounded integer grid,
   land a **definitive counterexample** on the ledger when one exists, or record an honest *weak-support*
   “none found in this search space” outcome when one does not.
2. **Read math results as math** — SymPy outputs surface as **KaTeX-typeset LaTeX** in the workspace
   (not raw `x**2` monospace strings), without changing the provenance record’s exact SymPy strings.

The acceptance bar for the whole line: walk **claims 1–4** of the flagship *measuring across a corner*
thread end-to-end from the workspace using only shipped instruments — geometry measure → supports,
`counterexample.search` on “sum of legs” → **refuted** with witness, results **readable** via KaTeX.
Claim 5 (Lean proof → Grade A) stays explicitly out of scope.

## Why this line is next (not agents yet)

`0.9.x` delivered the spine + four instruments + API + UI. What the product story still lacks:

| Gap | This line closes it |
|---|---|
| No programmatic *search* falsifier | `counterexample.search` — the Bench 4 anchor |
| Results show as SymPy strings | Additive `*_latex` fields + KaTeX in `Formula` |
| Flagship claim 2 (“`d = a + b`”) | Demo-default drive form finds `a=3, b=4, d=5 → 5 ≠ 7` |

Agents, execution sandbox, Z3/Lean, literature pin, plots/tables remain deferred (`0.11.x`+).

## Standing invariants (unchanged from `0.9.x`)

| Invariant | How this line honours it |
|---|---|
| One write path | New instruments compose through `services/tool_runs.py` → `create_checkpoint`; no new checkpoint mint paths. |
| Append-only | Blame tuple on `Checkpoint`; outputs hased from canonical JSON; corrections are new runs, never edits. |
| Three honest outcomes | `counterexample.search` uses `refuted` only when a witness is found; “none found” is `result` with explicit `samples_tried` + `search_space` — never “proven”. |
| Human-first | Drive/show surfaces ship before any agent drives the same `POST …/run` route. |
| No stamped grades | Exact vs approximate vs retrieved stays derivable from the instrument name; no new grade column. |

## Decisions (locked before implementation)

1. **`counterexample.search` is grid-first, integer-bounded, in-process.** v1 searches a Cartesian
   product of inclusive integer ranges (`min`/`max` per variable), capped by `max_samples` (hard ceiling).
   No random sampling, no floats, no Z3 — cheap and deterministic. Random/grid hybrid is deferred.
2. **“None found” is `result`, not `undecided`.** The instrument *ran* and completed the search;
   absence of a counterexample in the stated space is **weak support** (`maths-toolbox.md` Bench 4).
   The UI must never caption it as “proven” or “validated”.
3. **LaTeX is additive, not a replacement.** Output models keep exact SymPy strings for hashing and
   reproduction; optional `*_latex` companion fields are render hints only. The ledger’s content hash
   continues to use the non-LaTeX canonical output (no drift from presentation).
4. **KaTeX is frontend-only for v1.** The backend emits LaTeX strings via `sympy.latex()`; typesetting
   happens in `formula.tsx` (the Phase 7 seam). No server-side HTML render, no new `formula.render`
   instrument in `0.10.x` — that instrument is deferred unless a standalone “render this expr” run
   proves necessary during build.
5. **No schema migration.** Additive JSON on existing `Artifact`/`Checkpoint` outputs only; register
   the new instrument in code; export unchanged from `models/__init__.py`.
6. **Reuse `_sympy_support.parse` and the AST gate.** `counterexample.search` parses the relation and
   variable bindings through the same curated parser as `calc.eval` / `expr.compare` — no second parse
   path, no security regression.

## Out of scope (explicitly)

- **Agent loop**, Research crew execution, stage orchestration (`research-flow.md`).
- **Execution sandbox** (Fly microVM / resource cgroup) — `0.11.x`.
- **Z3 / Lean / `interval.eval`** — optional stretch; not required for the flagship claims 1–4.
- **`sample.grid`**, `pattern.find_relation`, `table.*`, `plot.*` (Vega-Lite).
- **Crossref / arXiv / OpenAlex** retrieval (Tier 1 wave 2).
- **Standalone `formula.render` instrument** — deferred (additive `*_latex` covers the UI need).
- **Object storage**, artifact upload, demo seeding.

---

## Provenance shapes (what Phases 1–2 add)

### `counterexample.search` I/O contract

```python
# app/toolbench/instruments/counterexample_search.py

class VariableRange(BaseModel):
    min: int = Field(ge=-1000, le=1000)
    max: int = Field(ge=-1000, le=1000)
    # model_validator: min <= max; (max - min + 1) bounded so the Cartesian product cannot explode silently

class CounterexampleSearchInput(BaseModel):
    relation: str = Field(min_length=1, max_length=500)
    # A top-level relational expression using ==, !=, <, <=, >, >= — same split semantics as calc.eval.
    variables: dict[str, VariableRange] = Field(min_length=1, max_length=8)
    max_samples: int = Field(default=500, ge=1, le=5000)

class CounterexampleSearchOutput(BaseModel):
    relation: str                      # echoed
    search_space: dict[str, str]     # e.g. {"a": "1..10", "b": "1..10", "d": "1..20"}
    samples_tried: int
    found: bool
    witness: dict[str, str] | None = None       # {"a": "3", "b": "4", "d": "5"} when found
    witness_relation: str | None = None         # concrete relation at witness, e.g. "5 == 7"
    witness_relation_latex: str | None = None   # Phase 4 additive field
```

**Outcome mapping:**

| Situation | `status` | `artifact_kind` | Default `relation_kind` (when targeting a claim) |
|---|---|---|---|
| Witness found (relation false at assignment) | `refuted` | `counterexample` | `weaken` |
| No witness in search space | `result` | `derivation` | `support` (weak — UI must qualify) |
| Parse / bound / sample cap error | — | — | Tool exception → `422`, nothing minted |

**Flagship witness (must be covered by tests):** relation `d == a + b`, ranges `a,b,d ∈ [1,10]`,
assignment `a=3, b=4, d=5` → `5 == 7` → `refuted`.

### LaTeX companion fields (Phase 4)

Additive optional strings on existing + new outputs. Naming convention: `<field>_latex` beside `<field>`.

| Instrument | New fields (examples) |
|---|---|
| `calc.eval` | `expression_latex`, `value_latex` |
| `expr.compare` | `left_latex`, `right_latex`, `difference_latex` |
| `geometry.coordinate_measure` | per-measurement `value_latex` in the measurements list (or a parallel list) |
| `counterexample.search` | `witness_relation_latex` |

Implementation: `to_latex(expr_or_str, assumptions) -> str | None` in `_sympy_support.py`; returns
`None` when latex conversion fails (frontend falls back to monospace SymPy string).

---

## Phase 1 — `counterexample.search` backend instrument

**Goal:** register a fifth Tier-0 instrument; conformance + DB-free behavioural tests green.

**Tasks**

1. **`app/toolbench/instruments/counterexample_search.py` (new)**
   - `CounterexampleSearch` class satisfying `Instrument` protocol; `name = "counterexample.search"`,
     `version = "0.1.0"`, `engine`/`engine_version` from `_sympy_support`.
   - **Relation parsing:** reuse `_split_relation` from `calc_eval.py` (extract to `_sympy_support.py`
     or import privately — prefer **extract** to `_sympy_support.py` so `calc_eval` and this instrument
     share one implementation).
   - **Variable extraction:** every name free in the relation must appear in `variables`; extra keys in
     `variables` are rejected (`422`-class `ValueError` at run time).
   - **Search loop:** iterate assignments in deterministic order (nested loops: sorted variable names,
     inner `min..max` ascending). Increment `samples_tried`; stop early on first falsifying assignment.
     Stop at `max_samples` even if the full grid is larger — set output field `truncated: bool` when
     the cap prevents exhausting the space (honesty: “searched N of M”).
   - **Evaluation:** substitute integers, evaluate via the same `_relation_holds` logic as `calc.eval`
     (extract alongside `_split_relation`). `False` → witness; `True` → continue; `None` (undecidable
     at this point) → skip assignment (do not treat as counterexample).
   - **Bounds:** cap per-variable range width (`max - min + 1 ≤ 50`) and total Cartesian product
     (`≤ 50_000` before `max_samples` clipping) — reject with a clear error before the loop starts
     (DoS parity with geometry’s input caps).

2. **Register** in `app/toolbench/instruments/__init__.py` — append to `INSTRUMENTS` tuple and
   `__all__`.

3. **Update conformance auto-coverage** — `test_production_registry_holds_the_tier0_instruments` (or
   equivalent) must expect five instruments including `counterexample.search`.

4. **Tests** (`tests/toolbench/test_instruments.py` additions, DB-free):
   - Conforms structurally (`check_conformance`).
   - Finds the flagship witness (`d == a + b` → `a=3,b=4,d=5`).
   - `found=False` on a relation true over the whole small grid (e.g. `a + b == b + a` on `a,b ∈ [1,3]`).
   - Rejects unknown variable, empty variables, product too large, `max_samples` truncation honesty.
   - Rejects relation with no free variables matching `variables` keys.
   - Parser injection vector still blocked if relation text is hostile.

**Deliverable / demoable:** `registry.get("counterexample.search").run(...)` returns `refuted` with
witness for the flagship case.

**Verification:**

```bash
cd backend && uv run ruff check . && uv run pytest tests/toolbench/test_instruments.py tests/toolbench/test_conformance.py -q
```

---

## Phase 2 — Write path + API round-trip for `counterexample.search`

**Goal:** the new instrument lands on the ledger through the existing chokepoint; API catalog lists it.

**Tasks**

1. **No `tool_runs.py` changes expected** — generic path already handles any registered instrument.
   Confirm `relation_kind` defaults: `refuted` → `weaken`, `result` → `support`.

2. **DB-backed tests** (`tests/toolbench/test_instruments_write_path.py` additions):
   - Run targeting a claim: refuted path mints `Evidence` + `weaken` link + `counterexample` artifact.
   - No-find path mints `result` + `support` link (weak support — assert `found=false` in output).
   - Blame tuple carries `instrument="counterexample.search"`, pinned `engine_version`.

3. **API test** (`tests/toolbench/test_instruments_api.py`):
   - `GET /instruments` includes `counterexample.search` with JSON Schema for `VariableRange`.
   - Authenticated member round-trip: flagship inputs → `201` + checkpoint summary.

**Deliverable / demoable:** `curl` (or httpx test) runs the flagship falsification; ledger shows one
`tool_run` contribution and a `counterexample` artifact.

**Verification:**

```bash
# Throwaway Postgres — same pattern as the 0.9.9 gate; container removed after.
TEST_DATABASE_URL='postgresql+asyncpg://…' uv run pytest tests/toolbench/test_instruments_write_path.py tests/toolbench/test_instruments_api.py -q
```

---

## Phase 3 — Frontend drive + show for `counterexample.search`

**Goal:** human-invokable workspace surface; honesty rules for weak support vs definitive refutation.

**Tasks**

1. **`drive-forms.tsx` — `CounterexampleSearchForm`**
   - Fields: relation (default `d == a + b`), variable range editor (name + min + max rows; demo defaults
     `a:1–10`, `b:1–10`, `d:1–15`), `max_samples` (default `500`).
   - Reuse the stable-row-id pattern from geometry (remove middle row without focus bugs).
   - Wire in `DriveForm` switch case.

2. **`result-view.tsx` — `CounterexampleSearchBody`**
   - `refuted` → existing `CounterexampleCard`: show `witness_relation`, witness assignment chips
     (`a=3`, `b=4`, `d=5`), caption “definitively falsifies the relation in this search space”.
   - `result` + `found=false` → **dedicated weak-support card** (neutral/hatched edge, not ok-green):
     headline “No counterexample found”; show `samples_tried`, `search_space`, and if `truncated` the
     honest “search capped — not exhaustive” caveat. **Never** “proven” / “validated” copy.
   - Route in the instrument `switch` alongside `calc.eval`, etc.

3. **`assumptions-editor.tsx`** — no default assumptions for this instrument (optional empty).

4. **`types/toolbench.ts`** — only if new response fields need explicit typing (likely unnecessary if
   outputs stay `Record<string, unknown>`).

**Deliverable / demoable:** signed-in member runs flagship falsification from the panel; counterexample
card appears; checkpoint on selected branch/main line.

**Verification:**

```bash
cd frontend && npm run typecheck && npm run lint && npm run build
```

Manual post-deploy: run flagship case; confirm branch scoping + sealed-branch disable still hold
(`0.9.8` behaviour).

---

## Phase 4 — Backend LaTeX companions (`to_latex`)

**Goal:** instruments emit authoritative LaTeX beside SymPy strings; hashing unchanged.

**Tasks**

1. **`_sympy_support.py`**
   - `to_latex(text: str, assumptions: dict) -> str | None` — parse → `sympy.latex()`; catch failures
     → `None`.
   - Extract shared `_split_relation` / `_relation_holds` from `calc_eval.py` here (Phase 1 dependency).

2. **Instrument output enrichment** (additive fields only):
   - `calc_eval.py` — `expression_latex`, `value_latex` when applicable.
   - `expr_compare.py` — `left_latex`, `right_latex`, `difference_latex`.
   - `geometry_measure.py` — latex for numeric measurement values (angles as degrees string is fine;
     distance `5` → `"5"` latex trivial).
   - `counterexample_search.py` — `witness_relation_latex` when `found`.

3. **Tests** (DB-free):
   - `to_latex("x**2 - 1")` contains superscript markup.
   - Existing instrument tests assert `*_latex` keys present on representative runs.
   - Content hash in write-path test **unchanged** when latex fields added (confirm hash excludes
     latex OR latex is derived-only and not in hashed output — **decision:** hash the same fields as
     before; add latex *after* hash computation in service layer, OR include latex in output but accept
     hash change only on new runs — prefer computing hash from pre-latex `model_dump` exclude set).

   **Recommended hash rule:** `_canonical_output_hash` excludes keys ending in `_latex` so presentation
   additions never invalidate dedup semantics.

4. **`services/tool_runs.py`** — if needed, pass `exclude={"*_latex"}` pattern into hash helper (implement
   `keys ending with _latex` strip).

**Deliverable / demoable:** API run response for `expr.compare` includes `difference_latex`; hash stable
vs pre-0.10.4 runs on the same mathematical content.

**Verification:**

```bash
cd backend && uv run ruff check . && uv run pytest tests/toolbench/ -q
TEST_DATABASE_URL='…' uv run pytest tests/toolbench/test_write_path.py::test_canonical_output_hash_is_stable_and_key_order_independent -q
```

---

## Phase 5 — Frontend KaTeX in `Formula`

**Goal:** readable math in all existing result cards + counterexample card.

**Tasks**

1. **Dependency:** `npm install katex` (+ import `katex/dist/katex.min.css` once in `formula.tsx` or
   `globals.css`).

2. **`formula.tsx` refactor** (single render seam — Phase 7 intent):
   ```tsx
   export function Formula({ expr, latex, className }: { expr: string; latex?: string | null; className?: string })
   ```
   - When `latex` is non-empty: `katex.renderToString(latex, { throwOnError: false, output: "html" })`
     inside a `dangerouslySetInnerHTML` span with Kamino-appropriate font sizing (still sans/mono
     hierarchy per blueprint — math block slightly larger, inherits `--text`).
   - On KaTeX error or missing `latex`: fall back to current monospace `expr` chip (provenance-safe).
   - `throwOnError: false` — a bad latex string must not white-screen the panel.

3. **Update all `Formula` call sites in `result-view.tsx`** to pass `latex={output.<field>_latex}` when
   present (`calc.eval`, `expr.compare`, `geometry`, `counterexample.search`).

4. **Drive forms:** optional preview is out of scope; inputs stay plain text.

**Deliverable / demoable:** `expr.compare` on `(a+b)**2` vs `a**2+b**2` shows typeset math; refuted
counterexample shows typeset `5 \neq 7` (or equivalent).

**Verification:**

```bash
cd frontend && npm run typecheck && npm run lint && npm run build
```

Visual check: superscripts, fractions, `\pi` in geometry angle output.

---

## Phase 6 — Flagship walkthrough + changelog

**Goal:** prove claims 1–4 narratively; ship docs.

**Tasks**

1. **Author a manual walkthrough checklist** (in this doc’s appendix or `docs/research-flow.md` cross-link)
   — not automated seed data:
   - Create thread “measuring across a corner”.
   - Claim A: “Return distance depends only on leg lengths” → `geometry.coordinate_measure` → support.
   - Claim B: “Return distance equals sum of legs” → `counterexample.search` → weaken (refuted).
   - Optionally fork/close branch on Claim B dead end.
   - Claim C/D: use `calc.eval` / `expr.compare` on squared-length relation (already shipped).
2. **Update `docs/changelog.md`** per release slice (`0.10.1`–`0.10.5` table below).
3. **Optional:** add `docs/completions/` phase notes as each slice lands (mirror `0.9.x` pattern).

**Verification:** full backend + frontend CI green; throwaway Postgres full suite `229 passed`.

---

## Release slicing

| Release | Phases | Demoable outcome |
|---|---|---|
| `0.10.1` | 1 | `counterexample.search` registered; flagship witness in DB-free tests. |
| `0.10.2` | 2 | Falsification lands on ledger via API. |
| `0.10.3` | 3 | Workspace drive/show; weak-support honesty in UI. |
| `0.10.4` | 4 | `*_latex` on outputs; hash excludes `_latex` keys. |
| `0.10.5` | 5 + 6 | KaTeX renders; flagship walkthrough complete; changelog updated. |

Each row updates `docs/changelog.md` on completion (per `CLAUDE.md`).

---

## Risks & watch-items

| Risk | Mitigation |
|---|---|
| Cartesian product DoS | Per-variable width cap + product cap + `max_samples`; mirror `0.9.8` geometry bounds tests. |
| “None found” misread as proof | Dedicated weak-support UI card; glossary copy reviewed; never use “validated” / “proven”. |
| LaTeX drift breaks content hash | Strip `*_latex` from `_canonical_output_hash`; DB test asserts stability. |
| KaTeX `throwOnError` | `false` + monospace fallback; never block result panel on bad latex. |
| Parser security regression | Reuse AST-gated `parse`; add one injection regression in Phase 1. |
| `calc_eval` refactor churn | Extract `_split_relation` / `_relation_holds` once; `calc_eval` imports — run full instrument tests. |
| Weak-support `support` link | Acceptable default per `tool_runs.py`; optional future: `relation_kind="context"` for no-find — **do not change in 0.10.x** unless product review demands it (would be API semantics change). |

---

## Verification matrix

| Phase | Backend | Frontend | DB |
|---|---|---|---|
| 1 | `ruff` + `pytest tests/toolbench/test_instruments.py` | — | none |
| 2 | `pytest tests/toolbench/test_instruments_write_path.py` | — | throwaway Postgres |
| 3 | — | `typecheck` + `lint` + `build` | manual signed-in |
| 4 | `pytest tests/toolbench/` | — | hash stability test on DB |
| 5 | — | `typecheck` + `lint` + `build` | manual visual |
| 6 | full `pytest` (`229`) | full FE CI | throwaway Postgres |

**Throwaway Postgres recipe** (same as prod-readiness gate):

```bash
docker run -d --name opentheory-pytest-throwaway \
  -e POSTGRES_USER=opentheory -e POSTGRES_PASSWORD=opentheory \
  -e POSTGRES_DB=opentheory_test -p 54329:5432 postgres:16-alpine
# wait for pg_isready …
TEST_DATABASE_URL='postgresql+asyncpg://opentheory:opentheory@127.0.0.1:54329/opentheory_test' \
  uv run pytest -q
docker rm -f opentheory-pytest-throwaway
```

---

## Appendix A — Flagship thread script (claims 1–4)

Manual workspace script for Phase 6 sign-off. Adjust claim text to taste; instrument inputs are the
load-bearing part.

| Step | Claim (summary) | Instrument | Expected outcome |
|---|---|---|---|
| 1 | Leg lengths determine return distance | `geometry.coordinate_measure` on `(0,0),(3,0),(3,4)` | `result` — `dist(A,C)=5`, `angle=90°` |
| 2 | Return distance **equals sum of legs** | `counterexample.search` — `d == a + b`, ranges `a,b,d ⊆ [1,15]` | `refuted` — witness `3,4,5` |
| 3 | Some relation among **squared** lengths | `calc.eval` — `3**2 + 4**2 == 5**2` | `result` |
| 4 | `dist² = leg₁² + leg₂²` for these legs | `expr.compare` — `(a+b)**2` vs `a**2+b**2` **or** dedicated equality on squared form | `refuted` or `undecided` depending on chosen claim shape — use the squared-distance claim text, not the sum claim |

After step 2: record validation or close branch as dead end (existing `0.4.x` flows).

Claim 5 (Lean proof) → **`0.12.x+`** with execution substrate.

---

## Appendix B — Optional stretch (`0.10.6+`, only if ahead of schedule)

**`interval.eval`** — `python-flint` / Arb, one value with proven enclosure (`docs/plans/maths-toolbox.md`
Bench 2). Adds `uv` dependency (LGPL), new instrument, and honest `result` with interval notation in
LaTeX. Not required for flagship claims 1–4.

---

## What comes after `0.10.x`

1. **`0.11.x`** — minimal execution sandbox (wall-clock + memory caps on instrument runs).
2. **`0.12.x`** — thin agent loop (Research crew → `POST …/run` on a thread).
3. **Tier 1 retrieval wave** — Crossref/arXiv pin instruments.
4. **Verifier wave** — Z3 (in-process, near-free) before Lean (substrate required).