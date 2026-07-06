# `0.12.3` — Thin Agent Loop Phase 4: The API surface + background execution

> **Status — completed (2026-07-06).** Phase 4 of
> [`docs/executing/thin-agent-loop-0.12-implementation-plan.md`](../executing/thin-agent-loop-0.12-implementation-plan.md).
> A project **member** now commissions a pass over HTTP; it runs in a background task, and the
> `AgentRun` trace is pollable. **Next:** Phase 6 (`0.12.4`) — the frontend trigger/trace/accept-reject
> (the `0.12.5` project-budget metering is an independent stretch that can slot before or after).

## What this phase delivered

| Deliverable | State |
|---|---|
| `services/agent_runs.py::start_agent_pass` — mint the `running` row in the request session | Shipped |
| `BackgroundExecutor` seam + `run_agent_pass_background` — the `BackgroundTask` entrypoint | Shipped |
| `list_thread_agent_runs` / `get_agent_run` — reads with a stale-`running` sweep | Shipped |
| `schemas/agent_run.py::AgentRunTrigger` — the commission body (`role` → `422`) | Shipped |
| `api/routes/agent_runs.py` — `POST` (member-gated) + two `GET`s, dark-launch-gated | Shipped |
| `api/router.py` — router registered at the root | Shipped |
| `tests/agent/test_agent_runs_api.py` (8: 3 DB-free gates green, 5 DB-backed manual gate) | Shipped |

No schema change (the `AgentRun` table shipped in `0.12.0`). No frontend yet. The dark-launch flag
`agent_loop_enabled` stays **off** — the surface is inert in prod until flipped.

## The surface in one paragraph

`POST /projects/{id}/threads/{thread_id}/agent-runs` (member-gated) calls `start_agent_pass`, which
mints the `running` `AgentRun` in the **request** session and commits it, then the route schedules
`run_agent_pass_background(run.id)` as a FastAPI `BackgroundTask` and returns **`202`** + the trace in
its `running` state. The background task opens its **own** session (the request one is closed by
then) and runs the `0.12.2` orchestrator; each step commits the mutable trace as it lands. The client
polls `GET /agent-runs/{id}` until `completed`/`failed`; `GET …/agent-runs` lists a thread's passes.
The whole surface `404`s while `agent_loop_enabled` is off.

## Files created / modified

### `backend/app/schemas/agent_run.py` — the commission body

`AgentRunTrigger{role: str}` with a `field_validator` gating `role ∈ AGENT_ROLE_FIELDS` → `422`. A
role that is valid but **unassigned** is intentionally accepted (it becomes a `failed` trace inside
the pass, Decision #7) — the schema only rejects *unknown* role names.

### `backend/app/services/agent_runs.py` — commission, background execution, reads

- **`start_agent_pass(db, project_id, thread_id, *, triggered_by, role)`** — the `POST` half only:
  validate thread∈project (`404`), mint `AgentRun(running)`, commit, return. It does **not** run the
  pass — so the multi-second work is off the request path.
- **`BackgroundExecutor`** (`session_factory` / `planner` / `llm`) + **`run_agent_pass_background`** —
  the `BackgroundTask` entrypoint. It resolves the executor **at call time**, opens a fresh session,
  and hands off to `run_agent_pass`. A last-ditch outer guard catches the pathological cases the
  orchestrator's own guard cannot (a missing row, a broken session) and best-effort marks the row
  `failed` in a clean session — a lost task can never strand a `running` row.
- **`list_thread_agent_runs` / `get_agent_run`** — the read side, each sweeping stale `running` rows
  to `failed` first (`_stale_running_cutoff` / `_sweep_if_stale`). `get_agent_run` `404`s an unknown
  id.

### `backend/app/api/routes/agent_runs.py` (+ `api/router.py`) — the routes

`require_agent_loop_enabled` is a **router-level** dependency (dark launch). The `POST` is
member-gated (`ensure_is_member`), returns `202`, and schedules the background task; the two `GET`s
are public (matching the codebase's public-read posture). Registered at the root like
threads/instruments (it spans nested + `/agent-runs/{id}` paths).

## Three deliberate design decisions (with rationale)

1. **Dark launch as a router-level dependency, not a body check — so `404` beats `401`.** The plan
   wants the route "indistinguishable from a route that does not exist yet" while the flag is off. A
   check in the handler body runs *after* `ActingActor`, so an unauthenticated request would get
   `401` — leaking that the route exists. FastAPI inserts router/route-level `dependencies` at the
   **front** of the dependency tree, so `require_agent_loop_enabled` runs before auth: an
   unauthenticated request sees `404`. This is **verified by a DB-free test**
   (`test_dark_launch_post_is_404_when_disabled`) that runs in the default suite — the ordering claim
   is checked, not assumed.

2. **The background seam must cover the session factory, not just the planner.** The plan calls for a
   "stub planner via a DI/settings seam." But a `BackgroundTask` runs after the `202` and its request
   session is gone, so the pass opens its own from `AsyncSessionLocal` — which in tests points at
   `settings.database_url`, **not** the `TEST_DATABASE_URL` engine the test writes to. A planner-only
   seam would leave the round-trip test unable to find its own row. So `BackgroundExecutor` bundles
   `(session_factory, planner, llm)` into **one** rebindable object; production keeps the defaults, a
   test flips it in a single `monkeypatch.setattr`.

3. **A stale-`running` sweep on read (the plan's watch-item), keyed on `updated_at`.** A killed
   background worker would otherwise strand a row `running` forever. Both `GET`s flip any `running`
   row untouched past a worst-case-pass TTL to `failed`. The TTL is derived, not guessed:
   `agent_llm_timeout_s + agent_pass_max_runs · toolbench_wall_timeout_s + margin`. Because the
   orchestrator commits the trace on **every** step, a live pass keeps bumping `updated_at`, so the
   sweep can never catch one that is genuinely in flight. Done via the ORM (not a Core bulk `UPDATE`)
   so `updated_at` bumps through the mixin `onupdate` and the swept row is fresh for serialization —
   no expire/refetch dance.

**Implementation note (a real trap):** the stale sweep over a list evaluates
`[_sweep_if_stale(r, cutoff) for r in rows]` into a list *before* `any(...)`. A generator would
short-circuit at the first stale row and leave later ones unswept.

## Why the background task completes before the `POST` returns (in tests)

Under httpx `ASGITransport`, Starlette awaits `BackgroundTasks` as part of the response lifecycle, so
the app coroutine — and thus `await client.post(...)` — does not resolve until the pass has finished.
The round-trip test therefore normally sees `completed` on its first poll; the `_poll_until_terminal`
loop is defensive, and models exactly what the frontend will do. The `POST` response itself is
serialized *before* the background task mutates the row, so it faithfully shows `running`.

## Tests (`tests/agent/test_agent_runs_api.py`, 8)

**DB-free gates (default suite — 3 green this session):**

| Test | Asserts |
|---|---|
| dark-launch `POST` `404` | flag off + **unauthenticated** + valid body → `404` (proves the gate beats auth *and* body validation). |
| dark-launch `GET` `404` | the poll target is dark too while off. |
| unauth `POST` `401` when enabled | flag on + no token + dev-header off → `401` (the gate no longer masks auth). |

**DB-backed (manual `TEST_DATABASE_URL` gate — 5 written, skip without Postgres):**

| Test | Asserts |
|---|---|
| non-member `403` | an outsider commissioning a member's project → `403`. |
| bad role `422` | a member with `role="wizard"` → `422` from `AgentRunTrigger`. |
| cross-project thread `404` | commissioning project A with project B's thread → `404`. |
| full round-trip | `POST` → `202 running`; poll `GET` → `completed`, `ran_count==1`, a landed `checkpoint_id` in `steps`, on the forked agent branch; the list surface includes it. Stub planner via the rebound `BackgroundExecutor`. |
| unassigned role | `POST` → `202` (commissioned), poll → `failed` with "no model assigned", `ran_count==0`, planner never reached (Decision #7). |

## Verification

```bash
cd backend && uv run ruff check .                  # All checks passed
cd backend && uv run pytest -q                      # 199 passed, 117 skipped (no DB)
```

DB-free this session: ruff clean; the app boots with the three routes registered (`POST` at `202`,
two `GET`s); the 3 DB-free gate tests pass (the dark-launch `POST` test empirically confirms the
router-level dependency runs before `ActingActor`); the 5 DB-backed tests collect and skip cleanly
(imports/syntax validated).

### Manual gate (deferred — needs Postgres)

The 5 DB-backed route tests are the real proof of the surface and must be run before trusting the
line:

```bash
cd backend && TEST_DATABASE_URL='postgresql+asyncpg://…@localhost:5432/opentheory_test' \
  uv run pytest tests/agent/ -q
```

Specifically confirm: (a) the round-trip's background task, running on the **rebound** test session
factory, lands a real checkpoint the poll can read; (b) `start_agent_pass`'s thread∈project guard
returns `404`; (c) `ensure_is_member` gates the `POST` to members (`403` otherwise); and (d) the
unassigned-role commission returns `202` then finalizes a `failed` trace.

## Standing invariants — honoured

- **One write path / failure split / append-only:** the route composes the `0.12.2` orchestrator,
  which reaches the ledger only via `run_instrument` + `create_branch`. `start_agent_pass` writes
  only the mutable `AgentRun` trace (not a ledger primitive). No new checkpoint mint path.
- **Human-first / roles separate:** the commissioning **human** is member-gated and accountable; the
  agent Actor authors the work one layer down. The agent never funds or self-validates; the surface
  adds no governance role. Budget stays a project-level seam (`0.12.5`), untouched here.
- **Dark launch:** `agent_loop_enabled=False` → the whole surface `404`s, before auth. Prod flips
  the flag (and sets `OPENROUTER_API_KEY` as a Fly secret) when the line is trusted.
