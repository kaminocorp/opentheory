# `0.11.x` — Minimal Execution Sandbox (Toolbench Wave 3)

> **Status — completed (`0.11.6`, 2026-07-03).** Prerequisite: `0.10.x` Falsify & Render **completed**
> (`docs/executing/falsify-and-render-0.10.md`). Shipped **in-process hardening** around
> instrument execution — wall-clock caps, optional memory caps, concurrency limits, and killable
> subprocess isolation for CPU-bound Tier-0 runs. **Not** the full Fly microVM / Lean substrate
> (`docs/plans/agent-research-tools.md` §6) — that remains a later line when Lean or
> agent-written code lands.

## Prerequisite (closed)

- `0.9.x` toolbench spine: adapter, registry, chokepoint write path, membership-gated run route.
- `0.10.x` flagship instruments + KaTeX render — regression suite for “normal” runs.
- Live deploy on Fly `shared-cpu-1x` / `512mb` (`backend/fly.toml`) — caps must be tuned for this
  envelope.

Re-run the full backend suite (`TEST_DATABASE_URL`) before merging each `0.11.x` slice.

## Goal

A member (later an agent on the same API) can run instruments with **bounded blast radius**:

1. **Wall-clock timeout** — a slow or hung SymPy run is terminated; the API returns **`422`**, nothing
   is minted on the ledger (same failure split as today).
2. **Memory ceiling (Linux prod)** — a runaway allocation in a child worker is killed before it OOMs
   the API process; **`422`** with a clear message, nothing minted.
3. **Concurrency limit** — many parallel runs cannot exhaust the Fly machine; excess waiters get
   **`503`** (service busy), nothing minted.
4. **Flagship walkthrough unchanged** — claims 1–4 complete within default caps; no UX regression for
   honest inputs.

The acceptance bar: a **deliberately slow** stub instrument and a **legal-but-expensive** input (e.g.
`factorial(100_000)` or a sleep stub) are stopped by the sandbox; the geometry / falsifier / KaTeX
walkthrough still passes.

## Why this line is next (not agents yet)

| Gap today | `0.11.x` closes it |
|---|---|
| Sync SymPy runs use `anyio.to_thread` with **no timeout** — a hung thread blocks a worker slot forever | Killable **subprocess** wrapper with wall-clock join + `terminate()` |
| `0.9.7` AST gate closed RCE; **legal** bombs (`factorial(huge)`, full grid at cap) can still OOM the API process | Optional **`RLIMIT_AS`** in the child (Linux); parent survives |
| No limit on concurrent instrument runs on a `512mb` machine | **Semaphore** on the run chokepoint |
| No operational signal for tuning caps | **`resource_used`** on the blame tuple + structured logs |

`0.12.x` agent loop should not ship until runs have a hard ceiling — agents will multiply invocation
rate and input diversity.

## Standing invariants (unchanged)

| Invariant | How this line honours it |
|---|---|
| One write path | Sandbox wraps step 2 of `run_instrument` only — still no alternate checkpoint mint path. |
| Failure split | Timeout / OOM / capacity → exception **before** `db.add` → **`422`** or **`503`**, nothing minted. |
| `undecided` is success | Only applies when `run()` returns normally; sandbox failures are tool exceptions, not outcomes. |
| Human-first | No agent changes; same `POST …/instruments/{name}/run` route. |
| No schema migration | Optional `resource_used` JSON on `ToolInvocation` only (checkpoint JSON column already exists). |

## Decisions (locked before implementation)

1. **Subprocess for sync Tier-0, not threads.** Python threads cannot be force-stopped. CPU-bound
   instruments (`calc.eval`, `expr.compare`, `geometry.coordinate_measure`, `counterexample.search`)
   run in a **`spawn`** child process (portable on macOS dev + Linux prod). Parent `join(timeout)`;
   if alive → `terminate()` → brief grace → `kill()`.
2. **Async retrieval stays on the event loop.** `oeis.search` remains `async def`; wrap with
   `asyncio.wait_for` using the same wall-clock budget (or a dedicated retrieval budget). No
   subprocess — network I/O is already bounded by httpx timeout (`0.9.4`).
3. **Instrument dispatch is name-based in the child.** The worker receives `instrument_name` +
   serialized `inputs` / `assumptions` dicts, imports the registry (side-effect registration), and
   calls `run`. Do **not** pickle instrument singletons across processes.
4. **Configurable caps via `Settings`.** Defaults conservative for `512mb` Fly:
   - `toolbench_wall_timeout_s = 30`
   - `toolbench_memory_limit_mb = 256` (child `RLIMIT_AS`; `0` = disabled — default on macOS local
     where `RLIMIT_AS` is unreliable, **enabled in production** via env)
   - `toolbench_max_concurrent_runs = 2`
   - `toolbench_subprocess_sandbox_enabled = True` (set `False` in fast unit tests that use stubs)
5. **`resource_used` is optional and additive** on `ToolInvocation` — e.g.
   `{ "wall_ms": 412, "sandbox": "subprocess", "terminated": "timeout" }`. Never stamped grades;
   never part of content hash.
6. **HTTP status mapping:**
   - Timeout / memory / instrument `ValueError` → **`422`** (tool did not complete successfully).
   - Semaphore not acquired within `toolbench_acquire_timeout_s` (e.g. 5s) → **`503`** with
     `"Server busy — too many concurrent instrument runs"`.
7. **No microVM, no gVisor, no Lean in `0.11.x`.** Document the seam: when Lean lands, add
   `execution_mode = "microvm"` and a second executor backend — out of scope here.

## Out of scope (explicitly)

- Fly Sprites / per-task Firecracker microVMs.
- Z3, Lean, `interval.eval`, new instruments.
- Agent loop / Research crew execution (`0.12.x`).
- Frontend progress UI for long runs (optional copy-only slice in Phase 6).
- Per-project or per-member budget accounting (funding simulation stays separate).
- cgroup v2 CPU throttling (wall-clock kill is enough for v1).

---

## Architecture (target state)

```
POST …/instruments/{name}/run
        │
        ▼
services/tool_runs.run_instrument
        │
        ├─ validate inputs / claim / thread (unchanged)
        │
        ├─ acquire concurrency semaphore (new)
        │
        ├─ execute instrument (replaces bare to_thread):
        │     ├─ sync compute  → toolbench.execution.run_bounded_sync(name, inputs, assumptions)
        │     │                    └─ subprocess spawn → worker → queue → InstrumentResult
        │     └─ async retrieval → asyncio.wait_for(instrument.run(...), timeout=...)
        │
        ├─ on sandbox failure → HTTPException 422/503, no db.add
        │
        └─ compose artifact / evidence / checkpoint (unchanged)
```

### New modules

| Path | Responsibility |
|---|---|
| `app/toolbench/execution/__init__.py` | Public `run_bounded_sync`, `run_bounded_async` entrypoints. |
| `app/toolbench/execution/policy.py` | Resolve timeouts/memory/concurrency from `settings` + per-instrument overrides. |
| `app/toolbench/execution/subprocess_runner.py` | Spawn/join/terminate/kill; `RLIMIT_AS` in child; queue IPC. |
| `app/toolbench/execution/worker.py` | Child entry: register instruments, validate, `run`, return serialized result. |
| `app/toolbench/execution/errors.py` | `ToolbenchTimeout`, `ToolbenchMemoryExceeded`, `ToolbenchBusy` (subclasses of a common base). |

### Optional protocol extension (Phase 1)

Add a **non-required** class attribute on instruments (no Protocol break for existing five):

```python
# On Instrument implementations — default applied in policy.py when absent
execution_mode: Literal["subprocess", "async"] = "subprocess"  # compute
# oeis.search: execution_mode = "async"
```

---

## Phase 1 — Policy, settings, and error types (`0.11.1`)

**Goal:** configuration and typed failures exist; no behaviour change yet.

**Tasks**

1. **`app/core/config.py`** — add settings (with sensible defaults and `.env.example` entries):
   - `toolbench_wall_timeout_s: float = 30.0`
   - `toolbench_memory_limit_mb: int = 0` (0 = disabled; document that production Fly sets `256`)
   - `toolbench_max_concurrent_runs: int = 2`
   - `toolbench_acquire_timeout_s: float = 5.0`
   - `toolbench_subprocess_sandbox_enabled: bool = True`

2. **`app/toolbench/execution/errors.py`** — exception types mapped later to HTTP statuses; carry
   `instrument_name`, `wall_ms`, `reason` (`timeout` | `memory` | `busy` | `worker_error`).

3. **`app/toolbench/execution/policy.py`**
   - `def limits_for(instrument: Instrument) -> ExecutionLimits` (wall, memory, mode).
   - `def subprocess_enabled() -> bool` reads settings (and `APP_ENV` hint for tests).

4. **Mark `oeis.search`** with `execution_mode = "async"` (class attribute on `OeisSearch`).

5. **Tests** (`tests/toolbench/test_execution_policy.py`, DB-free):
   - Defaults load from settings.
   - `oeis.search` resolves to async mode; `calc.eval` to subprocess.

**Deliverable:** imports and policy unit tests green; production behaviour unchanged (not wired).

**Verification:**

```bash
cd backend && uv run ruff check . && uv run pytest tests/toolbench/test_execution_policy.py -q
```

---

## Phase 2 — Subprocess runner (`0.11.2`)

**Goal:** sync instruments can run in a killable child with wall-clock timeout.

**Tasks**

1. **`app/toolbench/execution/worker.py`**
   - Top-level function `_run_instrument_in_child(instrument_name, inputs_dict, assumptions, limits)`
     importable as `__main__` target.
   - Apply `resource.setrlimit(RLIMIT_AS, ...)` when `memory_limit_mb > 0` and platform supports it
     (guard with try/except; skip on macOS dev with log warning).
   - Return a small result envelope: `{ "ok": true, "result": InstrumentResult dict }` or
     `{ "ok": false, "error": str, "kind": "..." }`.

2. **`app/toolbench/execution/subprocess_runner.py`**
   - `run_bounded_sync(instrument_name, inputs_dict, assumptions, limits) -> InstrumentResult`.
   - Use `multiprocessing.get_context("spawn")`.
   - `join(timeout=wall_timeout_s)`; on expiry `terminate()`, short second `join`, then `kill()`.
   - Map child exit codes: negative SIGKILL → memory or hard kill; queue empty after timeout →
     `ToolbenchTimeout`.
   - Re-raise instrument `ValueError` from child as-is (still `422` class).

3. **`app/toolbench/execution/__init__.py`** — export `run_bounded_sync`.

4. **Tests** (`tests/toolbench/test_subprocess_runner.py`, DB-free):
   - Register a **test-only stub** instrument `test.sleep` in `tests/toolbench/stubs.py` (or conftest)
     that sleeps N seconds; assert timeout when `toolbench_wall_timeout_s=0.5`.
   - Fast instrument (`calc.eval` `2+2`) completes under cap.
   - When `toolbench_subprocess_sandbox_enabled=False`, fallback runs in-thread (for CI speed) —
     document that production keeps subprocess `True`.

**Deliverable:** `run_bounded_sync("calc.eval", …)` returns correct result; sleep stub times out.

**Verification:**

```bash
cd backend && uv run pytest tests/toolbench/test_subprocess_runner.py -q
```

---

## Phase 3 — Wire the chokepoint (`0.11.3`)

**Goal:** all production runs go through the sandbox; concurrency capped.

**Tasks**

1. **Module-level asyncio semaphore** in `app/toolbench/execution/policy.py` or `tool_runs.py`:
   - Lazy-init from `toolbench_max_concurrent_runs`.
   - `async with acquire_run_slot():` around step 2 only.

2. **`app/services/tool_runs.py`** — replace the bare `anyio.to_thread.run_sync` branch:

   ```python
   if iscoroutinefunction(instrument.run):
       result = await run_bounded_async(instrument, validated, assumptions)
   else:
       result = await run_bounded_sync(instrument, validated, assumptions)
   ```

   - `run_bounded_sync` serializes `validated.model_dump(mode="json")`, calls execution layer,
     deserializes `InstrumentResult`.
   - Map `ToolbenchTimeout` / `ToolbenchMemoryExceeded` → `HTTP 422` with stable message prefix
     `"Instrument run exceeded resource limits"`.
   - Map `ToolbenchBusy` → `HTTP 503`.

3. **`run_bounded_async`** — `asyncio.wait_for(instrument.run(...), timeout=wall_timeout)`.

4. **Remove direct `anyio.to_thread` for instruments** (only path is execution module).

5. **`.env.example`** + **`docs/deploy.md`** snippet: production Fly env suggestions:
   `TOOLBENCH_MEMORY_LIMIT_MB=256`, `TOOLBENCH_MAX_CONCURRENT_RUNS=2`.

**Deliverable:** API runs use sandbox; `oeis.search` still works; membership gate unchanged.

**Verification:**

```bash
cd backend && uv run ruff check . && uv run pytest tests/toolbench/ -q
TEST_DATABASE_URL='…' uv run pytest tests/toolbench/test_instruments_api.py -q
```

---

## Phase 4 — Regression + adversarial tests (`0.11.4`)

**Goal:** prove safety properties and no flagship regression.

**Tasks**

1. **`tests/toolbench/test_execution_safety.py`** (DB-free):
   - Timeout stub instrument via registry (test-only) — API-less service call to `run_instrument` with
     `toolbench_subprocess_sandbox_enabled=True`.
   - Assert **no** `Artifact` / `Checkpoint` rows after timeout (service-layer: mock session or
     expect exception before flush — mirror existing write-path exception tests).

2. **Expensive SymPy case** — e.g. `factorial(50000)` or existing grid at `max_samples` cap: completes
   or fails fast with `422`, never hangs the test suite (mark `@pytest.mark.timeout(60)`).

3. **Flagship regression** — parametrized over:
   - `geometry.coordinate_measure` corner
   - `counterexample.search` pinned `5 == 7`
   - `calc.eval` `3**2 + 4**2 == 5**2`
   - `expr.compare` `(a+b)**2` vs `a**2+b**2`
   All complete under default limits.

4. **Concurrency test** — spawn 3 overlapping slow stubs with `max_concurrent_runs=2`; third gets
   `503` or waits then succeeds (document chosen behaviour; prefer **503** after acquire timeout).

5. **Update `tests/test_toolbench_provenance.py`** if `ToolInvocation` shape changes in Phase 5 — or
   keep Phase 4 green without `resource_used` until Phase 5 lands.

**Deliverable:** safety tests + full toolbench suite green on throwaway Postgres.

**Verification:**

```bash
TEST_DATABASE_URL='…' uv run pytest tests/toolbench/ -q
```

---

## Phase 5 — Observability (`0.11.5`)

**Goal:** operators can tune caps; ledger carries timing metadata.

**Tasks**

1. **`app/schemas/tool_invocation.py`** — add optional field:

   ```python
   resource_used: dict[str, Any] | None = None
   # e.g. {"wall_ms": 412, "sandbox": "subprocess", "memory_limit_mb": 256}
   ```

   Strict-write: only known keys documented in schema docstring; no grades.

2. **`tool_runs.py`** — populate `resource_used` from execution layer return metadata (wall ms,
   sandbox mode, termination reason when applicable).

3. **Structured logging** — one log line per run at INFO:
   `instrument_run_complete name=calc.eval wall_ms=… status=result sandbox=subprocess`;
   WARNING on timeout/OOM with project_id + actor_id (no PII in inputs).

4. **Tests** — blame tuple includes `resource_used` on a successful `calc.eval` run; omitted on
   timeout paths (nothing minted).

**Deliverable:** successful runs show timing in `checkpoint.tool_invocations[0].resource_used`.

**Verification:**

```bash
TEST_DATABASE_URL='…' uv run pytest tests/toolbench/test_instruments_write_path.py -q
```

---

## Phase 6 — Frontend error copy + docs (`0.11.6`)

**Goal:** users see legible errors; release ledger updated.

**Tasks**

1. **`toolbench-panel.tsx`** (or API client error mapper in `lib/api.ts`):
   - Map `422` bodies containing `"resource limits"` / `"timed out"` to a stable user-facing string
     (Kamino tone): *"This run exceeded the server time or memory limit — narrow the search space or
     simplify the expression."*
   - Map `503` busy: *"The server is running other instrument jobs — try again in a moment."*
   - Do not change success/result cards.

2. **`docs/changelog.md`** — index + sections for `0.11.1`–`0.11.6`.

3. **`docs/completions/execution-sandbox-phase-*.md`** — optional per-phase notes (mirror `0.10.x`).

4. **Mark this plan completed** in the status banner; point `docs/plans/roadmap-next-steps.md` at
   `0.12.x` agent loop.

5. **Manual sign-off:** run flagship walkthrough on staging/prod with default caps; intentionally
   trigger timeout (sleep stub in staging only, or very large factorial in dev).

**Verification:**

```bash
cd frontend && npm run typecheck && npm run lint && npm run build
cd backend && uv run ruff check . && uv run pytest -q
```

---

## Release slicing

| Release | Phase | Demoable outcome |
|---|---|---|
| `0.11.1` | 1 | Settings + policy + error types; tests only. |
| `0.11.2` | 2 | Subprocess runner kills sleep stub on timeout. |
| `0.11.3` | 3 | All API runs sandboxed; concurrency limit live. |
| `0.11.4` | 4 | Safety + flagship regression tests green on Postgres. |
| `0.11.5` | 5 | `resource_used` on blame tuple + logs. |
| `0.11.6` | 6 | Frontend error copy + changelog; line complete. |

Each row updates `docs/changelog.md` on completion (per `CLAUDE.md`).

---

## Risks & watch-items

| Risk | Mitigation |
|---|---|
| **Orphan subprocess** after `kill()` | `spawn` context; reap zombies; log child pid; consider `maxtasksperchild=1` pool later. |
| **`RLIMIT_AS` ineffective on macOS** | Default `memory_limit_mb=0` locally; enforce on Linux Fly via env; document in deploy runbook. |
| **Subprocess startup latency** | ~50–200ms per run acceptable for v1; flag `toolbench_subprocess_sandbox_enabled=False` only in tests. |
| **Pickle/import side effects in child** | Worker imports `app.toolbench.instruments` explicitly; pass only JSON-safe dicts. |
| **oeis double-timeout** | httpx 10s < wall 30s; retrieval uses `min(httpx_timeout, wall_timeout)`. |
| **503 vs 429 semantics** | Use **503** (machine capacity), not rate-limit per user — revisit with agent loop. |
| **512mb Fly + 256mb child + 2 concurrent** | Tune defaults after Phase 5 logs; may drop to `max_concurrent_runs=1` in fly.toml env. |
| **Regression of `0.9.7` security** | No second parse path; child uses same instrument code; AST gate unchanged. |

---

## Verification matrix

| Phase | Backend | Frontend | DB |
|---|---|---|---|
| 1 | `ruff` + `test_execution_policy.py` | — | none |
| 2 | `test_subprocess_runner.py` | — | none |
| 3 | `pytest tests/toolbench/` | — | API round-trip recommended |
| 4 | full toolbench + safety tests | — | throwaway Postgres |
| 5 | write-path blame tuple tests | — | throwaway Postgres |
| 6 | full `pytest` | `typecheck` + `lint` + `build` | manual flagship + timeout check |

**Throwaway Postgres recipe** (same as `0.10.x`):

```bash
docker run -d --name opentheory-pytest-throwaway \
  -e POSTGRES_USER=opentheory -e POSTGRES_PASSWORD=opentheory \
  -e POSTGRES_DB=opentheory_test -p 54329:5432 postgres:16-alpine
TEST_DATABASE_URL='postgresql+asyncpg://opentheory:opentheory@127.0.0.1:54329/opentheory_test' \
  uv run pytest -q
docker rm -f opentheory-pytest-throwaway
```

---

## Appendix A — Manual timeout check

1. Sign in as a project member.
2. Run `calc.eval` with a benign input (`2+2`) — should succeed quickly; blame tuple shows
   `resource_used.wall_ms`.
3. In a **local/dev** environment with a test sleep instrument, or a deliberately extreme input
   documented in Phase 4 tests, confirm:
   - UI shows the resource-limit message (Phase 6).
   - No new checkpoint appears on the timeline.
4. Re-run flagship step 1 (geometry) to confirm normal path unaffected.

---

## Appendix B — What comes after `0.11.x`

1. **`0.12.x`** — thin agent loop (Research crew → instrument runs on a thread).
2. **Z3 instrument** — still Tier 0 in-process; inherits sandbox automatically.
3. **Tier 1 retrieval** — Crossref / arXiv pins.
4. **Full microVM substrate** — when Lean or arbitrary agent code execution is required
   (`agent-research-tools.md` §6).

See `docs/plans/roadmap-next-steps.md`.