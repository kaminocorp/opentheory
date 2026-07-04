# `0.11.x` — Execution Sandbox (Toolbench Wave 3)

> **Status — completed (`0.11.6`, 2026-07-03).** All six phases shipped; see
> `docs/completions/execution-sandbox-phase-*.md` and `docs/changelog.md`. **What comes next:**
> `0.12.x` thin agent loop per `docs/plans/roadmap-next-steps.md`.

> Bounded, killable instrument execution for sync SymPy runs — wall-clock caps, optional memory
> ceiling, concurrency limit, and operator observability — without the full Fly microVM / Lean
> substrate (deferred until Lean or agent-written code lands).

## Prerequisite (closed)

- `0.10.x` Falsify & Render completed — flagship claims 1–4 walkthrough-ready.
- `0.9.x` toolbench spine — adapter, registry, chokepoint write path, membership-gated run route.

## Goal (achieved)

A member (later an agent on the same API) runs instruments with **bounded blast radius**:

1. Wall-clock timeout → `422`, nothing minted.
2. Memory ceiling (Linux prod, `RLIMIT_AS` in child) → `422`, parent survives.
3. Concurrency limit → `503` after acquire timeout, nothing minted.
4. Flagship walkthrough unchanged under default caps.
5. Successful runs carry `resource_used` on the blame tuple; failures show Kamino copy in the UI.

## Phase ledger

| Release | Phase | Completion doc |
|---|---|---|
| `0.11.1` | Policy, settings, error types | `execution-sandbox-phase-1.md` |
| `0.11.2` | Subprocess runner | `execution-sandbox-phase-2.md` |
| `0.11.3` | Wire chokepoint | `execution-sandbox-phase-3.md` |
| `0.11.4` | Safety + regression tests | `execution-sandbox-phase-4.md` |
| `0.11.5` | `resource_used` + logs | `execution-sandbox-phase-5.md` |
| `0.11.6` | Frontend error copy + changelog | `execution-sandbox-phase-6.md` |

## Architecture (shipped)

```
POST …/instruments/{name}/run
  → validate inputs
  → acquire_run_slot (semaphore)
  → sync: subprocess spawn → worker → InstrumentResult
     async: asyncio.wait_for(instrument.run, …)
  → on failure: 422 / 503, no db.add
  → on success: artifact + checkpoint + ToolInvocation(resource_used=…)
```

Production Fly env (see `docs/deploy.md`): `TOOLBENCH_MEMORY_LIMIT_MB=256`,
`TOOLBENCH_MAX_CONCURRENT_RUNS=2`.

## Out of scope (unchanged)

- Fly microVMs / Lean / arbitrary agent code execution.
- Agent loop (`0.12.x`).
- New instruments (Z3, `interval.eval`).

## Verification gate

```bash
cd backend && uv run ruff check . && uv run pytest tests/toolbench/ -q
cd frontend && npm run typecheck && npm run lint && npm run build

# Before prod merge:
TEST_DATABASE_URL='postgresql+asyncpg://…' uv run pytest tests/toolbench/ -q
```