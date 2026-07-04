# `0.11.1` — Execution Sandbox Phase 1: Policy, Settings, and Error Types

> **Status — completed (2026-07-03).** Phase 1 of
> `docs/executing/execution-sandbox-0.11.md`. Configuration and typed failure types exist;
> **production behaviour is unchanged** — the chokepoint is not wired until Phase 3 (`0.11.3`).
> **Next:** Phase 2 (`0.11.2`) — subprocess runner with kill-on-timeout. **Completed** — see
> `docs/completions/execution-sandbox-phase-2.md`.

## What this phase delivered

| Deliverable | State |
|---|---|
| `Settings` fields for sandbox caps | Shipped |
| `app/toolbench/execution/errors.py` — typed exceptions | Shipped |
| `app/toolbench/execution/policy.py` — `limits_for`, `subprocess_enabled` | Shipped |
| `oeis.search` marked `execution_mode = "async"` | Shipped |
| `.env.example` entries | Shipped |
| `tests/toolbench/test_execution_policy.py` (9 tests, DB-free) | Green |

No schema migration. No change to `services/tool_runs.py`, API routes, or frontend.

## Why Phase 1 is isolated (no wiring yet)

The execution plan slices by **demoable outcome per release**. Phase 1 establishes the configuration
contract and exception taxonomy that Phases 2–3 will consume, without risking regression on the
shipped flagship walkthrough. Policy and errors can be reviewed and tested in isolation; the
subprocess runner (Phase 2) and chokepoint integration (Phase 3) build on a stable surface.

This matches the standing invariant: **one write path** — nothing in Phase 1 touches
`run_instrument` step 2, so instrument runs still use the existing `anyio.to_thread` path.

## Files created

### `backend/app/toolbench/execution/errors.py`

Five exception types, all subclasses of `ToolbenchExecutionError`:

| Class | `reason` | Intended HTTP mapping (Phase 3) |
|---|---|---|
| `ToolbenchTimeout` | `timeout` | `422` |
| `ToolbenchMemoryExceeded` | `memory` | `422` |
| `ToolbenchBusy` | `busy` | `503` |
| `ToolbenchWorkerError` | `worker_error` | `422` |

Each carries `instrument_name`, optional `wall_ms`, and a human-readable message. The base class
uses `reason: Literal["timeout", "memory", "busy", "worker_error"]` so log mappers and API error
handlers can branch without string-matching exception class names.

**Design choice:** exceptions are raised *before* `db.add` in the write path (Phase 3). They are
distinct from instrument `ValueError` (bad inputs) and from honest `undecided` outcomes — sandbox
failures mean the tool did not complete, not that the math was inconclusive.

### `backend/app/toolbench/execution/policy.py`

- **`ExecutionLimits`** — frozen dataclass (`slots=True`) holding resolved caps for one run:
  `wall_timeout_s`, `memory_limit_mb`, `mode`, `max_concurrent_runs`, `acquire_timeout_s`.
- **`execution_mode_for(instrument)`** — reads optional class attribute `execution_mode`
  (`"subprocess"` | `"async"`); defaults to `"subprocess"`. Invalid values raise `ValueError` at
  resolve time (fail fast during development, not at runtime in prod).
- **`limits_for(instrument)`** — merges global `settings` with per-instrument mode.
- **`subprocess_enabled()`** — reads `toolbench_subprocess_sandbox_enabled` (Phase 2 uses this for
  the in-thread test fallback).

**Design choice:** `max_concurrent_runs` and `acquire_timeout_s` live on `ExecutionLimits` even though
Phase 1 does not use them yet — Phase 3's semaphore will take limits from the same object, avoiding
a second settings read at the chokepoint.

### `backend/app/toolbench/execution/__init__.py`

Public re-exports for policy and errors only. `run_bounded_sync` / `run_bounded_async` are documented
as Phase 2–3 entrypoints and are not exported until they exist.

## Files modified

### `backend/app/core/config.py`

Added five settings with plan defaults:

```python
toolbench_wall_timeout_s: float = 30.0
toolbench_memory_limit_mb: int = 0      # 0 = disabled; prod Fly sets 256
toolbench_max_concurrent_runs: int = 2
toolbench_acquire_timeout_s: float = 5.0
toolbench_subprocess_sandbox_enabled: bool = True
```

**Why `memory_limit_mb=0` locally:** `RLIMIT_AS` is unreliable on macOS dev. Production enables
256 MB via env (`docs/deploy.md` snippet lands in Phase 3). Defaulting to disabled locally avoids
surprise failures during development.

**Why `subprocess_sandbox_enabled`:** fast unit tests in Phase 2 can set `False` to run sync
instruments in-thread without subprocess startup latency; production must keep `True`.

### `backend/app/toolbench/instruments/oeis_search.py`

Added class attribute:

```python
execution_mode = "async"
```

**Why:** `oeis.search` is the only production instrument with `async def run`. It performs network I/O
on the event loop (httpx, already bounded by retrieval timeout in `0.9.4`). Phase 3 will wrap it with
`asyncio.wait_for`, not a subprocess. The four SymPy instruments stay on `"subprocess"` (default).

This is a **non-breaking Protocol extension** — `Instrument` does not require `execution_mode`; only
`policy.execution_mode_for` reads it via `getattr`.

### `backend/.env.example`

Documented all five `TOOLBENCH_*` env vars with comments explaining local vs production posture.

## Tests

`backend/tests/toolbench/test_execution_policy.py` — 9 DB-free tests:

1. Settings defaults match plan.
2. `limits_for(CALC_EVAL)` → `subprocess`, default caps.
3. `limits_for(OEIS_SEARCH)` → `async`.
4. `execution_mode_for` on both instruments.
5. `monkeypatch` on `settings` propagates into `limits_for`.
6. `subprocess_enabled()` tracks settings toggle.
7. Error types carry `instrument_name`, `reason`, `wall_ms`, custom messages.
8. All concrete errors subclass `ToolbenchExecutionError`.

Tests use the module-level `settings` singleton with `monkeypatch.setattr`, consistent with
`test_auth.py`, `test_projects.py`, etc.

## Verification (run at completion)

```bash
cd backend && uv run ruff check .
cd backend && uv run pytest tests/toolbench/test_execution_policy.py -q
# 9 passed
```

Full toolbench suite was not required for Phase 1 (no production path change). Re-run before merging
Phase 3 when `tool_runs.py` is wired.

## What Phase 2 will add (`0.11.2`)

| Module | Responsibility |
|---|---|
| `execution/worker.py` | Child entry: import registry, `run`, return serialized envelope |
| `execution/subprocess_runner.py` | `spawn` + `join(timeout)` + `terminate()` + `kill()` |
| `execution/__init__.py` | Export `run_bounded_sync` |
| `tests/toolbench/test_subprocess_runner.py` | Sleep stub timeout + `calc.eval` fast path |

Phase 2 will call `limits_for` and `subprocess_enabled` from the runner; error types will be raised
on timeout and child failure.

## What Phase 3 will add (`0.11.3`)

- Module-level asyncio semaphore from `toolbench_max_concurrent_runs`.
- Replace bare `anyio.to_thread.run_sync` in `services/tool_runs.py` with
  `run_bounded_sync` / `run_bounded_async`.
- Map `ToolbenchTimeout` / `ToolbenchMemoryExceeded` → HTTP `422`; `ToolbenchBusy` → `503`.

## Risks noted (unchanged from plan)

- `RLIMIT_AS` ineffective on macOS — mitigated by `memory_limit_mb=0` default locally.
- Subprocess startup latency (~50–200 ms) — acceptable for v1; tests can disable sandbox.
- No second SymPy parse path — child reuses same instrument code; `0.9.7` AST gate unchanged.

## Related docs

- Execution plan: `docs/executing/execution-sandbox-0.11.md` (Phase 1 section)
- Roadmap: `docs/plans/roadmap-next-steps.md` (`0.11.x` recommended next)
- Prior line: `docs/completions/falsify-and-render-0.10.md` (`0.10.x` prerequisite, closed)