# `0.12.2` — Thin Agent Loop Phase 3: The bounded orchestrator + agent-branch selection

> **Status — completed (2026-07-06).** Phase 3 of
> [`docs/executing/thin-agent-loop-0.12-implementation-plan.md`](../executing/thin-agent-loop-0.12-implementation-plan.md).
> A real pass now lands attributed checkpoints on the (reused-or-forked) agent branch, safety-cap
> bounded, with a full `AgentRun` trace — driven at the **service layer** (no HTTP yet). **Next:**
> Phase 4 (`0.12.3`) — the API surface + background execution.

## What this phase delivered

| Deliverable | State |
|---|---|
| `services/checkpoints.py::latest_thread_checkpoint` — the fork-point query | Shipped |
| `services/agent_runs.py::select_agent_branch` — reuse / fork / main-line fallback | Shipped |
| `services/agent_runs.py::run_agent_pass` — the bounded, fully-traced orchestrator | Shipped |
| `BudgetPolicy` Protocol — the project-budget seam (Decision #4; v1 passes `None`) | Shipped |
| `AgentLlmError.tokens_used` — honest spend on a parse failure (small `llm.py` add) | Shipped |
| `tests/agent/test_orchestrator.py` (7 tests, DB-backed) | Written — **manual gate** |

No schema change (the `AgentRun` table shipped in `0.12.0`). No route yet, no frontend.

## The orchestrator in one paragraph

`run_agent_pass(db, agent_run_id, *, llm=None, planner=default_plan, budget_policy=None)` loads the
pre-created `running` row (the single source of truth for `project_id` / `thread_id` / `role`),
resolves the project's agent Actor, resolves the role's model, calls the planner **once**, then — only
if the plan has runnable steps — selects the agent branch and executes each step through the **same**
`run_instrument` chokepoint humans use, attributed to the agent Actor, catching per-step failures.
Every step is recorded on the mutable `AgentRun` trace; the pass finalizes `completed` or `failed`.

## Files created / modified

### `backend/app/services/checkpoints.py` — `latest_thread_checkpoint`

The fork-point query: the newest **main-line** (`branch_id IS NULL`) checkpoint on a thread, or
`None`. It deliberately ignores checkpoints already on a branch (e.g. a closed prior agent line), so
an agent branch always forks from the thread's main line. `None` → the main-line fallback.

### `backend/app/services/agent_runs.py` — the orchestrator

**`select_agent_branch(db, project_id, thread_id, agent_actor, *, role) -> UUID | None`** — Decision
#2:
1. **Reuse** — the newest `OPEN` branch referenced by any `AgentRun` on this thread (join
   `agent_runs → branches`). The trace table is the provenance index for "which branches are agent
   branches," so no author column or naming hack is needed. This is what keeps a **durable line of
   inquiry** across passes instead of proliferating branches.
2. **Fork** — else a fresh agent branch off `latest_thread_checkpoint`, attributed to the agent
   Actor (`create_branch`).
3. **Main-line fallback** — else `None`.

**`run_agent_pass(...)`** — the core loop. Key properties, each honoring a standing invariant:

- **One write path / failure split.** The ledger is reached only via `run_instrument` (which runs
  the instrument *before* any `db.add`, so a failed run mints nothing) and `create_branch`. A failed
  step is a recorded trace entry, not a checkpoint.
- **A sequence of atomic transactions, not one.** Each `run_instrument` → `create_checkpoint` owns
  its own commit; the trace is committed *separately* after each step. A later failed step never
  rolls back an earlier durable checkpoint.
- **Controlled failures are recorded, not raised.** An unassigned role and a planner `AgentLlmError`
  both finalize `status=failed` with a legible `error` and mint nothing — never a `500`. A truly
  unexpected exception is caught by an outer guard that rolls back the partial tail and records
  `failed`, so the row never dangles `running`.

**`BudgetPolicy` (Protocol)** — the Decision #4 seam. `check(*, tokens_used, ran_count) -> bool`. v1
passes `None` (the per-pass safety caps bound blast radius); a future orchestrator agent injects a
**project-budget**-derived policy here — never per-thread.

### Two deliberate design decisions (deviations from the plan's letter, with rationale)

1. **Fork *after* planning, not before.** The plan's architecture diagram forks the branch (step 3)
   *before* the planner (step 4). But `create_branch` mints a checkpoint — so forking first would
   leave a **branch-creation checkpoint on a planner failure**, violating the acceptance bar's
   "a malformed plan mints nothing." The orchestrator therefore forks **only after** a successful
   plan with runnable steps. Consequences: a planner failure and an empty plan mint *nothing*, and
   no-op passes never create stray branches. Branch **reuse** across passes is unaffected — it is a
   query (mints nothing) and still resolves the durable agent line.

2. **`run_agent_pass` reads context from the row, not from params.** The plan's signature threaded
   `project_id` / `thread_id` / `triggered_by` / `role` as arguments. Since the `AgentRun` row
   already carries all of them (and is the single source of truth), the orchestrator takes just
   `agent_run_id` and reads the rest — exactly what the `0.12.3` background entrypoint needs (it only
   has the id). Less parameter/row drift, one source of truth.

### `backend/app/agent/llm.py` + `planner.py` — honest spend on failure

`AgentLlmError` gained an optional `tokens_used` (default `0`). The planner attaches
`response.tokens_used` when a *completed* call parses badly, so the orchestrator records the spend on
the failed trace instead of losing it. A pre-completion failure (missing key, timeout, down provider)
stays `0`.

## The trace shape (what a poll sees)

Each `AgentRun` accumulates `steps` — `dropped_invalid` records seeded from the planner, then
`landed` / `failed` (/ `skipped` for a future budget stop) records as execution proceeds:

```json
{"index": 0, "instrument": "counterexample.search", "inputs": {...},
 "claim_id": "…", "relation_kind": "weaken", "rationale": "…",
 "status": "landed", "checkpoint_id": "…", "evidence_id": "…", "outcome": "refuted",
 "error": null, "reason": null}
```

**Implementation note (a real trap avoided):** `AgentRun.steps`/`plan` are plain `JSON` columns (no
`MutableList`/`MutableDict`), so SQLAlchemy does **not** track in-place mutation. The orchestrator
**reassigns** a fresh object on every update (`agent_run.steps = list(steps)`); an `.append(...)`
would be silently dropped and never persist for the poller.

## Tests (`tests/agent/test_orchestrator.py`, 7, DB-backed — the manual gate)

Driven with a **stub planner** (a canned `PlanResult` — no LLM), while `run_instrument` and the
chokepoint run for real:

| Test | Asserts |
|---|---|
| happy path | a `counterexample.search` on a claim lands a checkpoint **+ evidence on the agent branch**; `Checkpoint.author_id == agent_actor` (type `AGENT`, "Research crew"), `Checkpoint.branch_id == branch_id`, `Contribution.action == "tool_run"`, `AgentRun.status == completed`. |
| failure split | a 2-step plan whose 2nd targets a non-existent claim → 1st `landed`, 2nd `failed`, pass `completed`, **exactly one** `tool_run` (no orphan for step 2). |
| safety cap | real planner + `StubLlm` proposing 10 runs, `agent_pass_max_runs=3` → exactly 3 landed, 7 `max_runs` drops, `planned_count == 10`. |
| branch reuse | two passes land on the **same** branch; after `close_branch(dead_end)`, a third **forks a new** branch. |
| main-line fallback | a thread with no checkpoint → `branch_id is None`, the run lands on the main line. |
| unassigned role | finalize `failed` ("no model assigned"), planner never called, **no** `tool_run`. |
| planner failure | `AgentLlmError` → `failed` ("planner failed"), `tokens_used` recorded, **no** `tool_run`. |

## Verification

```bash
cd backend && uv run ruff check .                  # All checks passed
cd backend && uv run pytest -q                      # 196 passed, 112 skipped (no DB)
```

DB-free this session: ruff clean; the app boots with the orchestrator; the full suite is green and
the 7 orchestrator tests **collect and skip cleanly** (imports/syntax validated).

### Manual gate (deferred — needs Postgres)

The 7 orchestrator tests are the real proof of Phase 3 and must be run before trusting the line.
They exercise exactly the DB-specific behaviours that can't be checked without a database — and which
this session could not run:

```bash
cd backend && TEST_DATABASE_URL='postgresql+asyncpg://…@localhost:5432/opentheory_test' \
  uv run pytest tests/agent/ -q
```

Specifically confirm: (a) the `get_or_create_project_agent_actor` `begin_nested` savepoint composes
inside `run_agent_pass`'s transaction; (b) the `JSON`-column **reassignment** persists `steps`/`plan`
across the per-step commits; (c) the `agent_runs → branches` **reuse join** resolves the open agent
line; and (d) the failure-split step leaves **no orphan checkpoint**.

## Standing invariants — honoured

- **One write path / failure split / append-only:** ledger reached only via `run_instrument` +
  `create_branch`; failed/empty/planner-failed passes mint nothing; the `AgentRun` trace is the one
  deliberately-mutable non-ledger object.
- **Human-first / roles separate:** the agent Actor authors (`tool_run` contributions); it never
  funds or self-validates. Budget is a project-level seam (`BudgetPolicy`), never conflated with
  authorship, never per-thread.
- **Stages optional:** the thread `stage` reaches the planner only as a prompt hint; the pass never
  reads or mutates it.
