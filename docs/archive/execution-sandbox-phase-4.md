# `0.11.4` — Execution Sandbox Phase 4: Regression + Adversarial Tests

> **Status — completed (2026-07-03).** Phase 4 of
> `docs/executing/execution-sandbox-0.11.md`. Safety properties and flagship regression are covered
> by a dedicated test module; `tests/test_toolbench_provenance.py` unchanged (no `resource_used`
> until Phase 5). **Completed** — see `docs/completions/execution-sandbox-phase-5.md`. **Next:**
> Phase 6 (`0.11.6`).

## What this phase delivered

| Deliverable | State |
|---|---|
| `tests/toolbench/test_execution_safety.py` (8 tests) | Green |
| DB-free timeout mint-nothing via `run_instrument` + recording session | Shipped |
| Expensive SymPy + max_samples adversarial cases | Shipped |
| Parametrized flagship regression through `execute_sync_instrument` | Shipped |
| Concurrency: 2 slots, 3 waiters → 2 success + 1 `ToolbenchBusy` | Shipped |
| `tests/test_toolbench_provenance.py` | Unchanged (Phase 5 scope) |

No production code changes — tests-only slice.

## Test module: `test_execution_safety.py`

All tests run with `toolbench_subprocess_sandbox_enabled=True` unless noted, exercising the
production subprocess path through `execute_sync_instrument` / `run_instrument`.

### 1. Timeout mints nothing (DB-free)

`test_timeout_via_run_instrument_mints_nothing_db_free`:

- `_RecordingSession` stub records `session.add` calls.
- `test.sleep` for 2s with `toolbench_wall_timeout_s=0.5`.
- Asserts `HTTPException` 422 with `Instrument run exceeded resource limits`.
- Asserts `session.added == []` — nothing flushed before failure.

Mirrors `test_write_path.test_engine_error_leaves_zero_rows` without Postgres.

### 2. Expensive SymPy (adversarial, bounded wall-clock)

`test_expensive_factorial_fails_fast_under_sandbox`:

- `calc.eval` on `factorial(50000)` through subprocess wrapper.
- SymPy hits Python's int string conversion limit → `ValueError` in **< 10s** (not a hung suite).
- Wrapped in `asyncio.wait_for(..., timeout=60)` as plan's wall-clock guard (no `pytest-timeout` dep).

`test_max_samples_grid_completes_under_sandbox`:

- `counterexample.search` on a **7_500-cell** space (`50×50×3`) capped at `max_samples=5000`.
- Completes with `truncated=True`, `samples_tried=5000`, within 60s.

### 3. Flagship regression (parametrized)

`test_flagship_instruments_complete_under_default_sandbox` — four cases through
`execute_sync_instrument` with default limits:

| Case | Instrument | Expected |
|---|---|---|
| Corner measure | `geometry.coordinate_measure` | `result`, `dist(A,C)=5`, angle `90°` |
| Pinned falsifier | `counterexample.search` | `refuted`, witness `5 == 7` |
| Pythagorean | `calc.eval` | `result`, `holds=True` |
| Binomial identity | `expr.compare` `(a+b)**2` vs `a²+b²` | `undecided`, `difference=2*a*b` |

**Note on expr.compare:** The plan listed this pair as a flagship walkthrough step; SymPy honestly
returns `undecided` (non-zero symbolic difference without a concrete witness). The regression test
asserts **completion under caps** with the correct honest outcome — not a forced `refuted`.

### 4. Concurrency (503 semantics)

`test_concurrency_third_waiter_gets_busy_not_unbounded_overlap`:

- `toolbench_max_concurrent_runs=2`, `toolbench_acquire_timeout_s=0.5`.
- Three parallel `acquire_run_slot` + `test.sleep(1.0)` runs.
- **Chosen behaviour:** 2 succeed, 1 raises `ToolbenchBusy` (maps to HTTP `503` at API layer).
- Does not wait for a fourth slot — fails fast after acquire timeout.

### Supporting changes

`tests/toolbench/stubs.py` — exports `SleepInstrument` in `__all__` for typed fixtures.

## `test_toolbench_provenance.py`

No changes. `ToolInvocation` shape is unchanged until Phase 5 adds optional `resource_used`.

## Verification (run at completion)

```bash
cd backend && uv run ruff check .
cd backend && uv run pytest tests/toolbench/test_execution_safety.py -q
# 8 passed (~5s with subprocess)

cd backend && uv run pytest tests/toolbench/ -q
# 110 passed, 20 skipped (no TEST_DATABASE_URL)

# Throwaway Postgres gate (recommended before prod merge):
TEST_DATABASE_URL='postgresql+asyncpg://…' uv run pytest tests/toolbench/ -q
```

Full backend suite (no DB): **174 passed**, 100 skipped.

## What Phase 5 will add (`0.11.5`)

- `resource_used: dict | None` on `ToolInvocation`
- Populate `wall_ms`, `sandbox` mode from execution layer
- INFO/WARNING structured logs per instrument run
- Blame tuple tests in `test_instruments_write_path.py`

## What Phase 6 will add (`0.11.6`)

- Frontend Kamino error copy for resource limits / busy
- Changelog index for `0.11.1`–`0.11.6`

## Related docs

- Execution plan: `docs/executing/execution-sandbox-0.11.md` (Phase 4 section)
- Phase 3 completion: `docs/completions/execution-sandbox-phase-3.md`
- Flagship walkthrough: `docs/executing/falsify-and-render-0.10.md` Appendix A