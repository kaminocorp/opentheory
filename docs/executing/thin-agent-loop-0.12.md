# `0.12.x` — Thin Agent Loop (Research crew becomes an operator)

> **Status — proposal (2026-07-06), not started.** Prerequisite `0.11.x` Execution Sandbox
> **completed** (`0.11.8`; `docs/archive/execution-sandbox-0.11.md`). This is the roadmap's
> recommended next line (`docs/plans/roadmap-next-steps.md` §`0.12.x`). Depends on
> `docs/plans/agent-research-tools.md` (§8 build order, the human-first rule) and
> `docs/vision/research-flow.md` (stage semantics — used as **optional hints**, never enforced here).

> Turn the **config-only** Research crew (`0.8.10`) into an operator: a signed-in member
> commissions one **bounded agent pass** on a thread; the agent uses the project's assigned
> OpenRouter model to plan a short sequence of **existing** instrument runs, lands the results on
> the ledger through the **same** chokepoint humans use — attributed to an `agent` `Actor`, isolated
> on an agent branch — and the human accepts, rejects, or branches. No parallel data model, no new
> write path, no autonomous continuous research.

---

## The one thing that makes this "thin"

The entire write / attribution / gating spine **already exists and is directly reusable**. The
agent loop composes it; it invents no ledger mechanics.

| Existing piece | File | The loop's use |
|---|---|---|
| `run_instrument(db, project_id, instrument, actor, *, inputs, assumptions, thread_id, branch_id, claim_id, relation_kind)` | `services/tool_runs.py:94` | **The single call.** The loop calls it directly with an `agent` Actor. Same failure split, same blame tuple, same `tool_run` contribution. |
| `create_checkpoint` (the chokepoint, owns the one commit) | `services/checkpoints.py:219` | Untouched — reached only via `run_instrument`. |
| `create_branch` / `close_branch` | `services/branches.py:53,129` | Agent work lands on a dedicated agent **branch** (isolation); "reject" = `close_branch(outcome="dead_end")`. |
| `ensure_is_member(db, project_id, actor)` | `services/project_members.py:95` | The **commissioning human's** membership authorizes the pass (route-level), exactly as the run route does today. |
| `registry.get(name)` / `build_catalog()` | `toolbench/registry.py`, `toolbench/catalog.py:45` | Resolve the instrument (owns the 404); the catalog is fed to the planner as the agent's tool menu. |
| `projects.agent_models` JSON + `OPENROUTER_MODELS` / `VALID_MODEL_IDS` | `models/project.py:34`, `core/openrouter_models.py` | The role→model roster (`research_lead`, `thread_manager`, `researcher`, `research_assistant`) already stored and validated; the loop *reads* it. |
| `Actor(type=AGENT)` — unconstrained per account, `account_id` nullable | `models/actor.py:21,30` | The data model already anticipates many agent actors; we add the first **creation path**. |

**What is genuinely net-new** (all additive):

| New piece | Where | Why it doesn't exist yet |
|---|---|---|
| OpenRouter client (async httpx → `/chat/completions`, structured output) | `app/agent/llm.py` | Research crew is **config only** — no code calls OpenRouter anywhere in the backend. |
| Settings: `openrouter_api_key`, base URL, per-pass caps | `core/config.py` | No LLM/agent settings exist today. |
| Agent `Actor` provisioning | `services/agent_actors.py` | Only `human` (JIT login) and dev actors are created today; no `agent` path in production. |
| The **planner** — (thread + claims + catalog) → validated plan of instrument runs | `app/agent/planner.py` | The "intelligence" step; the one place an LLM decides. |
| The **orchestrator** — bounded, budget-capped pass on an agent branch | `services/agent_runs.py` | Composes the above with the reuse spine. |
| `AgentRun` trace model + read models + `POST …/agent-runs` | `models/agent_run.py`, `schemas/agent_run.py`, `api/routes/agent_runs.py`, migration `0013` | The "human-visible trace" the roadmap asks for. |
| Frontend trigger + trace + accept/reject | `frontend/src/components/workspace/` | No agent-run UI exists. |

---

## Goal & acceptance bar

A project **member** clicks **Run agent pass** on a thread. The platform:

1. Resolves the project's **agent Actor** and the OpenRouter **model** assigned to the chosen role.
2. Opens an **agent branch** off the thread's latest checkpoint (fork-point fallback below).
3. Calls the **planner** once: the model sees the thread, its open claims, and the instrument
   catalog, and returns a **bounded plan** (≤ `agent_pass_max_runs`) of instrument invocations,
   each optionally targeting a claim.
4. Executes each planned run through `run_instrument(..., actor=agent_actor, branch_id=agent_branch)`
   — landing real, attributed checkpoints — catching per-run failures so one bad run doesn't abort
   the pass.
5. Records an `AgentRun` trace: what was planned, what actually landed (checkpoint ids), what failed,
   and tokens/runs consumed.

**Acceptance bar (the flagship, agent-driven):** on the *measuring across a corner* thread, an agent
pass plans and runs `counterexample.search` / `geometry.coordinate_measure` against claims 1–4,
lands checkpoints + evidence on the agent branch attributed to the agent Actor, stays within the
per-pass cap, and the human can **reject** the branch (`dead_end`) or **accept** its results
(validate) — all from the workspace. A pass that exceeds the budget cap stops cleanly with a trace
showing why; a planned run that errors is recorded as a failed step, and the pass still completes.

---

## Standing invariants (how this line honours them)

| Invariant | How honoured |
|---|---|
| **One write path** | The loop reaches the ledger **only** through `run_instrument` → `create_checkpoint`. No new checkpoint mint path. |
| **Failure split** | Per-run failures are already `HTTPException` from `run_instrument` *before* any `db.add` — the loop catches them per step; a failed planned run mints nothing and is recorded as a trace step, not a checkpoint. |
| **Human-first** | Humans already drive this exact API (`POST …/instruments/{name}/run`). The agent uses the **same** service call; the human **commissions and is accountable** (membership-gated trigger). Agents are not a parallel actor model — they are `Actor(type=agent)`. |
| **Funder / contributor / validator kept separate** | The agent is a **contributor** (`tool_run` contributions, authored checkpoints). It never funds and never self-validates; the human validates. Budget is metered against `FundingAllocation`, not conflated with authorship. |
| **Append-only** | Nothing is edited. A rejected pass is a `close_branch` **event** (a new checkpoint), never a deletion — dead ends are recorded (`primitives.md`). |
| **Stages are optional metadata** | Thread `stage` is passed to the planner as a **hint** to bias tool choice; it is never enforced and the pass never mutates it. |

---

## Decisions (proposed — see "Open decisions" for the forks that need your call)

1. **Human-commissioned, not autonomous.** v1 has no scheduler and no continuous loop. A member
   triggers exactly one pass. (Continuous/scheduled research is explicitly out of scope — roadmap.)
2. **Single planning call per pass, then deterministic execution** (not a multi-turn plan→observe→
   replan loop). One LLM call emits the whole bounded plan; the orchestrator executes it. This keeps
   latency and token cost bounded and the pass trivially testable with a stubbed planner. Iterative
   reflection is a later evolution (`0.12.x+`). *(See Open decision #1.)*
3. **Agent work lands on a dedicated agent branch**, forked from the thread's latest checkpoint.
   Isolation is exactly what branches are for ("parallel exploration and dead ends"), and it gives a
   clean **reject** (`close_branch(dead_end)`). Fallback: if the thread has **no** checkpoint to fork
   from, the first pass lands on the thread main line (`branch_id=None`) and the trace records that.
   *(See Open decision #2.)*
4. **The agent Actor is account-less and per-project.** One `Actor(type=agent, account_id=NULL,
   display_name="Research crew", actor_metadata={"project_id": …})`, created lazily on first pass.
   It is **not** a `ProjectMember` and needs no account: the *commissioning human's* membership is the
   authorization (route gate), and `run_instrument` / `create_checkpoint` attribute to whatever
   `Actor` they are handed without re-checking membership. The agent is an authored identity, not a
   governance principal — mirroring the funder-vs-contributor separation. *(See Open decision #3.)*
5. **Budget = a hard per-pass safety cap in v1**, plus recorded usage; wiring token→spend into the
   funding surface (`FundingAllocation.spent`, today hard-coded `0` — funding service Decision #6)
   is a **separate phase** (`0.12.5`), because it is real accounting, not a safety guarantee.
   *(See Open decision #4.)*
6. **Structured planner output, validated twice.** The model returns JSON validated against an
   `AgentPlan` schema; then every planned instrument name is resolved against the `registry` and its
   `inputs` dry-validated against the instrument's `InputModel` **before** any run. A malformed plan
   fails legibly (recorded on the trace) and mints nothing.
7. **Execution model: kick off as a request-scoped `BackgroundTask` with its own session.** The
   `POST …/agent-runs` route writes the `AgentRun` row `running` and returns its id immediately; the
   pass runs in a FastAPI background task holding its own `AsyncSessionLocal` session (the request
   session is closed at response). The frontend polls the trace. This avoids Fly request-timeout risk
   on multi-second LLM calls without introducing external worker infra. *(See Open decision #1.)*

## Open decisions (need your call before implementation)

1. **Loop shape & execution.** (a) single planning call + synchronous return, (b) single planning
   call + **background task + poll** *(recommended — robust to LLM latency, still thin)*, or
   (c) iterative plan→observe→replan (more "agentic", more tokens, harder to bound). Recommend (b).
2. **Where agent work lands.** Dedicated **agent branch** *(recommended)* vs the thread **main line**
   with agent attribution. The branch gives clean reject-via-close but has **no merge path yet**
   (`BranchStatus.MERGED` is reserved, unimplemented), so "accept" means validate-in-place / adopt,
   with true merge as a follow-on. Main-line avoids the fork-point wrinkle but mixes agent output
   into the canonical line.
3. **Agent identity granularity.** One agent Actor **per project** *(recommended)* vs one **per
   role** (`research_lead`/…). Per-project is simpler; the role + model are recorded on the `AgentRun`
   and the `tool_run` contribution's metadata either way.
4. **Budget in v1.** Hard **per-pass cap only** *(recommended for the thin line)* vs also wire a
   per-project **funding-ledger debit** (close funding Decision #6 now). The latter is `0.12.5`.

---

## Architecture (target state)

```
POST /projects/{id}/threads/{thread_id}/agent-runs   (member-gated)
        │  ActingActor = commissioning human;  ensure_is_member(project, human)
        ▼
services/agent_runs.start_agent_pass
        │  writes AgentRun(status=running), returns id  ── response returns immediately
        │
        └─► BackgroundTask(run_agent_pass) with its own AsyncSessionLocal session:
              1. agent_actor = get_or_create_project_agent_actor(project)
              2. model = project.agent_models[role]           (VALID_MODEL_IDS; 422 if unassigned)
              3. branch  = create_branch(fork = latest thread checkpoint, actor=agent_actor)
              4. plan    = planner.plan(thread, open_claims, build_catalog(), model)   ← the ONE LLM call
                           └─ validate each step: registry.get(name) + InputModel.model_validate(inputs)
              5. for step in plan.runs[:agent_pass_max_runs]:      (budget-capped)
                     try: result = run_instrument(db, project, instrument, agent_actor,
                                                   inputs=…, branch_id=branch.id,
                                                   claim_id=…, relation_kind=…)
                          record step → landed checkpoint id
                     except HTTPException as e: record step → failed (mints nothing)
              6. AgentRun(status=completed|failed, ran_count, tokens_used, steps=[…])
```

Every landed run is its own atomic transaction (each `run_instrument` → `create_checkpoint` owns one
commit); the pass is a **sequence** of atomic runs, not one giant transaction — which is correct, so
a later failed step never rolls back an earlier durable result.

---

## Phase plan

Mirrors the `0.11.x` slicing: each release is independently shippable and demoable, and updates
`docs/changelog.md` on completion (per `CLAUDE.md`).

### `0.12.0` — Foundations: settings, OpenRouter client, agent Actor, trace table

**Goal:** the config, the LLM client, the agent identity, and the (empty) trace table exist; no loop
yet.

**Tasks**
1. **`core/config.py`** — add (mirroring the `toolbench_*` settings group):
   - `openrouter_api_key: str | None = None`
   - `openrouter_base_url: str = "https://openrouter.ai/api/v1"`
   - `agent_llm_timeout_s: float = 60.0`
   - `agent_pass_max_runs: int = 5`
   - `agent_pass_max_tokens: int = 200_000`
   - `agent_loop_enabled: bool = False` (dark-launch flag; production sets it when ready)
   - `.env.example` entries + `docs/operations/deploy.md` note (the key is a **Fly secret**, never `fly.toml [env]`).
2. **`app/agent/llm.py`** — a minimal async client: `async def complete(model, messages, *, response_format, timeout) -> LlmResponse` (text + `tokens_used`), one `httpx.AsyncClient` POST to `{base_url}/chat/completions`, `RetrievalError`-style typed failure (`AgentLlmError`) so a down provider is a clean `422/503`, never a `500`. Reuse the retrieval `Fetcher` posture (`toolbench/retrieval.py`).
3. **`services/agent_actors.py`** — `get_or_create_project_agent_actor(db, project_id) -> Actor`: idempotent (unique on `actor_metadata->>'project_id'` or a dedicated lookup), `type=ActorType.AGENT`, `account_id=None`. Export nothing new from models (Actor already exists).
4. **`models/agent_run.py`** — `AgentRun` (`IdMixin` + `TimestampMixin`): `project_id`, `thread_id`, `branch_id | None`, `agent_actor_id`, `triggered_by_actor_id`, `role`, `model`, `status` (`Enum(AgentRunStatus, name="agent_run_status")` — `running|completed|failed`), `plan` (JSON), `steps` (JSON list), `planned_count`, `ran_count`, `tokens_used`, `error | None`. **Export from `models/__init__.py`** (Alembic discovery). Add `AgentRunStatus` to `models/enums.py`.
5. **Migration `0013_agent_runs`** — additive `create_table` + the named enum. No backfill.
6. **`schemas/agent_run.py`** — `AgentRunRead` / `AgentRunSummary` (`from_attributes=True`).

**Tests (DB-free where possible):** client against a stubbed httpx transport (success + timeout + provider error); `get_or_create_project_agent_actor` idempotency (DB-backed); migration up/down round-trip.

**Deliverable:** `alembic upgrade head` clean; client + actor unit tests green; no behaviour change (flag off).

### `0.12.1` — The planner (pure, injectable, no writes)

**Goal:** given a thread and its claims, produce a **validated, bounded** plan — deterministically
testable with a stub LLM.

**Tasks**
1. **`app/agent/planner.py`** — `async def plan(thread, open_claims, catalog, model, *, llm, max_runs) -> AgentPlan`:
   - Build a system+user prompt: the thread question/stage (hint), each open claim (`kind`, `status`, text), and the instrument catalog (`build_catalog()` — names, `input_schema`, the three-outcome contract) as the tool menu. Instruct the model to return **only** JSON matching `AgentPlan`.
   - `AgentPlan` / `PlannedRun` Pydantic schemas: `runs: list[PlannedRun]`; `PlannedRun{instrument: str, inputs: dict, claim_id: UUID | None, relation_kind: str | None, rationale: str}`.
   - **Two-stage validation:** parse JSON → `AgentPlan`; then for each run `registry.get(instrument)` (drop/flag unknown) and `instrument.InputModel.model_validate(inputs)` (drop/flag invalid) — so the orchestrator only ever executes runnable steps. Truncate to `max_runs`; record dropped steps with a reason.
2. **Prompt fixtures** under `tests/agent/` and a `StubLlm` returning canned JSON.

**Tests (DB-free):** stub returns a valid plan → validated & bounded; stub returns an unknown
instrument / bad inputs → those steps flagged, not raised; stub returns non-JSON → `AgentLlmError`
surfaced (recorded, mints nothing); empty plan ("nothing to do") is a valid outcome.

**Deliverable:** planner emits a validated plan from a fixture thread with an injected stub — no
network, no DB.

### `0.12.2` — The bounded orchestrator + agent branch (service layer)

**Goal:** a real pass lands attributed checkpoints on an agent branch, budget-capped, with a full
trace — driven at the **service** layer (no HTTP yet).

**Tasks**
1. **`services/agent_runs.py`** — `run_agent_pass(db, project_id, thread_id, *, triggered_by, role) -> AgentRun`:
   - Resolve agent Actor + role model (422 if the role is unassigned in `project.agent_models`).
   - Pick the fork point: latest checkpoint on the thread (query mirroring `list_checkpoints`), else `branch_id=None` fallback (Decision #3).
   - `create_branch(...)` (when a fork point exists) attributed to the agent Actor.
   - `planner.plan(...)`; persist the plan on the `AgentRun`.
   - Loop the runnable steps up to `agent_pass_max_runs`, tracking cumulative `tokens_used` against `agent_pass_max_tokens` (stop early when exceeded); each step wrapped in `try/except HTTPException`, recording landed checkpoint id or the failure.
   - Finalize `AgentRun(status=…, ran_count, tokens_used, steps)`.
2. A tiny helper for "latest checkpoint on a thread" in `services/checkpoints.py` if not cheaply expressible inline.

**Tests (DB-backed — `TEST_DATABASE_URL`):** with a **stub planner** injected (no real LLM):
   - A plan running `counterexample.search` on a claim lands a checkpoint + evidence **on the agent
     branch**, `Checkpoint.author` = the agent Actor, `Contribution.action = "tool_run"`.
   - A plan whose 2nd step errors: 1st lands, 2nd recorded failed, pass `completed`, no orphan.
   - Budget cap: a plan of 10 with `agent_pass_max_runs=3` runs exactly 3; trace notes the cap.
   - No-fork-point thread: first pass lands on main line, trace records `branch_id=None`.

**Deliverable:** `run_agent_pass(...)` produces real ledger checkpoints + an `AgentRun` trace.

### `0.12.3` — The API surface (+ background execution)

**Goal:** members commission a pass and read its trace over HTTP.

**Tasks**
1. **`api/routes/agent_runs.py`**:
   - `POST /projects/{id}/threads/{thread_id}/agent-runs` — `ActingActor` + `ensure_is_member` (403 non-member); body `{role}`; **404 if `agent_loop_enabled` is off** (dark launch). Writes `AgentRun(running)`, schedules the pass as a `BackgroundTask` **with its own `AsyncSessionLocal`** (Decision #7), returns `AgentRunRead` (id + `running`) `202 Accepted`.
   - `GET /projects/{id}/threads/{thread_id}/agent-runs` and `GET /agent-runs/{id}` — the trace read models.
   - Register in `api/router.py`.
2. Ensure the background task resolves a **fresh** agent Actor / thread inside its own session (the request session is gone) and never leaks exceptions (any failure → `AgentRun(failed, error=…)`).

**Tests:** member gate (403 non-member, 401 unauth); `agent_loop_enabled=False` → 404; a full
round-trip with a stub planner (via a settings/DI seam) landing a checkpoint and flipping the trace
to `completed`.

**Deliverable:** `POST …/agent-runs` end-to-end; the trace is pollable.

### `0.12.5` — Budget metering into the funding surface (closes funding Decision #6)

**Goal:** agent passes debit the project's compute budget; the funding panel shows real `spent`.

**Tasks**
1. Convert recorded `tokens_used` → a compute cost (a simple per-1k-token rate in `Settings`, per model tier from `OPENROUTER_MODELS` metadata) and record it as a **debit** — either a lightweight `compute_ledger` row or a `FundingAllocation(kind=adjustment, source=native, amount=-cost)` (respecting append-only). *(Model choice is a sub-decision to settle when this phase is picked up.)*
2. `services/funding.py::project_budget` — replace the hard-coded `spent = Decimal("0")` with the sum of debits; enforce a per-project ceiling in `run_agent_pass` (refuse to start / stop mid-pass when `available` is exhausted → the trace records "budget exhausted").
3. **Tests:** budget `available` drops after a pass by the metered amount; a pass on an exhausted
   project stops with a clear trace and mints nothing.

**Deliverable:** the funding surface reflects agent spend; passes are bounded by real budget.
*(Stretch — the thin line is demoable without it; the per-pass safety cap already bounds blast radius.)*

### `0.12.4` — Frontend: trigger, trace, accept/reject

**Goal:** the loop is drivable and legible from the workspace.

**Tasks**
1. **Trigger** — a member-only **Run agent pass** control on a thread (role picker defaulting to the
   assigned `researcher`), disabled when the role has no model or `agent_loop_enabled` is off.
2. **Trace view** — poll `GET /agent-runs/{id}`: show the plan (rationale per step), what **landed**
   (link each to its checkpoint/evidence card), what **failed**, and tokens/runs consumed vs cap.
   console tone; reuse the instrument result-card components.
3. **Accept / reject / branch** — surface the agent branch in the existing **branch bar**:
   **reject** = `close_branch(dead_end)`; **accept** = record a validation on the surviving
   claim(s) (existing validation surface) — merge deferred; **branch** = fork further (existing).
4. **`lib/api.ts`** typed calls; `types/`; `query-keys.ts`. Map `422`/`503` to console copy
   (reuse `lib/instrument-run-errors.ts`).
5. **`docs/changelog.md`** index + sections `0.12.0`–`0.12.4`; move this plan to `docs/archive/`;
   point `docs/plans/roadmap-next-steps.md` at the next line (Z3 / Tier-1 retrieval).

**Verification:** `npm run typecheck && lint && build`; manual flagship walkthrough — an agent pass on
*measuring across a corner* lands on the agent branch, the trace renders, reject closes the branch.

---

## Accept / reject / branch — the human decision (reusing what exists)

| Human action | Mechanism (all shipped) |
|---|---|
| **Reject** the pass | `close_branch(branch_id, outcome="dead_end", reason=…)` — a recorded event, not a deletion. |
| **Accept** a result | Record a `Validation` on the landed claim/checkpoint (existing `0.4.1` write path). True branch **merge** is unimplemented (`BranchStatus.MERGED` reserved) — v1 "accept" = validate-in-place / adopt on the line; merge is the one follow-on gap. |
| **Branch** further | Fork from any landed checkpoint (existing `create_branch`). |

The agent never validates its own work — the validator role stays human, preserving the
contributor/validator separation.

## Out of scope (explicitly)

- Autonomous / scheduled / continuous research; multi-thread project orchestration.
- Iterative plan→observe→replan within a pass (v1 is single-plan) — unless Open decision #1 flips.
- Branch **merge** mechanics (`MERGED`) — a separate line.
- Agents writing *arbitrary code* / new instruments (needs the microVM substrate — `agent-research-tools.md` §6).
- New instruments (Z3, `interval.eval`) — they inherit the sandbox for free when added, independent of this line.
- Reputation / influence scoring; real payment settlement.

## Risks & watch-items

| Risk | Mitigation |
|---|---|
| **LLM latency blows the HTTP timeout** | Background task + poll (Decision #7); `agent_llm_timeout_s` bounds the single call. |
| **Prompt injection via claim/thread text** into the planner | The planner's output is **structurally constrained** (validated `AgentPlan`) and every step is re-validated against the registry + `InputModel`; the model can only pick from the fixed instrument menu — it cannot invent an action or reach the DB. The sandbox (`0.11.x`) still bounds each run. |
| **Runaway invocation rate** (the exact reason the sandbox shipped first) | Per-pass `agent_pass_max_runs` + token cap; `toolbench_max_concurrent_runs` semaphore still applies to every run; `agent_loop_enabled` dark-launch flag. |
| **Background task lost on restart** (no durable queue) | `AgentRun(running)` older than a TTL is swept to `failed` on read/startup; acceptable for a member-triggered v1. A durable worker is the evolution if passes get long. |
| **Agent Actor drift** (duplicate agent actors per project) | Idempotent `get_or_create_project_agent_actor` with a uniqueness guard. |
| **Non-JSON / malformed model output** | Two-stage validation; a bad plan is a recorded trace outcome that mints nothing — never a `500`. |
| **Cost surprise** | Token usage recorded from `0.12.0`; the hard cap bounds a single pass even before `0.12.5` wires funding debit. |

## Verification gate

```bash
cd backend && uv run ruff check .
cd backend && uv run pytest -q                                   # DB-free: client/planner/policy
TEST_DATABASE_URL='postgresql+asyncpg://…' uv run pytest tests/agent/ tests/toolbench/ -q
cd frontend && npm run typecheck && npm run lint && npm run build
```

Before prod: set `OPENROUTER_API_KEY` (Fly secret) and flip `AGENT_LOOP_ENABLED=true`; run one
flagship agent pass on staging and confirm a checkpoint lands on the agent branch attributed to the
agent Actor, and reject closes it.

## Appendix — manual walkthrough

1. Sign in as a project **member**; assign a model to the `researcher` role (Research crew panel).
2. Open the *measuring across a corner* thread; click **Run agent pass**.
3. Watch the trace: the plan (e.g. `counterexample.search` on claim 2), then the landed checkpoint
   on the **agent branch**; confirm `Checkpoint.author` is the agent Actor and the contribution is
   `tool_run`.
4. **Reject** → the branch bar shows it `dead_end`; the reasoning is preserved on the timeline.
5. Re-run the flagship *human* walkthrough to confirm the normal path is unchanged.
