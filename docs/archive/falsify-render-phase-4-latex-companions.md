# Falsify & Render Phase 4 — Backend LaTeX companions (completion notes)

> **Status:** implemented · **Release slice:** `0.10.4` of
> `docs/executing/falsify-and-render-0.10.md` · **Scope:** backend only — additive `*_latex`
> render hints on all five Tier-0 instruments; content hashing unchanged. **No frontend KaTeX yet**
> (Phase 5), **no schema migration**.
>
> **What it delivers:** API run responses include authoritative LaTeX beside SymPy strings for
> human-readable math; `_canonical_output_hash` strips `*_latex` keys recursively so presentation
> additions never change dedup semantics on the same mathematical content.

---

## 1. What this phase is (and is deliberately not)

Phase 4 is the **presentation layer on the backend** — SymPy strings remain the provenance ground
truth; LaTeX is a render hint the frontend will typeset in Phase 5 (`formula.tsx` + KaTeX).

Not in this phase: KaTeX wiring, changelog batch (Phase 6), standalone `formula.render` instrument.

## 2. What changed, where, and why

### 2.1 `app/toolbench/instruments/_sympy_support.py` — LaTeX helpers

| Helper | Role |
|---|---|
| `latex_of(expr)` | `sympy.latex()` on an already-parsed object; `None` on failure. |
| `to_latex(text, assumptions)` | parse → latex; `None` on failure. |
| `relation_to_latex(text, assumptions)` | relational expression → LaTeX with mapped operators (`==` → `=`, `<=` → `\leq`, …). |
| `attach_latex(output, **fields)` | merge non-`None` `*_latex` keys into a `model_dump` dict. |

Failures are swallowed — presentation-only; the SymPy string in the output dict is authoritative.

### 2.2 `app/services/tool_runs.py` — hash excludes latex

- `_strip_latex_keys()` — recursive drop of keys ending in `_latex` (including nested angle
  measures).
- `_canonical_output_hash()` — hashes the stripped dict. Same mathematical output → same hash
  whether or not latex companions are present.

### 2.3 Instrument output enrichment

| Instrument | New optional fields |
|---|---|
| `calc.eval` | `expression_latex`, `value_latex` (value mode) |
| `expr.compare` | `left_latex`, `right_latex`, `difference_latex` |
| `geometry.coordinate_measure` | `distances_latex` dict; per-angle `radians_latex`, `degrees_latex` |
| `counterexample.search` | `relation_latex`; `witness_relation_latex` when `found` |

Each instrument's `OutputModel` declares the new fields as optional (`None` default) so conformance
and `test_every_run_output_validates_against_its_output_model` stay green.

`geometry.coordinate_measure` still builds a strict `CoordinateMeasureOutput` first, then patches
latex companions onto the dumped dict (same pattern as before, now schema-documented).

### 2.4 Tests

| File | Change |
|---|---|
| `tests/toolbench/test_instruments.py` | `to_latex` superscript test; per-instrument `*_latex` presence tests; exact-equality assertions relaxed to core fields only (latex is additive). |
| `tests/toolbench/test_write_path.py` | `test_canonical_output_hash_ignores_latex_companions` — nested `angles.*.radians_latex` + top-level `distances_latex` stripped before hash. |

## 3. Judgment calls

### 3.1 OutputModel fields vs post-dump enrichment

LaTeX keys are declared on each `OutputModel` rather than treating them as extra dict keys. This
keeps `check_conformance` honest and documents the contract in the catalog JSON Schema without a
migration.

### 3.2 Hash strip is recursive

Nested `angles["A-B-C"]["radians_latex"]` must not affect the hash — a flat top-level-only strip
would have been wrong for geometry.

### 3.3 `attach_latex` omits `None`

When conversion fails, the key is absent (not `null`), so pre-0.10.4 consumers that ignore unknown
keys see no behaviour change on failure paths.

## 4. Verification

```bash
cd backend && uv run ruff check . && uv run pytest tests/toolbench/ -q
# hash tests (no DB required):
uv run pytest tests/toolbench/test_write_path.py::test_canonical_output_hash_is_stable_and_key_order_independent \
  tests/toolbench/test_write_path.py::test_canonical_output_hash_ignores_latex_companions -q
```

**Recorded run (2026-07-02):** ruff clean; **87 passed**, 19 skipped (DB-backed write-path tests
skipped without `TEST_DATABASE_URL`); both hash tests passed.

Full throwaway-Postgres gate (`244` tests) was not re-run in this session — Docker daemon
unavailable. Re-run before merge if ledger-touching code changes per plan prerequisite.

## 5. Next slice

**Phase 5 (`0.10.5`):** `npm install katex`; refactor `formula.tsx` to accept `latex` prop; wire
`result-view.tsx` call sites to pass `output.*_latex` when present.