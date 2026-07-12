# `0.12.0` — Thin Agent Loop Phase 1: Foundations (settings, LLM client, agent Actor, trace table)

> **Status — completed (2026-07-06).** Phase 1 of
> [`docs/executing/thin-agent-loop-0.12-implementation-plan.md`](../executing/thin-agent-loop-0.12-implementation-plan.md).
> The config, the OpenRouter client, the agent-identity provisioning, and the (empty, migrated)
> `AgentRun` trace table now exist. **No loop yet; the dark-launch flag is off; zero behaviour
> change.** **Next:** Phase 2 (`0.12.1`) — the pure, injectable planner (no writes).

## What this phase delivered

| Deliverable | State |
|---|---|
| `Settings` fields for the agent loop (`openrouter_*`, `agent_*`) | Shipped |
| `.env.example` entries + the "key is a Fly secret" note | Shipped |
| `app/agent/__init__.py` + `app/agent/llm.py` — OpenRouter client with typed failure | Shipped |
| `app/services/agent_actors.py` — idempotent agent-Actor provisioning | Shipped |
| `AgentRunStatus` enum + `app/models/agent_run.py` — the trace model | Shipped |
| Partial functional unique index `uq_actors_one_agent_per_project` (on the `Actor` model) | Shipped |
| Migration `0013_agent_runs` (enum + table + the actors index) | Shipped |
| `app/schemas/agent_run.py` — `AgentRunRead` / `AgentRunSummary` | Shipped |
| `tests/agent/test_llm_client.py` (6 tests, DB-free) | Green |
| `tests/agent/test_migration_0013.py` (2 tests, DB-free) | Green |
| `tests/agent/test_agent_actors.py` (3 tests, DB-backed) | Written — **manual gate** |

No behaviour change on any shipped path. `agent_loop_enabled` defaults to `False`; nothing imports
the client or the service into a request path yet (routes arrive in `0.12.3`).

## Why Phase 1 is isolated (no loop yet)

The plan slices by demoable/reviewable outcome per release. Phase 1 lands the *substrate* — an LLM
client, an agent identity, a trace schema — that Phases 2–4 consume, without touching
`run_instrument`, the checkpoint chokepoint, or any route. Each piece is reviewable and testable in
isolation, and the standing invariants hold trivially because **nothing writes to the ledger this
phase.**

## Files created / modified

### `backend/app/core/config.py` (+ `.env.example`) — settings

Added an `agent`/`openrouter` group mirroring the `toolbench_*` group:

| Setting | Default | Meaning |
|---|---|---|
| `openrouter_api_key` | `None` | The OpenRouter key — a **Fly secret** in prod, never `fly.toml [env]`. |
| `openrouter_base_url` | `https://openrouter.ai/api/v1` | Overridable for tests / proxies. |
| `agent_llm_timeout_s` | `60.0` | Wall-clock cap on the single planning call. |
| `agent_pass_max_runs` | `5` | Max instrument runs per pass — a **safety** cap, not budget. |
| `agent_pass_max_tokens` | `200_000` | Token ceiling recorded/compared per pass — safety, not budget. |
| `agent_loop_enabled` | `False` | Dark-launch flag; the routes (`0.12.3`) `404` while off. |

A comment block states the load-bearing distinction the plan insists on: **per-pass caps are safety
limits (blast radius); real budget is a project-level concern (`0.12.5`), never per-thread.**

### `backend/app/agent/llm.py` — the OpenRouter client

- `LlmResponse` (frozen dataclass): `text`, `tokens_used`, `model`.
- `AgentLlmError`: one typed failure for a missing key, a network error, a timeout, a non-2xx, or an
  empty/malformed body — so a route maps it to `422`/`503`, **never a `500`** (the retrieval
  `RetrievalError` posture).
- `LlmClient` `Protocol`: the single `complete(...)` method the planner depends on, so a `StubLlm`
  substitutes trivially and CI never touches the network.
- `OpenRouterClient`: one `httpx.AsyncClient` `POST {base_url}/chat/completions`,
  `Authorization: Bearer {key}`, parsing `choices[0].message.content` + `usage.total_tokens`.
  `transport` is an injection seam (`httpx.MockTransport` in tests) exactly like `RetrievalClient`.

**Design choice — the `max_tokens` deviation.** The plan literally said "`max_tokens=agent_pass_max_tokens`".
Sending `max_tokens=200_000` as the *completion* budget would be rejected by most providers (their
output caps are far lower), and `agent_pass_max_tokens` is described in the same plan as a
*usage/budget* ceiling. So the client sends `max_tokens` **only when a caller passes one
explicitly**; the pass-level token cap is enforced by the orchestrator (`0.12.2`) comparing the
recorded `usage.total_tokens`, which is what that setting is actually for. This is the semantically
correct reading and keeps the client provider-agnostic.

### `backend/app/services/agent_actors.py` — agent-Actor provisioning

- `get_or_create_project_agent_actor(db, project_id) -> Actor` — **idempotent**. Finds the existing
  `Actor(type=AGENT)` whose `actor_metadata->>'project_id'` matches; else creates one with
  `type=AGENT`, `account_id=None`, `display_name="Research crew"`,
  `actor_metadata={"project_id": str(project_id)}`.
- Composes with the caller's transaction (`flush`, **no commit**), like every other write helper.
- **Race-safe** via a `begin_nested()` SAVEPOINT around the insert: on the rare concurrent-first-pass
  race the partial unique index rejects the loser with an `IntegrityError`; we roll the savepoint
  back and refetch the winner, so the caller always gets exactly one agent Actor without poisoning
  the outer transaction.

### `backend/app/models/actor.py` — the idempotency guard (create_all/Alembic lockstep)

Added a second entry to `Actor.__table_args__`:

```
CREATE UNIQUE INDEX uq_actors_one_agent_per_project
  ON actors ((actor_metadata ->> 'project_id')) WHERE type = 'AGENT'
```

This is declared **on the model** (not only in the migration) so the test harness's
`Base.metadata.create_all` builds the *same* constraint migration `0013` installs in prod — the
exact pattern the existing `uq_actors_one_human_per_account` index (migration `0006`) follows. The
compiled DDL was verified DB-free to match the migration byte-for-byte.

### `backend/app/models/enums.py` + `app/models/agent_run.py` — the trace

- `AgentRunStatus(StrEnum)`: `RUNNING` / `COMPLETED` / `FAILED`, with a docstring stating it is a
  **mutable** live trace, *deliberately outside* the append-only guards.
- `AgentRun(IdMixin, TimestampMixin, Base)` — `agent_runs`. Columns per the plan, with the step
  JSON shape documented in the module docstring. Exported from `models/__init__.py` `__all__`
  (Alembic discovery — a model missing from `__all__` is silently absent from migrations).

**Design choice — two nullability deviations, forced by the settled execution model (Decision #7).**
The plan's column table marked `agent_actor_id` and `model` `NOT NULL`. But the settled architecture
mints the `AgentRun` row `running` **at commission time** (the request session), when only the
commissioning human (`triggered_by_actor_id`) and the `role` are known; the **agent Actor** and the
resolved **model** are looked up *inside the background pass* (`0.12.2`/`0.12.3`). So both are
**nullable** and stamped when resolved:

| Column | Plan said | Shipped | Why |
|---|---|---|---|
| `triggered_by_actor_id` | not null | not null (SET NULL on actor delete) | Known at commission. |
| `role` | not null | not null | Known at commission. |
| `agent_actor_id` | not null | **nullable** (SET NULL) | Resolved inside the pass; null on early failure. |
| `model` | not null | **nullable** | Resolved from `agent_models[role]`; null when the role is unassigned → a *failed trace*, which the plan explicitly wants recorded (not a commission-time `422`). |
| `branch_id` | nullable | nullable (SET NULL) | Main-line fallback + resolved in the pass. |

This is the only way the "unassigned role → recorded failed trace, mints nothing" outcome (a
`0.12.2` test) is expressible: the row must exist before the model is known.

### `backend/alembic/versions/0013_agent_runs.py` — migration

Additive, mirroring the `0010`/`0012` idioms: creates the `agent_run_status` enum (uppercase
StrEnum-member labels, this DB's convention), the `agent_runs` table (FKs inline + unnamed,
per-FK indexes on `project_id`/`thread_id` only — matching the model's `index=True`), and the
partial functional unique index on `actors`. `downgrade` reverses all three. Chains cleanly:
`0012_toolbench_provenance -> 0013_agent_runs (head)`.

### `backend/app/schemas/agent_run.py` — read schemas

`AgentRunSummary` (list row: counts + status, no heavy JSON) and `AgentRunRead` (the poll target:
summary + `plan` + `steps`). Both `from_attributes=True`, lenient reads — the `plan`/`steps` JSON is
passed through verbatim. The *planner* schemas (`AgentPlan`/`PlannedRun`) belong with the planner in
`0.12.1`, not here (this file is read-only).

## Tests

| File | Kind | Coverage |
|---|---|---|
| `tests/agent/test_llm_client.py` | DB-free (`httpx.MockTransport`) | success returns text + `tokens_used`; timeout, non-2xx, missing key, malformed body, empty content each raise `AgentLlmError`. |
| `tests/agent/test_migration_0013.py` | DB-free | revision chain (`0013` → `0012`); enum labels match `AgentRunStatus` member names. |
| `tests/agent/test_agent_actors.py` | DB-backed (`TEST_DATABASE_URL`) | idempotency (two calls → same id); distinct projects → distinct agents; the partial unique index rejects a raw duplicate insert. |

## Verification

```bash
cd backend && uv run ruff check .                  # All checks passed
cd backend && uv run pytest -q                      # 185 passed, 105 skipped (no DB)
```

DB-free checks that ran green this phase:

- **App boots** with the new models/enum/settings; the append-only guards still register.
- **Functional-index DDL parity** — compiled `CreateIndex` for the `Actor` table's indexes against
  the PostgreSQL dialect and confirmed `uq_actors_one_agent_per_project` matches the migration.
- **Alembic chain** — `alembic heads` → `0013_agent_runs (head)`.
- **8 DB-free agent tests** pass; the full suite is unchanged apart from the additions.

### Manual gate (deferred, not run this session)

The 3 DB-backed agent-actor tests need Postgres and are documented as a manual gate (the repo's
standing posture — the destructive `DROP SCHEMA` suite runs only against an explicit
`TEST_DATABASE_URL`, never the live DB):

```bash
cd backend && TEST_DATABASE_URL='postgresql+asyncpg://…@localhost:5432/opentheory_test' \
  uv run pytest tests/agent/ -q
# and the migration up/down round-trip against a throwaway/staging DB:
MIGRATION_DATABASE_URL='…' uv run alembic upgrade head && uv run alembic downgrade -1
```

## Standing invariants — honoured

- **One write path / append-only:** nothing this phase writes a ledger row. `AgentRun` is a
  deliberately mutable trace, *outside* the append-only guards, with a comment saying so.
- **Human-first / roles separate:** the agent Actor is an *authored identity* (`account_id=None`),
  not a `ProjectMember` and not a governance principal; role/model are recorded per-pass, keeping
  funder/contributor/validator separation intact.
- **Dark launch:** `agent_loop_enabled=False`; the surface is inert until `0.12.3` adds the routes.
