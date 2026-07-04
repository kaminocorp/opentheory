# Falsify & Render Phase 2 — Write path + API round-trip (completion notes)

> **Status:** implemented · **Release slice:** `0.10.2` of
> `docs/executing/falsify-and-render-0.10.md` · **Scope:** tests only — no new backend routes,
> services, or schema. The generic `run_instrument` path and `POST …/instruments/{name}/run`
> from `0.9.2`/`0.9.6` already handle any registered instrument; Phase 2 proves
> `counterexample.search` composes through them on a real Postgres.
>
> **What it delivers:** DB-backed ledger tests for refuted and weak-support runs, plus an API
> round-trip and catalog assertion — the `0.10.1` instrument is end-to-end on the chokepoint.

---

## 1. What this phase is (and is deliberately not)

Phase 1 registered `counterexample.search` and proved its math in-process. Phase 2 is the
**ledger-invariant gate** for that instrument: one atomic transaction mints artifact (+ optional
evidence/links) + checkpoint + `tool_run` contribution, with the blame tuple round-tripping through
Postgres.

No production code changes were required — `services/tool_runs.py` and the run route are
instrument-agnostic. This phase is **test coverage + catalog assertion updates** only.

Not in this phase: frontend drive/show (Phase 3), LaTeX (Phases 4–5).

## 2. What changed, where, and why

### 2.1 `tests/toolbench/test_instruments_write_path.py` (edited)

Two new tests driving `run_instrument` with `COUNTEREXAMPLE_SEARCH`:

| Test | Asserts |
|---|---|
| `test_counterexample_search_refutes_a_claim_as_a_counterexample` | Geometry-story inputs (`a=b=c` pinned → `5 == 7`) → `REFUTED`; artifact `counterexample`; `ClaimEvidenceLink.relation_kind == weaken`; blame tuple `instrument=counterexample.search`, `engine_version` pinned, `found=true`. |
| `test_counterexample_search_no_find_supports_weakly` | Tautology `a + b == b + a` on `1..3` → `RESULT`; artifact `derivation`; link `support`; output `found=false`, `samples_tried=9`. |

Import: `COUNTEREXAMPLE_SEARCH` from `app.toolbench.instruments`.

Shared helper `_GEOMETRY_STORY_SEARCH` mirrors Phase 1's pinned-range witness test — the narrative
`(3,4,5)` triple, not the wide-grid first hit `(1,1,1)`.

### 2.2 `tests/toolbench/test_instruments_api.py` (edited)

| Change | Why |
|---|---|
| `test_instruments_catalog_is_public` — catalog set now includes `counterexample.search` | Registry grew in `0.10.1`; public catalog must list all five production instruments. |
| `test_run_counterexample_search_over_the_api` (new) | Member `POST …/counterexample.search/run` → `201`, `status=refuted`, blame tuple on response, exactly one `Checkpoint` in DB. |

No route or schema edits — the existing catalog serializer picks up the new instrument from the
registry automatically.

## 3. Judgment calls

### 3.1 Weak-support `relation_kind` stays `support`

`tool_runs.py` maps `ResultStatus.RESULT` → default `support`. The executing plan noted an optional
future `context` for no-find; we **did not** change that in `0.10.2` — the UI (Phase 3) carries the
“weak support, not proof” honesty via copy and card treatment, not a new relation kind.

### 3.2 Service-layer tests before HTTP

Write-path tests call `run_instrument` directly (same pattern as `calc.eval` / `oeis.search` in this
file). The API test is one happy-path round-trip — edges (`403`/`422`) remain covered generically for
`calc.eval` and apply to all instruments via the same route.

## 4. Verification

Throwaway Postgres (`opentheory-pytest-throwaway` on port `54329`, removed on `EXIT`):

```bash
cd backend && uv run ruff check .
TEST_DATABASE_URL='postgresql+asyncpg://opentheory:opentheory@127.0.0.1:54329/opentheory_test' \
  uv run pytest tests/toolbench/test_instruments_write_path.py tests/toolbench/test_instruments_api.py -v
# 13 passed

TEST_DATABASE_URL='…' uv run pytest -q
# 244 passed / 0 skipped
```

Container and port verified clean after the run (`docker rm -f`, port `54329` free).

## 5. Scope boundary

- Zero changes under `app/` (no `tool_runs.py`, routes, or instrument code).
- No frontend.
- No changelog entry yet — batch at `0.10.2` merge.

## 6. Next step

**Phase 3 (`0.10.3`)** — `CounterexampleSearchForm` + `CounterexampleSearchBody` in the workspace
(weak-support card vs definitive counterexample card); wire `DriveForm` / `result-view.tsx`.