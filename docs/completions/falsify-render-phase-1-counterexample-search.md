# Falsify & Render Phase 1 — `counterexample.search` backend (completion notes)

> **Status:** implemented · **Release slice:** `0.10.1` of
> `docs/executing/falsify-and-render-0.10.md` · **Scope:** backend only — the fifth Tier-0
> instrument plus shared relation-parsing extraction. **No API/UI changes yet** (Phases 2–3),
> **no LaTeX** (Phases 4–5), **no schema migration**.
>
> **What it delivers:** `counterexample.search` — a deterministic integer grid falsifier that
> records `refuted` + a witness when a relation is provably false, or `result` (weak support) when
> the capped search finds none. Shared `split_relation` / `relation_holds` live in `_sympy_support.py`
> so `calc.eval` and the new instrument cannot drift.

---

## 1. What this phase is (and is deliberately not)

Phase 1 adds the **first Bench 4 instrument** from `docs/plans/maths-toolbox.md` on the existing
`0.9.x` substrate (adapter protocol, registry, write-path chokepoint composition, conformance
harness). The instrument is thin: Pydantic I/O models, a bounded Cartesian loop, and the three honest
outcomes — load-bearing provenance, atomicity, and attribution were already shipped in `0.9.1`–`0.9.3`.

Not in this phase: workspace drive/show surfaces, DB-backed write-path/API round-trip tests for this
instrument (Phase 2), KaTeX/`*_latex` fields (Phases 4–5), assumptions on search runs (explicitly
rejected in v1).

## 2. What changed, where, and why

### 2.1 `app/toolbench/instruments/_sympy_support.py` (edited) — shared relation logic

**Extracted from `calc_eval.py`** (plan Decision 6):

- `RELATIONAL_OPS`, `split_relation()`, `relation_holds()` — the exact semantics `calc.eval` already
  shipped (`0.9.2`); moved here so `counterexample.search` evaluates relations identically and there
  is one place to fix inequality / `==` / undecidable behaviour.

`calc_eval.py` now imports these helpers; no behaviour change intended (existing `calc.eval` tests
are the regression guard).

### 2.2 `app/toolbench/instruments/counterexample_search.py` (new) — `counterexample.search`

| Piece | Behaviour |
|---|---|
| `VariableRange` | Inclusive `min`/`max` per variable (`±1000`); width cap **50** values per variable. |
| `CounterexampleSearchInput` | `relation` (≤500 chars), `variables` (1–8 names), `max_samples` (1–5000, default 500). Whole-grid product cap **50_000** assignments — reject at validation time. |
| Search order | Sorted variable names → nested `itertools.product` over `range(min, max+1)` — deterministic, reproducible. |
| Variable discipline | Parse relation; **every** declared variable must appear free in the relation; **no** extra keys. Integer symbols via `{"integer": True}` assumption flags. |
| Evaluation | Substitute assignment → `relation_holds()`; `False` → stop with `refuted`; `True` → continue; `None` → skip (not a counterexample). |
| No witness | `result` + `artifact_kind="derivation"` + `found=false` + `samples_tried` + `truncated` when product > `max_samples`. |
| Assumptions | v1 rejects non-empty `assumptions` with `ValueError` — contextual keys like `angle=90` do not apply to grid search. |

**Outcome mapping** (locked in `docs/executing/falsify-and-render-0.10.md`):

- Witness → `refuted` / `counterexample`
- Exhausted/capped search with no witness → `result` / `derivation` (weak support — never `undecided`)

**Flagship geometry story:** `d == a + b` with pinned ranges `a=3`, `b=4`, `d=5` yields witness
`5 == 7` (DB-free test). Over the demo-default ranges `a,b ∈ [1,10]`, `d ∈ [1,15]`, the *first*
falsifying assignment in sorted order is `(1,1,1) → 1 == 2` — still a valid counterexample to
“distance equals sum of legs,” found in one sample.

### 2.3 `app/toolbench/instruments/__init__.py` (edited) — registration

`COUNTEREXAMPLE_SEARCH` appended to `INSTRUMENTS`; production registry now holds **five** instruments.
Import side-effect unchanged (`app.toolbench` import populates registry for catalog/conformance).

### 2.4 `app/toolbench/instruments/calc_eval.py` (edited) — import-only refactor

Removed duplicated `_split_relation` / `_relation_holds`; imports `split_relation` / `relation_holds`
from `_sympy_support`. Zero intended semantic change.

### 2.5 Tests

| File | Change |
|---|---|
| `tests/toolbench/test_conformance.py` | Registry assertion expects `counterexample.search`. Auto-coverage parametrization picks it up automatically (`registry.all()`). |
| `tests/toolbench/test_instruments.py` | New section: conformance, definitive witness, geometry-story witness (pinned ranges), weak-support tautology, `max_samples` truncation, unused-variable rejection, plain-expression rejection, oversized-grid validation, assumptions rejection, AST injection block. `ALL_INSTRUMENTS` + output-model round-trip case updated. |

## 3. Judgment calls (interpretations of the plan)

### 3.1 First witness ≠ narrative triple on default ranges

The executing plan names `(3,4,5) → 5 == 7` as the flagship *story* witness. Deterministic grid order
hits `(1,1,1) → 1 == 2` first on the wide demo ranges — correct for the instrument (any falsifying
assignment is asymmetrically strong). Tests cover both: first-hit behaviour on demo ranges, and the
story triple under pinned `min == max` ranges.

### 3.2 “None found” is `result`, not `undecided`

Matches `maths-toolbox.md` Bench 4: the search *ran* and completed; absence of a counterexample in
the stated space is weak support. `undecided` is reserved for “could not decide this assignment”
(`relation_holds` → `None`), which is skipped rather than ending the run.

### 3.3 Oversized grid: two validation layers

Per-variable width (>50) fails on `VariableRange`; product >50_000 fails on `CounterexampleSearchInput`.
The test uses four variables `1..17` (product 83_521) to hit the product cap without tripping the
per-variable width guard first.

### 3.4 No assumptions in v1

Grid search is over plain integers; mixing SymPy symbol assumptions with contextual ledger assumptions
(e.g. `angle=90`) would blur what was searched. Fail loud if `assumptions` is non-empty; Phase 3 UI
will not show an assumptions editor for this instrument.

## 4. Verification

```bash
cd backend && uv run ruff check .
cd backend && uv run pytest tests/toolbench/test_instruments.py tests/toolbench/test_conformance.py -q
# 65 passed (DB-free)

cd backend && uv run pytest tests/toolbench/ -q
# 105 passed (DB-backed cases still skip without TEST_DATABASE_URL — Phase 2 target)
```

## 5. Scope boundary

- No `services/tool_runs.py` / route changes (generic path already handles any registered instrument).
- No frontend (`drive-forms.tsx`, `result-view.tsx`) — Phase 3.
- No `*_latex` / KaTeX — Phases 4–5.
- No changelog entry yet — batch at `0.10.1` merge per release slicing table.

## 6. Next step

**Phase 2 (`0.10.2`)** — DB-backed write-path + API round-trip tests for `counterexample.search`
(`test_instruments_write_path.py`, `test_instruments_api.py`): refuted path weakens a claim,
no-find path mints weak-support `result`, catalog lists the new JSON Schema.