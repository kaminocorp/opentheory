# `0.11.5` — Execution Sandbox Phase 5: Observability

> **Status — completed (2026-07-03).** Phase 5 of
> `docs/executing/execution-sandbox-0.11.md`. Successful instrument runs carry `resource_used` on the
> blame tuple; structured logs record completion and resource-limit failures. **Completed** — see
> `docs/completions/execution-sandbox-phase-6.md` and umbrella `execution-sandbox-0.11.md`.

## What this phase delivered

| Deliverable | State |
|---|---|
| `resource_used` optional field on `ToolInvocation` | Shipped |
| `ExecutionOutcome` + `build_resource_used` in execution layer | Shipped |
| `tool_runs.py` populates blame tuple + INFO/WARNING logs | Shipped |
| `tests/toolbench/test_execution_observability.py` (4 tests) | Green |
| Frontend `ToolInvocation.resource_used` type (optional) | Shipped |

No schema migration — additive JSON on existing `Checkpoint.tool_invocations` column.

## `resource_used` shape

Documented allowed keys (validated on strict-write via `ToolInvocation` field validator):

| Key | Type | When present |
|---|---|---|
| `wall_ms` | float (1 decimal) | Always on successful runs |
| `sandbox` | `"subprocess"` \| `"in-thread"` \| `"async"` | Always on successful runs |
| `memory_limit_mb` | int | When `toolbench_memory_limit_mb > 0` |
| `terminated` | `"timeout"` \| `"memory"` \| `"busy"` \| `"worker_error"` | Reserved for failure metadata (not minted on ledger today) |

Never stamped grades. Not part of `_canonical_output_hash` — presentation/ops only.

Example on a successful `calc.eval`:

```json
{
  "wall_ms": 142.3,
  "sandbox": "subprocess",
  "memory_limit_mb": 256
}
```

## Files created

### `backend/app/toolbench/execution/outcome.py`

- `ExecutionOutcome` — pairs `InstrumentResult` with `resource_used` dict.
- `build_resource_used()` — constructs the allowed-key payload from wall time, sandbox mode, and
  `ExecutionLimits`.
- `ALLOWED_RESOURCE_USED_KEYS` — shared with schema validator.

### `backend/tests/toolbench/test_execution_observability.py`

| Test | Proves |
|---|---|
| `test_tool_invocation_accepts_resource_used` | Strict-write parses known keys |
| `test_tool_invocation_rejects_unknown_resource_used_keys` | `grade` etc. rejected |
| `test_successful_calc_eval_blame_tuple_carries_resource_used` | DB: blame tuple + INFO log |
| `test_timeout_logs_warning_and_omits_resource_used` | DB: WARNING log, no checkpoint |

## Files modified

### `backend/app/schemas/tool_invocation.py`

Added optional `resource_used: dict[str, Any] | None` with `@field_validator` against
`ALLOWED_RESOURCE_USED_KEYS`.

### `backend/app/toolbench/execution/runner.py`

`execute_sync_instrument` / `execute_async_instrument` now return `ExecutionOutcome`:

- Sync: measures parent wall time around subprocess/in-thread call; sandbox =
  `"subprocess"` or `"in-thread"`.
- Async: measures `asyncio.wait_for` wall time; sandbox = `"async"`.

### `backend/app/services/tool_runs.py`

- Unpacks `outcome.result` and `outcome.resource_used`.
- Passes `resource_used` into `ToolInvocation(...)`.
- **INFO** on success: `instrument_run_complete name=… wall_ms=… status=… sandbox=… project_id=…
  actor_id=…` (no input PII).
- **WARNING** on `ToolbenchTimeout` / `ToolbenchMemoryExceeded`: `instrument_run_resource_limit
  instrument=… reason=… wall_ms=… project_id=… actor_id=…`.

Timeout paths still mint nothing — `resource_used` appears only on successful checkpoints.

### `backend/app/toolbench/execution/__init__.py`

Exports `ExecutionOutcome`, `build_resource_used`.

### `backend/tests/toolbench/test_execution_safety.py`

Updated for `ExecutionOutcome` return type; flagship regression also asserts `resource_used` present.

### `frontend/src/types/research.ts`

Optional `resource_used?: Record<string, unknown> | null` on `ToolInvocation` (lenient read).

## Verification (run at completion)

```bash
cd backend && uv run ruff check .
cd backend && uv run pytest tests/toolbench/test_execution_observability.py -q
# 2 passed DB-free; 2 skipped without TEST_DATABASE_URL

cd backend && uv run pytest tests/toolbench/ -q
# 119 passed, 26 skipped

cd frontend && npm run typecheck
```

Full backend suite: **183 passed**, 100 skipped.

## What Phase 6 will add (`0.11.6`)

- Kamino error copy for resource-limit `422` and busy `503` in toolbench panel / API client
- `docs/changelog.md` index for `0.11.1`–`0.11.6`
- Mark execution plan completed; point roadmap at `0.12.x`

## Related docs

- Execution plan: `docs/executing/execution-sandbox-0.11.md` (Phase 5 section)
- Phase 4 completion: `docs/completions/execution-sandbox-phase-4.md`