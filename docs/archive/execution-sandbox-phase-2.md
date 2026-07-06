# `0.11.2` — Execution Sandbox Phase 2: Subprocess Runner

> **Status — completed (2026-07-03).** Phase 2 of
> `docs/executing/execution-sandbox-0.11.md`. Sync instruments can run in a killable child with
> wall-clock timeout; the in-thread fallback works when subprocess sandbox is disabled.
> **Production behaviour is still unchanged** — `services/tool_runs.py` is not wired until Phase 3
> (`0.11.3`). **Completed** — see `docs/completions/execution-sandbox-phase-3.md`. **Next:** Phase 4.

## What this phase delivered

| Deliverable | State |
|---|---|
| `execution/worker.py` — child entry + in-thread executor | Shipped |
| `execution/subprocess_runner.py` — `run_bounded_sync` | Shipped |
| `execution/__init__.py` exports `run_bounded_sync` | Shipped |
| `tests/toolbench/stubs.py` — `test.sleep` stub | Shipped |
| `tests/toolbench/test_subprocess_runner.py` (5 tests, DB-free) | Green |

No schema migration. No change to `services/tool_runs.py`, API routes, or frontend.

## Architecture

```
run_bounded_sync(name, inputs_dict, assumptions, limits)
        │
        ├─ subprocess_enabled() == False
        │     └─ run_instrument_in_thread()  (same process, for fast tests)
        │
        └─ subprocess_enabled() == True
              └─ spawn child → run_instrument_in_child()
                    ├─ _apply_memory_limit(RLIMIT_AS) when memory_limit_mb > 0
                    ├─ _bootstrap_registry()  (production instruments + optional test stubs)
                    ├─ InputModel.validate → instrument.run() → InstrumentResult
                    └─ queue envelope { ok, result | error, kind }
              parent join(timeout) → terminate → kill → map to typed errors
```

### IPC envelope (child → parent)

Success:

```json
{ "ok": true, "result": { "output": {...}, "status": "result", "artifact_kind": "...", ... } }
```

Failure:

```json
{ "ok": false, "error": "...", "kind": "value_error" | "worker_error" }
```

`ValueError` and Pydantic `ValidationError` from the child are serialized as `value_error` and
re-raised in the parent as `ValueError` — preserving the `422` class for Phase 3 mapping.
Unexpected child failures become `ToolbenchWorkerError`.

## Files created

### `backend/app/toolbench/execution/worker.py`

| Function | Role |
|---|---|
| `_bootstrap_registry()` | `import app.toolbench.instruments` (side-effect registration) |
| `_maybe_register_test_stubs()` | Imports `tests.toolbench.stubs` when pytest is on `PYTHONPATH` |
| `_apply_memory_limit()` | `resource.setrlimit(RLIMIT_AS, …)` when `memory_limit_mb > 0`; logs and skips on failure (macOS) |
| `_execute_instrument()` | Registry lookup → validate → sync `run()`; rejects awaitable returns |
| `run_instrument_in_child()` | Picklable multiprocessing target; puts envelope on queue |
| `run_instrument_in_thread()` | In-thread fallback (no subprocess overhead) |
| `envelope_to_result()` | Deserializes `InstrumentResult` or re-raises `ValueError` |
| `child_exit_implies_memory_kill()` | Detects SIGKILL exit (`-9`) for memory/OOM mapping |

**Design choice — name-based dispatch in child:** The worker receives `instrument_name` + JSON dicts,
not pickled instrument singletons. The child re-imports the registry from scratch (spawn semantics).
This matches plan Decision #3 and avoids pickle side effects.

**Design choice — test stubs via optional import:** `test.sleep` lives in `tests/toolbench/stubs.py`
and is registered only when the test package is importable. Production workers never see it; pytest
children bootstrap it through `_maybe_register_test_stubs()`.

### `backend/app/toolbench/execution/subprocess_runner.py`

`run_bounded_sync(instrument_name, inputs_dict, assumptions, limits) -> InstrumentResult`:

1. If `subprocess_enabled()` is False → `run_instrument_in_thread` (CI speed).
2. Else `multiprocessing.get_context("spawn")` + `Process(target=run_instrument_in_child, …)`.
3. `join(timeout=limits.wall_timeout_s)`.
4. If still alive → `terminate()` → grace `1.0s` → `kill()` → `ToolbenchTimeout`.
5. Read queue; empty queue + SIGKILL exit → `ToolbenchMemoryExceeded`.
6. Empty queue + other exit → `ToolbenchWorkerError`.
7. Success envelope → `InstrumentResult.model_validate`.

`wall_ms` is recorded on timeout/memory/worker errors for Phase 5 observability.

### `backend/tests/toolbench/stubs.py`

`test.sleep` — sleeps `inputs.seconds` (bounded 0–60s). Used to prove wall-clock kill without
blocking the full test suite when timeout is `0.5s` and sleep is `2s`.

`register_test_instruments()` — idempotent registration into the production `registry` singleton.

### `backend/tests/toolbench/test_subprocess_runner.py`

| Test | Proves |
|---|---|
| `test_calc_eval_completes_in_subprocess` | Production instrument `2+2` → `4` through spawn |
| `test_sleep_stub_times_out` | `ToolbenchTimeout` within ~0.5s, not 2s |
| `test_in_thread_fallback_when_subprocess_disabled` | `subprocess_enabled=False` path works |
| `test_value_error_reraised_from_child` | Unknown instrument → `ValueError` |
| `test_invalid_inputs_reraised_as_value_error` | Pydantic validation → `ValueError` in parent |

## Files modified

### `backend/app/toolbench/execution/__init__.py`

Added `run_bounded_sync` to public exports. Docstring updated: Phase 3 adds `run_bounded_async` +
chokepoint wiring.

## Error mapping (implemented in runner)

| Condition | Exception | `wall_ms` |
|---|---|---|
| `join` timeout + kill | `ToolbenchTimeout` | yes |
| Empty queue + exit `-SIGKILL` | `ToolbenchMemoryExceeded` | yes |
| Empty queue + other exit | `ToolbenchWorkerError` | yes |
| Envelope `value_error` | `ValueError` (re-raised) | — |
| Envelope `worker_error` | `ToolbenchWorkerError` | yes |

`ToolbenchBusy` is not used until Phase 3 (concurrency semaphore).

## What Phase 3 will add (`0.11.3`)

| Change | Location |
|---|---|
| Module-level asyncio semaphore | `policy.py` or `tool_runs.py` |
| Replace `anyio.to_thread.run_sync` | `services/tool_runs.py` step 2 |
| `run_bounded_async` with `asyncio.wait_for` | `execution/` for `oeis.search` |
| Map sandbox errors → HTTP `422` / `503` | `tool_runs.py` |
| `.env.example` + `docs/deploy.md` prod caps | `TOOLBENCH_MEMORY_LIMIT_MB=256` |

Phase 3 will call:

```python
limits = limits_for(instrument)
result = await anyio.to_thread.run_sync(
    run_bounded_sync,
    instrument.name,
    validated.model_dump(mode="json"),
    assumptions,
    limits,
)
```

(or an async wrapper — same contract).

## Verification (run at completion)

```bash
cd backend && uv run ruff check .
cd backend && uv run pytest tests/toolbench/test_subprocess_runner.py -q
# 5 passed
cd backend && uv run pytest tests/toolbench/ -q
# full toolbench suite green (no DB required for new tests)
```

## Risks noted (from plan, addressed in implementation)

| Risk | Mitigation in Phase 2 |
|---|---|
| Orphan subprocess after kill | `terminate()` → grace → `kill()`; `join` after each |
| `RLIMIT_AS` ineffective on macOS | `_apply_memory_limit` catches and logs; default `memory_limit_mb=0` |
| Subprocess startup latency | Acceptable for v1; tests can set `subprocess_sandbox_enabled=False` |
| Pickle instrument singletons | Name + JSON dicts only; child re-imports registry |
| Test instruments in production | `tests.toolbench.stubs` import guarded by `ImportError` |

## Related docs

- Execution plan: `docs/executing/execution-sandbox-0.11.md` (Phase 2 section)
- Phase 1 completion: `docs/completions/execution-sandbox-phase-1.md`
- Roadmap: `docs/plans/roadmap-next-steps.md`