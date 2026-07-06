# `0.12.x` — Thin Agent Loop · Implementation Plan (decision-settled)

> **Status — ready to implement (2026-07-06).** This is the *methodical, follow-along* plan for the
> `0.12.x` line. It supersedes the open decisions in the design proposal
> [`thin-agent-loop-0.12.md`](./thin-agent-loop-0.12.md) with the user's settled calls (below); that
> proposal stays as the design rationale (invariant analysis, risk table, architecture narrative).
> Prerequisite `0.11.x` Execution Sandbox is **complete** (`0.11.8`,
> `docs/archive/execution-sandbox-0.11.md`). Depends conceptually on
> `docs/plans/agent-research-tools.md` (§8 build order, human-first rule) and
> `docs/research-flow.md` (stage semantics — used only as planner **hints**, never enforced).

## What we are building (one paragraph)

A signed-in project **member** clicks **Run agent pass** on a thread. The backend resolves the
project's single **agent `Actor`** and the OpenRouter **model** assigned to the chosen Research-crew
role, then runs **one bounded pass**: a single LLM planning call turns *(thread + open claims +
instrument catalog)* into a validated, capped plan of **existing** instrument runs; the orchestrator
executes each run through the **same** `run_instrument` chokepoint humans use — attributed to the
agent Actor, landing real checkpoints/evidence on a durable **agent branch** (the line of inquiry) —
catching per-run failures so one bad step never aborts the pass. Every pass writes an `AgentRun`
trace (plan, what landed, what failed, tokens/runs). The human then **accepts** (validate), **rejects**
(`close_branch(dead_end)`), or **branches further**. No parallel data model, no new write path, no
autonomous/continuous loop.

---

## Settled decisions (the four forks, now closed)

| # | Decision | Call | Consequence baked into this plan |
|---|---|---|---|
| 1 | **Loop shape & execution** | **Single planning call → deterministic execution in a request-scoped `BackgroundTask` with its own session; `POST` returns `202` immediately; frontend polls the trace.** | Robust to multi-second LLM latency without external worker infra. `AgentRun` is a **mutable live trace** (not append-only); the ledger writes it triggers *are* append-only via the chokepoint. |
| 2 | **Where agent work lands** | **A durable agent branch = one line of inquiry, pursued until proven/disproven.** Reuse the thread's *open* agent branch across passes; fork a new one only when none is open; main-line fallback (`branch_id=None`) only when the thread has zero checkpoints to fork from. | Branch **selection** is the orchestrator's job (§0.12.2). Agent branches are identified via the `AgentRun` table (Branch has no author column). "Reject" = `close_branch(dead_end)`; true **merge** stays out of scope (`BranchStatus.MERGED` reserved). |
| 3 | **Agent identity granularity** | **One account-less `Actor(type=agent)` per project** (`display_name="Research crew"`), created lazily on first pass. | Role + model recorded on the `AgentRun` and the `tool_run` contribution metadata, not in separate identities. |
| 4 | **Budget** | **Budget is a *project-level* concern, never per-thread.** v1 keeps per-pass caps as **safety** (blast-radius), records token usage, and defers project-budget metering to `0.12.5`. A future **orchestrator agent** (not built here) will read the project budget and dynamically allocate per-subagent limits. | The orchestrator exposes a **budget-policy seam** (§0.12.2/§0.12.5) so the future orchestrator injects allocations without touching the write path. **No per-thread budget assumptions anywhere.** |

`★ Insight ─────────────────────────────────────`
The cleanest structural consequence of Decision 2 is that **`AgentRun` becomes the source of truth
for "which branches are agent branches."** The `Branch` row carries no author, so rather than hack a
naming convention or add a column, the orchestrator answers *"does this thread have an open agent
line?"* by joining `agent_runs → branches` on `branch_id` where `branches.status = 'open'`. The trace
table earns a second job — provenance index — for free.
`─────────────────────────────────────────────────`

---

## The reuse spine (verified present — this line invents no ledger mechanics)

| Existing piece | Location (verified) | The loop's use |
|---|---|---|
| `run_instrument(db, project_id, instrument, actor, *, inputs, assumptions=None, thread_id=None, branch_id=None, claim_id=None, relation_kind=None) -> ToolRunResult` | `services/tool_runs.py:94` | **The single write call.** Called with the agent Actor. Same failure split, blame tuple, `tool_run` contribution. Validates `inputs` against `instrument.InputModel` internally. |
| `create_checkpoint` (chokepoint, owns the one commit) | `services/checkpoints.py:219` | Untouched — reached only via `run_instrument` / `create_branch`. |
| `create_branch(db, project_id, payload: BranchCreate, actor)` / `close_branch(db, branch_id, payload: BranchClose, actor)` | `services/branches.py:53,129` | Fork the agent line (attributed to agent Actor); reject = `close_branch(dead_end)`. `create_branch` **requires an existing fork checkpoint** (404 otherwise) → mandates the main-line fallback. |
| `ensure_is_member(db, project_id, actor) -> Project` | `services/project_members.py:95` | Route-level gate: the **commissioning human's** membership authorizes the pass. |
| `registry.get(name) -> Instrument | None` / `build_catalog(registry=None)` | `toolbench/registry.py:40`, `toolbench/catalog.py:45` | Resolve each planned instrument (owns the 404 semantics); catalog is the planner's tool menu. |
| `project.agent_models: dict` + `AGENT_ROLE_FIELDS=("research_lead","thread_manager","researcher","research_assistant")` + `VALID_MODEL_IDS` | `models/project.py:34`, `schemas/project.py:17`, `core/openrouter_models.py` | role→model roster, already stored/validated; the loop **reads** it. |
| `Actor(type=ActorType.AGENT)` — `account_id` nullable, `display_name`, `actor_metadata` JSON | `models/actor.py`, `models/enums.py:6` | First production **creation path** for an agent Actor. |

**Net-new (all additive):** OpenRouter client (`app/agent/llm.py`), agent settings (`core/config.py`),
agent-actor provisioning (`services/agent_actors.py`), the planner (`app/agent/planner.py`), the
orchestrator (`services/agent_runs.py`), the `AgentRun` trace model + schemas + routes + migration
`0013`, and the workspace UI.

---

## Architecture (target state, decision-settled)

```
POST /projects/{id}/threads/{thread_id}/agent-runs        (member-gated; 404 if agent_loop_enabled off)
        │  ActingActor = commissioning human;  ensure_is_member(project, human)
        │  body: { role }               role ∈ AGENT_ROLE_FIELDS; 422 if unassigned in agent_models
        ▼
services/agent_runs.start_agent_pass(db, project_id, thread_id, triggered_by, role)
        │  writes AgentRun(status=running) in the REQUEST session, commits, returns its id
        │  ── response: 202 Accepted + AgentRunRead(running) ── request session closes here
        │
        └─► BackgroundTask → run_agent_pass_background(agent_run_id)
              async with AsyncSessionLocal() as db:          # its OWN session
                1. agent_actor = get_or_create_project_agent_actor(db, project_id)
                2. model       = project.agent_models[role]                 (422→fail trace if unset)
                3. branch_id   = select_agent_branch(db, project_id, thread_id, agent_actor)
                       reuse latest OPEN agent branch on the thread  (via agent_runs join)
                       else fork new agent branch off latest thread checkpoint
                       else branch_id = None  (thread has no checkpoint — main-line fallback)
                4. plan        = await planner.plan(thread, open_claims, build_catalog(), model,
                                                    llm=OpenRouterClient(), max_runs=cap)   ← the ONE LLM call
                       validate each step: registry.get(name)  +  InputModel.model_validate(inputs)
                       drop+record unrunnable steps; truncate to agent_pass_max_runs
                5. for step in plan.runnable_runs:                          (safety cap already applied)
                       try:  result = await run_instrument(db, project_id, instrument, agent_actor,
                                                          inputs=…, thread_id=…, branch_id=branch_id,
                                                          claim_id=…, relation_kind=…)
                             step → landed (checkpoint_id, evidence_id, outcome)
                       except HTTPException as e:  step → failed (mints nothing)
                6. AgentRun(status=completed|failed, ran_count, tokens_used, steps=[…], branch_id)
```

Each landed run is its **own atomic transaction** (each `run_instrument`→`create_checkpoint` owns one
commit). The pass is a **sequence** of atomic runs, not one giant transaction — so a later failed step
never rolls back an earlier durable result. The `AgentRun` trace row is updated (mutably) as steps
complete.

---

## Phase plan (each phase independently shippable; update `docs/changelog.md` on completion)

Dependency order: **0.12.0 → 0.12.1 → 0.12.2 → 0.12.3 → 0.12.4**. **0.12.5 (project-budget
metering) is a stretch** that depends only on 0.12.2 and can slot before or after 0.12.4 — the thin
line is demoable without it because the per-pass safety caps already bound blast radius.

Legend for task files: **[new]** create, **[mod]** modify.

---

### `0.12.0` — Foundations: settings, OpenRouter client, agent Actor, trace table

**Goal:** config, LLM client, agent identity, and the (empty, migrated) trace table exist. No loop
yet; flag off; zero behaviour change.

**Files**

- **[mod]** `app/core/config.py`, `backend/.env.example`, `docs/deploy.md`
- **[new]** `app/agent/__init__.py`, `app/agent/llm.py`
- **[new]** `app/services/agent_actors.py`
- **[new]** `app/models/agent_run.py`; **[mod]** `app/models/__init__.py`, `app/models/enums.py`
- **[new]** `alembic/versions/0013_agent_runs.py`
- **[new]** `app/schemas/agent_run.py`

**Tasks**

1. **Settings** (mirror the existing `toolbench_*` group in `core/config.py:46`):
   - `openrouter_api_key: str | None = None`
   - `openrouter_base_url: str = "https://openrouter.ai/api/v1"`
   - `agent_llm_timeout_s: float = 60.0`
   - `agent_pass_max_runs: int = 5`  *(safety cap — blast radius, not budget)*
   - `agent_pass_max_tokens: int = 200_000`  *(cap on the planning call; recorded usage)*
   - `agent_loop_enabled: bool = False`  *(dark-launch flag; prod flips it when ready)*
   - Add matching `.env.example` entries. In `docs/deploy.md` note **`OPENROUTER_API_KEY` is a Fly
     secret** (`fly secrets set`), never `fly.toml [env]`; `AGENT_LOOP_ENABLED` is set when launching.
   - Add a comment block: *"per-pass caps are safety limits; real budget is project-level (`0.12.5`)."*
2. **OpenRouter client** — `app/agent/llm.py`, reusing the retrieval `Fetcher` posture
   (`toolbench/retrieval.py`):
   - `@dataclass LlmResponse: text: str; tokens_used: int; model: str`
   - `class AgentLlmError(Exception)` — typed failure (down provider / timeout / non-2xx / no content)
     so a route maps it to `422`/`503`, **never `500`**.
   - `class OpenRouterClient` with `async def complete(self, *, model: str, messages: list[dict],
     response_format: dict | None = None, timeout: float | None = None) -> LlmResponse`.
   - One `httpx.AsyncClient` `POST {base_url}/chat/completions`, `Authorization: Bearer {key}`,
     `max_tokens=agent_pass_max_tokens`. Parse `choices[0].message.content` + `usage.total_tokens`.
     `AgentLlmError` on `httpx.TimeoutException`, non-2xx, empty/malformed body, or missing key.
   - Keep it a thin protocol so the planner takes an injectable `llm` (a `StubLlm` in tests).
3. **Agent-actor provisioning** — `services/agent_actors.py`:
   - `async def get_or_create_project_agent_actor(db, project_id: UUID) -> Actor` — **idempotent**.
     Look up `Actor` where `type=AGENT` and `actor_metadata->>'project_id' == str(project_id)`;
     create if absent with `type=ActorType.AGENT`, `account_id=None`,
     `display_name="Research crew"`, `actor_metadata={"project_id": str(project_id)}`.
   - `db.add` + `flush` (no commit — composes with the caller's transaction). Guard the race with a
     `flush`-then-refetch or a partial unique index (see task 5) so concurrent first passes can't mint
     two agent actors.
4. **Model + enum**:
   - `models/enums.py`: `class AgentRunStatus(StrEnum): RUNNING="running"; COMPLETED="completed"; FAILED="failed"`.
   - `models/agent_run.py`: `class AgentRun(IdMixin, TimestampMixin, Base)` — `__tablename__="agent_runs"`:
     | Column | Type | Notes |
     |---|---|---|
     | `project_id` | FK `projects.id` `CASCADE`, indexed, not null | |
     | `thread_id` | FK `threads.id` `CASCADE`, indexed, not null | the commissioned thread |
     | `branch_id` | FK `branches.id` `SET NULL`, nullable | the agent line; `NULL` = main-line fallback |
     | `agent_actor_id` | FK `actors.id`, not null | the authoring agent Actor |
     | `triggered_by_actor_id` | FK `actors.id`, not null | the commissioning human |
     | `role` | `String(40)`, not null | one of `AGENT_ROLE_FIELDS` |
     | `model` | `String(120)`, not null | resolved OpenRouter model id |
     | `status` | `Enum(AgentRunStatus, name="agent_run_status")`, default `RUNNING` | mutable |
     | `plan` | `JSON`, default `dict` | the raw validated `AgentPlan` |
     | `steps` | `JSON`, default `list` | per-step trace (shape below) |
     | `planned_count` | `Integer`, default `0` | steps the model proposed |
     | `ran_count` | `Integer`, default `0` | steps that reached `run_instrument` |
     | `tokens_used` | `Integer`, default `0` | planning-call usage (future: cumulative) |
     | `error` | `Text`, nullable | pass-level failure reason |
   - **Step JSON shape** (documented in a module docstring): `{"index", "instrument", "inputs",
     "claim_id", "relation_kind", "rationale", "status": "landed|failed|dropped_invalid",
     "checkpoint_id", "evidence_id", "outcome", "error"}`.
   - **`AgentRun` is deliberately NOT in `models/append_only.py`** — it is a live, mutable trace
     (running→completed/failed). Add a one-line comment saying so, to preempt a future reviewer
     "wiring it into the guards for consistency."
   - **Export `AgentRun` from `models/__init__.py` `__all__`** (Alembic discovery — a model missing
     from `__all__` is silently absent from autogenerated migrations).
5. **Migration `0013_agent_runs`** — additive: `create_table("agent_runs")` + the named
   `agent_run_status` enum. Add the **partial unique index** for agent-actor idempotency
   (`CREATE UNIQUE INDEX ... ON actors ((actor_metadata->>'project_id')) WHERE type='agent'`) — decide
   here vs. an app-level guard; the index is the durable answer. No backfill. Verify `upgrade`/
   `downgrade` round-trip.
6. **Schemas** — `schemas/agent_run.py`: `AgentRunRead` (full trace) and `AgentRunSummary` (list view),
   both `ConfigDict(from_attributes=True)`.

**Tests**

- `tests/agent/test_llm_client.py` (DB-free) — stubbed `httpx` transport: success returns text +
  `tokens_used`; timeout and non-2xx raise `AgentLlmError`; missing key raises `AgentLlmError`.
- `tests/agent/test_agent_actors.py` (DB-backed, `TEST_DATABASE_URL`) — first call creates, second
  returns the same actor id (idempotency); a simulated concurrent create does not mint two.
- `tests/agent/test_migration_0013.py` or the existing migration harness — up/down round-trip.

**Exit criteria:** `alembic upgrade head` clean; `ruff` clean; new unit tests green; app boots with
`agent_loop_enabled=False` and **no observable behaviour change**.

---

### `0.12.1` — The planner (pure, injectable, no writes)

**Goal:** *(thread + open claims + catalog)* → a **validated, bounded** `AgentPlan`, deterministically
testable with a stub LLM. No DB writes, no network in tests.

**Files:** **[new]** `app/agent/planner.py`, `app/agent/prompts.py`; **[new]** `tests/agent/`
fixtures + `StubLlm`.

**Tasks**

1. **Plan schemas** in `planner.py` (or `schemas/agent_run.py`):
   - `class PlannedRun(BaseModel): instrument: str; inputs: dict[str, Any]; claim_id: UUID | None = None;
     relation_kind: str | None = None; rationale: str`
   - `class AgentPlan(BaseModel): runs: list[PlannedRun]`
2. **Prompt builder** — `app/agent/prompts.py`:
   - System prompt: the loop's contract — *"You plan a short sequence of deterministic instrument runs
     to make progress on a research thread. You may only choose instruments from the provided catalog.
     Return JSON matching the schema. Prefer runs that target an open claim. It is valid to return an
     empty plan if no instrument helps."*
   - User prompt: thread question + `stage` (labelled a **hint**, not a rule); each open claim
     (`id`, `kind`, `status`, text); and `build_catalog()` rendered as the tool menu (name,
     `input_schema`, the three-outcome contract). **Explicitly note** claim/thread text is untrusted
     content — the model's only power is picking from the fixed menu (structural anti-injection).
3. **`plan(...)`** — `async def plan(thread, open_claims, catalog, model, *, llm, max_runs) -> tuple[AgentPlan, list[dict], int]`
   returning *(validated runnable plan, dropped-step records, tokens_used)*:
   - Call `llm.complete(model=model, messages=…, response_format={"type":"json_object"},
     timeout=settings.agent_llm_timeout_s)`.
   - Parse JSON → `AgentPlan`; non-JSON / schema-invalid → raise `AgentLlmError` (the orchestrator
     records it and mints nothing).
   - **Two-stage validation** per run: `registry.get(instrument)` (unknown → drop, record
     `{"reason":"unknown_instrument"}`); `instrument.InputModel.model_validate(inputs)` (invalid →
     drop, record `{"reason":"invalid_inputs","detail":…}`). Enforce `relation_kind ⇒ claim_id`
     (drop otherwise — mirrors `run_instrument`'s own rule, fail before execution).
   - **Truncate** runnable runs to `max_runs`; record truncation as a dropped record with
     `{"reason":"max_runs"}`.
4. **Test doubles** — `StubLlm(canned_json: str | Exception)` implementing the same `complete`
   protocol; fixture thread + claims + a real `build_catalog()`.

**Tests (all DB-free):**

- valid plan → validated & bounded; targets resolve.
- unknown instrument / bad inputs / `relation_kind` without `claim_id` → those steps **dropped &
  recorded**, not raised; runnable remainder returned.
- non-JSON / schema-mismatch → `AgentLlmError` surfaced.
- empty plan ("nothing to do") is a **valid** outcome (0 runnable, no error).
- `max_runs` truncation recorded.

**Exit criteria:** planner emits a validated plan from a fixture thread with an injected `StubLlm` —
no network, no DB; branch coverage on the drop/truncate paths.

---

### `0.12.2` — The bounded orchestrator + agent-branch selection (service layer)

**Goal:** a real pass lands attributed checkpoints on the (reused-or-forked) agent branch, safety-cap
bounded, with a full trace — driven at the **service layer** (no HTTP yet).

**Files:** **[new]** `app/services/agent_runs.py`; **[mod]** `app/services/checkpoints.py` (small
query helper if needed).

**Tasks**

1. **Branch-selection helper** — `select_agent_branch(db, project_id, thread_id, agent_actor) -> UUID | None`
   implementing Decision 2:
   - **Reuse:** latest branch with `status=OPEN` referenced by an `AgentRun` for this `thread_id`
     (join `agent_runs.branch_id → branches.id`, `branches.status='open'`, order by `branches.created_at desc`).
   - **Fork:** else the latest checkpoint on the thread (`_latest_thread_checkpoint`, task 2) →
     `create_branch(BranchCreate(from_checkpoint_id=…, thread_id=…, name=f"Agent line · {role}",
     reason="agent pass"), actor=agent_actor)`; return its id.
   - **Main-line fallback:** else `None` (thread has no checkpoint to fork from) — the trace records it.
2. **`_latest_thread_checkpoint(db, project_id, thread_id) -> Checkpoint | None`** — a small query
   (mirror `list_checkpoints` ordering; latest by `created_at`, main-line preferred). Place in
   `services/checkpoints.py` if not cheaply inline.
3. **`run_agent_pass(db, project_id, thread_id, *, triggered_by, role, agent_run_id, llm=None,
   planner=<default>, budget_policy=None) -> AgentRun`** — the core:
   - Load the `AgentRun(running)` row by `agent_run_id` (created by the route in 0.12.3; in the
     service test it's created inline).
   - `agent_actor = await get_or_create_project_agent_actor(db, project_id)`; stamp `agent_actor_id`.
   - `model = project.agent_models.get(role)`; if falsy → finalize `status=failed`,
     `error="role '{role}' has no model assigned"`, return (no LLM call, mints nothing).
   - `branch_id = await select_agent_branch(...)`; stamp on the row.
   - `plan, dropped, tokens = await planner.plan(thread, open_claims, build_catalog(), model,
     llm=llm or OpenRouterClient(), max_runs=settings.agent_pass_max_runs)` inside `try/except
     AgentLlmError` → on error finalize `status=failed`, record `error`, `tokens_used`, keep dropped;
     mints nothing. Persist `plan`, `planned_count`, seed `steps` with dropped records.
   - **Execute loop** over runnable runs (already `≤ max_runs`); `budget_policy` seam (v1 default =
     `None` = safety-cap-only; §0.12.5 supplies a project ceiling):
     ```
     for step in runnable:
         instrument = registry.get(step.instrument)      # re-resolve in-session
         try:
             result = await run_instrument(db, project_id, instrument, agent_actor,
                                           inputs=step.inputs, thread_id=thread_id,
                                           branch_id=branch_id, claim_id=step.claim_id,
                                           relation_kind=step.relation_kind)
             record step landed: checkpoint_id, evidence_id, outcome=result.outcome
             ran_count += 1
         except HTTPException as e:
             record step failed: error=e.detail   # mints nothing (failure split holds)
     ```
   - Finalize `AgentRun(status=completed, ran_count, tokens_used, steps)`; return.
   - Wrap the whole body so **any** unexpected exception → `status=failed`, `error=…` (never a
     dangling `running` row, never a `500` leaking to the caller).
4. **Budget-policy seam** (Decision 4) — define `class BudgetPolicy(Protocol)` with
   `def check(self, *, tokens_used, ran_count) -> bool` (True = keep going). v1 passes `None`
   (safety caps only). Document that a **future orchestrator agent** supplies a project-budget-derived
   policy here — *no per-thread limits*.

**Tests (DB-backed, `TEST_DATABASE_URL`, stub planner injected — no real LLM):**

- **Flagship happy path:** a plan running `counterexample.search` / `geometry.coordinate_measure` on a
  claim lands a checkpoint **+ evidence on the agent branch**; assert `Checkpoint.author == agent_actor`,
  `Checkpoint.branch_id == branch_id`, `Contribution.action == "tool_run"`, `AgentRun.status==completed`.
- **Failure split:** a 2-step plan whose 2nd step errors → 1st landed, 2nd `failed`, pass `completed`,
  **no orphan checkpoint** for step 2.
- **Safety cap:** a 10-step plan with `agent_pass_max_runs=3` runs exactly 3; trace records the cap.
- **Branch reuse:** two consecutive passes on the same thread land on the **same** branch id (no
  proliferation); after `close_branch(dead_end)`, a third pass forks a **new** branch.
- **Main-line fallback:** a thread with zero checkpoints → first pass lands with `branch_id=None`;
  trace records it.
- **Unassigned role / planner `AgentLlmError`:** finalize `failed`, mints nothing.

**Exit criteria:** `run_agent_pass(...)` produces real ledger checkpoints + a complete `AgentRun`
trace; all branch-selection paths covered.

---

### `0.12.3` — The API surface (+ background execution)

**Goal:** members commission a pass and poll its trace over HTTP; the pass runs in the background.

**Files:** **[new]** `app/api/routes/agent_runs.py`; **[mod]** `app/api/router.py`; **[mod]**
`app/services/agent_runs.py` (add `start_agent_pass` + the background entrypoint).

**Tasks**

1. **`start_agent_pass(db, project_id, thread_id, *, triggered_by, role) -> AgentRun`** — validate the
   thread belongs to the project; resolve the agent actor id lazily is fine, but **write the
   `AgentRun(status=running)` row and commit in the request session**, returning it. (Keep the actual
   pass out of this function.)
2. **Background entrypoint** — `async def run_agent_pass_background(agent_run_id: UUID) -> None`:
   opens `async with AsyncSessionLocal() as db:`, re-loads everything **fresh** in its own session
   (the request session is gone), calls `run_agent_pass(...)`, and **never lets an exception escape**
   (catch-all → `AgentRun(failed, error=…)`, commit). Add structured `INFO`/`WARNING` logs
   (pass start, plan size, each landed checkpoint id, finalize) matching the toolbench logging style.
3. **Routes** (`api/routes/agent_runs.py`):
   - `POST /projects/{id}/threads/{thread_id}/agent-runs` — deps: `ActingActor` (401 unauth) +
     `ensure_is_member` (403 non-member). **`404` when `settings.agent_loop_enabled is False`**
     (dark launch — indistinguishable from "not a route yet"). Body `AgentRunTrigger{role: str}`
     (validate `role ∈ AGENT_ROLE_FIELDS`, else `422`). Call `start_agent_pass`, add
     `BackgroundTasks.add_task(run_agent_pass_background, agent_run.id)`, return **`202`** +
     `AgentRunRead(running)`.
   - `GET /projects/{id}/threads/{thread_id}/agent-runs` → `list[AgentRunSummary]` (newest first).
   - `GET /agent-runs/{id}` → `AgentRunRead` (the poll target).
   - Register the router in `api/router.py`.
4. **Stale-running sweep** (watch-item, cheap v1): on `GET`, mark any `AgentRun(running)` older than a
   TTL (e.g. `2 × agent_llm_timeout_s + margin`) as `failed(error="lost — worker restart?")`. Prevents
   a killed background task from stranding a `running` row forever. (A durable queue is the future
   evolution.)

**Tests:**

- Member gate: `403` non-member, `401` unauth (DB-free where the deps allow, else DB-backed).
- `agent_loop_enabled=False` → `404`.
- Full round-trip (stub planner via a DI/settings seam): `POST` → `202 running`; poll `GET` → flips to
  `completed` with a landed checkpoint id in `steps`.
- Bad `role` → `422`.

**Exit criteria:** `POST …/agent-runs` end-to-end; trace pollable; background failure can never surface
as a `500` or a stuck `running` row.

---

### `0.12.5` — Project-budget metering (stretch; closes funding Decision #6) — **project-scoped, never per-thread**

**Goal:** agent passes debit the **project's** compute budget; the funding panel shows real `spent`;
a pass on an exhausted project stops cleanly. Honors Decision 4: *the limit is on the project, and the
per-pass caps remain pure safety.*

**Files:** **[mod]** `app/services/funding.py`, `app/services/agent_runs.py`, `app/core/config.py`;
possibly **[new]** a lightweight debit model + migration `0014`.

**Tasks**

1. **Confirm current shape** — verify `services/funding.py::project_budget` still hard-codes
   `spent = Decimal("0")` (proposal's funding Decision #6). Adjust the plan to whatever it actually is
   at pickup.
2. **Token → cost** — a per-1k-token rate in `Settings` (or per model tier from `OPENROUTER_MODELS`
   metadata). Record each pass's spend as a **project-scoped debit** — choose at pickup between:
   (a) a lightweight `compute_ledger` row, or (b) `FundingAllocation(kind=adjustment, source=native,
   amount=-cost)` respecting append-only. *(Sub-decision deferred to this phase.)*
3. **`project_budget`** — replace `spent=0` with the sum of debits; expose `available`.
4. **Enforcement via the budget-policy seam (§0.12.2)** — inject a `ProjectBudgetPolicy` into
   `run_agent_pass`: **refuse to start** when `available <= 0` (trace: `failed, error="project budget
   exhausted"`, mints nothing); optionally stop mid-pass between runs when exhausted. **The check is
   against the project total — not the thread.** Leave the seam shaped so the future orchestrator can
   supply per-subagent allocations derived from the project budget.

**Tests (DB-backed):** budget `available` drops by the metered amount after a pass; a pass on an
exhausted project stops with a clear trace and mints nothing; **no per-thread limit is ever consulted.**

**Exit criteria:** funding surface reflects agent spend; passes bounded by real *project* budget; the
per-pass caps unchanged as safety. *(Stretch — the thin line demos without it.)*

---

### `0.12.4` — Frontend: trigger, trace, accept/reject

**Goal:** the loop is drivable and legible from the workspace, in Kamino tone.

**Files:** **[new]** `frontend/src/components/workspace/agent-pass-*` (trigger + trace view);
**[mod]** `frontend/src/lib/api.ts`, `frontend/src/types/…`, `query-keys.ts`, the branch bar,
`docs/changelog.md`, `docs/plans/roadmap-next-steps.md`.

**Tasks**

1. **Trigger** — a member-only **Run agent pass** control on a thread; role picker defaulting to the
   assigned `researcher`; **disabled** when the role has no model or `agent_loop_enabled` is off
   (feature-detect via a `404`/config). `POST` → store the returned `AgentRun` id.
2. **Trace view** — poll `GET /agent-runs/{id}` (TanStack Query `refetchInterval` while `running`):
   render the plan (rationale per step), what **landed** (link each to its checkpoint/evidence card —
   reuse the instrument result-card components), what **failed**, and `ran_count`/`tokens_used` vs the
   caps. Stop polling on `completed|failed`.
3. **Accept / reject / branch** in the existing **branch bar** (reuse shipped write paths):
   - **Reject** → `close_branch(dead_end, reason)` — the recorded dead-end.
   - **Accept** → record a `Validation` on the surviving claim(s) (`0.4.1` surface). *Merge stays out
     of scope — v1 "accept" = validate-in-place / adopt.*
   - **Branch further** → `create_branch` from any landed checkpoint (existing).
4. **API/types plumbing** — typed calls in `lib/api.ts`; mirror `AgentRunRead`/`AgentRunSummary` in
   `types/`; query keys. Map `422`/`503` to Kamino copy (reuse `lib/instrument-run-errors.ts`).
5. **Release ledger** — `docs/changelog.md` index + sections `0.12.0`–`0.12.4`; **move this plan and
   the proposal to `docs/archive/`**; point `docs/plans/roadmap-next-steps.md` at the next line
   (Z3 / Tier-1 retrieval).

**Verification:** `npm run typecheck && npm run lint && npm run build`; manual flagship walkthrough
(below).

**Exit criteria:** an agent pass on *measuring across a corner* lands on the agent branch, the trace
renders with linked result cards, reject closes the branch, and the normal human walkthrough is
unchanged.

---

## Standing invariants — how each phase honors them

| Invariant | How this line honors it |
|---|---|
| **One write path** | The loop reaches the ledger **only** through `run_instrument`→`create_checkpoint` and `create_branch`/`close_branch`. No new checkpoint mint path. |
| **Failure split** | Per-run failures are `HTTPException` from `run_instrument` *before* any `db.add`; the orchestrator catches per step — a failed run mints nothing and is a trace step, not a checkpoint. |
| **Human-first** | Humans already drive `POST …/instruments/{name}/run`; the agent uses the **same** service call. The human **commissions and is accountable** (membership-gated trigger). The agent is `Actor(type=agent)`, not a parallel model. |
| **Funder / contributor / validator separate** | The agent is a **contributor** (`tool_run` contributions, authored checkpoints); it never funds, never self-validates. Budget meters against the **project** (`FundingAllocation`, §0.12.5), never conflated with authorship. |
| **Append-only** | `Checkpoint`/`Validation`/`FundingAllocation` writes stay ORM-guarded. `AgentRun` is a **separate, deliberately mutable trace** — not a ledger primitive. A rejected pass is a `close_branch` **event** (new checkpoint), never a deletion. |
| **Stages optional** | Thread `stage` is a planner **hint** only; never enforced, never mutated by the pass. |

## Anti-injection posture (claim/thread text is untrusted)

The planner's output is **structurally constrained** (validated `AgentPlan`) and every step is
re-validated against the `registry` + `InputModel` before execution. The model can only *pick from the
fixed instrument menu* — it cannot invent an action or reach the DB. The `0.11.x` sandbox still bounds
every individual run. A prompt-injected claim can, at worst, cause a *runnable-but-pointless*
instrument run on the agent branch — which the human then rejects.

## Out of scope (explicit)

- Autonomous / scheduled / continuous research; multi-thread orchestration; the **orchestrator agent**
  that dynamically allocates project budget to subagents (Decision 4 names it as *future*).
- Iterative plan→observe→replan within a pass (v1 is single-plan; the orchestrator is shaped to allow
  it later).
- Branch **merge** mechanics (`BranchStatus.MERGED` reserved) — "accept" = validate-in-place for v1.
- Agents writing arbitrary code / new instruments (needs the microVM substrate).
- New instruments (Z3, `interval.eval`) — independent of this line.
- Reputation / influence; real payment settlement.

## Risks & watch-items

| Risk | Mitigation | Phase |
|---|---|---|
| LLM latency blows the HTTP timeout | Background task + poll; `agent_llm_timeout_s` bounds the single call | 0.12.3 |
| Prompt injection via claim/thread text | Structural plan validation + registry/`InputModel` re-validation; fixed tool menu; sandbox per run | 0.12.1/0.12.2 |
| Runaway invocation rate | `agent_pass_max_runs` + token cap; `toolbench_max_concurrent_runs` semaphore still applies; `agent_loop_enabled` dark launch | 0.12.0/0.12.2 |
| Background task lost on restart | Stale-`running` sweep to `failed` on read; durable worker is the future evolution | 0.12.3 |
| Duplicate agent Actors per project | Idempotent `get_or_create_project_agent_actor` + partial unique index | 0.12.0 |
| Non-JSON / malformed model output | Two-stage validation; a bad plan is a recorded trace outcome that mints nothing — never a `500` | 0.12.1 |
| Branch proliferation across passes | Reuse the thread's open agent branch (Decision 2) | 0.12.2 |
| Cost surprise | Token usage recorded from 0.12.0; per-pass cap bounds a single pass even before 0.12.5 | 0.12.0/0.12.5 |

## Verification gate (per phase, and before prod)

```bash
cd backend && uv run ruff check .
cd backend && uv run pytest -q                                   # DB-free: client / planner / policy
TEST_DATABASE_URL='postgresql+asyncpg://…' uv run pytest tests/agent/ tests/toolbench/ -q
cd frontend && npm run typecheck && npm run lint && npm run build
```

**Before prod:** set `OPENROUTER_API_KEY` (Fly **secret**), flip `AGENT_LOOP_ENABLED=true`; run one
flagship agent pass on staging and confirm a checkpoint lands on the agent branch attributed to the
agent Actor, and reject closes it.

## Manual flagship walkthrough (acceptance)

1. Sign in as a project **member**; assign a model to the `researcher` role (Research crew panel).
2. Open the *measuring across a corner* thread; click **Run agent pass**.
3. Watch the trace: the plan (e.g. `counterexample.search` on claim 2), then the landed checkpoint on
   the **agent branch**; confirm `Checkpoint.author` is the agent Actor and the contribution is
   `tool_run`. Run a **second** pass; confirm it lands on the **same** branch.
4. **Reject** → the branch bar shows it `dead_end`; the reasoning is preserved on the timeline.
5. Re-run the flagship **human** walkthrough to confirm the normal path is unchanged.

## Acceptance bar (definition of done for the line)

On the *measuring across a corner* thread, an agent pass plans and runs `counterexample.search` /
`geometry.coordinate_measure` against claims 1–4, lands checkpoints + evidence on a durable agent
branch attributed to the agent Actor, stays within the per-pass safety cap, records a complete
`AgentRun` trace, and the human can **reject** (`dead_end`) or **accept** (validate) from the
workspace. A pass that hits the cap stops cleanly with a trace showing why; a planned run that errors
is recorded as a failed step and the pass still completes; a malformed model plan mints nothing and is
a legible trace outcome, never a `500`.
