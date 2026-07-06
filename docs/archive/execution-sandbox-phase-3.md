# `0.11.3` — Execution Sandbox Phase 3: Wire the Chokepoint

> **Status — completed (2026-07-03).** Phase 3 of
> `docs/executing/execution-sandbox-0.11.md`. All production instrument runs now go through the
> execution sandbox; concurrency is capped at the chokepoint. Phase 4 **completed** — see
> `docs/completions/execution-sandbox-phase-4.md`. **Next:** Phase 5 (`0.11.5`).

## What this phase delivered

| Deliverable | State |
|---|---|
| `acquire_run_slot()` asyncio semaphore in `policy.py` | Shipped |
| `async_runner.py` — `run_bounded_async` with `asyncio.wait_for` | Shipped |
| `runner.py` — `execute_sync_instrument` / `execute_async_instrument` | Shipped |
| `services/tool_runs.py` step 2 wired through sandbox | Shipped |
| HTTP `422` / `503` error mapping at chokepoint | Shipped |
| `docs/deploy.md` production cap guidance | Shipped |
| `tests/toolbench/test_execution_wiring.py` | Green (1 DB-free + 1 DB-backed when Postgres set) |
| `tests/toolbench/conftest.py` — semaphore reset between tests | Shipped |

No schema migration. Membership gate unchanged. `oeis.search` still runs async on the event loop.

## Behaviour change (production)

Before Phase 3, `run_instrument` step 2 called `instrument.run` directly (`anyio.to_thread` for sync).
After Phase 3:

```
run_instrument step 2
  async with acquire_run_slot(instrument_name):
    if async instrument → execute_async_instrument → asyncio.wait_for(run, wall_timeout)
    else               → execute_sync_instrument  → anyio.to_thread → run_bounded_sync (subprocess)
```

| Failure | HTTP | Ledger |
|---|---|---|
| `ToolbenchTimeout` / `ToolbenchMemoryExceeded` | `422` (`Instrument run exceeded resource limits: …`) | nothing minted |
| `ToolbenchBusy` | `503` (`Server busy — too many concurrent instrument runs`) | nothing minted |
| `ToolbenchWorkerError` / `ValueError` | `422` (`Instrument {name} failed to run: …`) | nothing minted |
| Instrument/network errors (e.g. `RetrievalError`) | `422` (generic handler) | nothing minted |
| Honest `undecided` / `result` / `refuted` | `201` via API | checkpoint minted |

## Files created

### `backend/app/toolbench/execution/async_runner.py`

`run_bounded_async(instrument, validated, assumptions, limits?)`:

- Resolves limits via `limits_for` when omitted.
- `asyncio.wait_for(instrument.run(...), timeout=wall_timeout_s)`.
- `TimeoutError` → `ToolbenchTimeout` with `wall_ms`.

**Why no subprocess for async:** `oeis.search` performs bounded httpx I/O (10s client timeout).
Wall-clock wrap uses the same `toolbench_wall_timeout_s` (30s default), so httpx fails before the
outer cap in normal operation (plan risk note: oeis double-timeout).

### `backend/app/toolbench/execution/runner.py`

High-level async entrypoints consumed by `tool_runs.py`:

| Function | Path |
|---|---|
| `execute_sync_instrument` | `limits_for` → `anyio.to_thread.run_sync(run_bounded_sync, name, json inputs, …)` |
| `execute_async_instrument` | `limits_for` → `run_bounded_async` |

Serializes `validated.model_dump(mode="json")` before crossing into the subprocess layer — the child
never receives Pydantic model instances.

## Files modified

### `backend/app/toolbench/execution/policy.py`

- Lazy `asyncio.Semaphore(toolbench_max_concurrent_runs)`.
- `acquire_run_slot(instrument_name=…)` — `asyncio.wait_for(sem.acquire(), acquire_timeout_s)`;
  on timeout → `ToolbenchBusy`.
- `reset_run_slot_semaphore()` — test helper when settings change mid-suite.

**Design choice:** Semaphore wraps **step 2 only** (instrument execution), not validation or ledger
composition — input validation and claim/thread checks still fail fast without holding a slot.

### `backend/app/services/tool_runs.py`

- Removed direct `anyio.to_thread.run_sync(instrument.run, …)` and bare `await instrument.run`.
- Added sandbox exception mapping with stable `_RESOURCE_LIMITS_PREFIX` for timeout/memory.
- `ToolbenchBusy` → `503` with the exception message (includes the plan's busy copy).

### `backend/app/toolbench/execution/__init__.py`

Exports: `acquire_run_slot`, `reset_run_slot_semaphore`, `run_bounded_async`,
`execute_sync_instrument`, `execute_async_instrument`.

### `docs/deploy.md`

- Fly `secrets set` example includes `TOOLBENCH_MEMORY_LIMIT_MB=256` and
  `TOOLBENCH_MAX_CONCURRENT_RUNS=2`.
- New section **Toolbench execution caps (`0.11.x`)** explaining prod tuning on `512mb` machines.

## Tests

### `tests/toolbench/conftest.py`

Autouse `reset_run_slot_semaphore()` before/after each toolbench test — prevents leaked semaphore
state when tests override `toolbench_max_concurrent_runs`.

### `tests/toolbench/test_execution_wiring.py`

| Test | Requires DB | Proves |
|---|---|---|
| `test_acquire_run_slot_raises_busy_when_saturated` | no | `ToolbenchBusy` after acquire timeout |
| `test_run_instrument_timeout_mints_nothing` | yes | `test.sleep` → `422` + zero artifacts/checkpoints |

Existing `test_instruments_api.py`, `test_write_path.py`, and `test_instruments_write_path.py`
continue to pass through the wired path (subprocess or in-thread per settings).

## Verification (run at completion)

```bash
cd backend && uv run ruff check .
cd backend && uv run pytest tests/toolbench/ -q
# 102 passed, 20 skipped (no TEST_DATABASE_URL)

# Recommended before prod merge (timeout wiring test + API round-trip):
TEST_DATABASE_URL='postgresql+asyncpg://…' uv run pytest tests/toolbench/test_execution_wiring.py \
  tests/toolbench/test_instruments_api.py -q
```

## What Phase 4 will add (`0.11.4`)

- `test_execution_safety.py` — adversarial cases, expensive SymPy, flagship regression parametrized
- Concurrency test with 3 overlapping slow stubs
- Full throwaway-Postgres toolbench suite gate

## What Phase 5 will add (`0.11.5`)

- `resource_used` on `ToolInvocation` blame tuple
- Structured INFO/WARNING logs per run

## Related docs

- Execution plan: `docs/executing/execution-sandbox-0.11.md` (Phase 3 section)
- Phase 2 completion: `docs/completions/execution-sandbox-phase-2.md`
- Deploy runbook: `docs/deploy.md`