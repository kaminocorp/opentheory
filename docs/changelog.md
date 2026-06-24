# Changelog

## Index

- `0.4.8` — First live deployment: the FastAPI backend on Fly.io and the Next.js frontend on Vercel, both against the live Supabase DB, as an open (no-auth) preview. Adds the deploy scaffolding (Dockerfile, `fly.toml`, runbook) and documents the production connection shape. No app code, schema, or migration change.
- `0.4.7` — Developer convenience: a root `Makefile` wrapping the common backend (`uv`) and frontend (`npm`) tasks — `make dev`, `make migrate`, `make test`, `make fe`, etc. No app code, schema, or behavior change.
- `0.4.6` — First live database: provisioned the managed Postgres, applied migrations `0001→0003`, and hardened the connection config for a pooled cloud Postgres (app over the transaction pooler, Alembic over a direct connection). No new features or schema.
- `0.4.5` — Post-`0.4.0` review fixes: order-aware claim `signal` (a contradiction after a retract re-contests), corrected a stale overview-counts test that would have failed on a live DB, sealed-branch recording UX, typed the checkpoint ref validator, and removed dead frontend exports. No new features, schema, or migration.
- `0.4.4` — Read-model enrichment + polish: claim validation history with a derived `signal`, project overview branch/validation counts + contradictions summary, per-branch checkpoint counts, and the workspace surfaces for all of it. Completes `0.4.0`.
- `0.4.3` — Frontend validation + branch surfaces: record validations on claims/checkpoints, a branch bar that forks/closes and scopes the ledger timeline, and contradiction indicators. Third phase of `0.4.0`.
- `0.4.2` — Branch write path: fork from a checkpoint, record checkpoints on a branch, close as dead-end/superseded — all through the checkpoint chokepoint; adds `checkpoints.branch_id` (migration `0003`). Second phase of `0.4.0`.
- `0.4.1` — Validation write path: record an immutable assessment of a claim/checkpoint/branch through the checkpoint chokepoint, attributed by a `validate` contribution. First phase of `0.4.0`.
- `0.3.4` — Enriched ledger read models: project aggregate counts, per-thread claim counts, and a checkpoint timeline showing author, action, and referenced claims/evidence. Completes `0.3.0`.
- `0.3.3` — Three-panel research workspace (threads / claims+evidence / checkpoint timeline) wired to all create/read flows, plus a localStorage-backed dev-actor switcher attached as `X-Dev-Actor-Id`.
- `0.3.2` — Checkpoint service as the sole append-only ledger write path, ORM-enforced append-only on checkpoints/refs/funding, and automatic contribution recording for all four create flows.
- `0.3.1` — Backend write path for threads, claims, and evidence, plus dev actors, two join tables, and the first real Alembic migration.
- `0.2.0` — Added the initial Next.js frontend scaffold with Tailwind, TanStack Query, typed API client, project index, and project detail surfaces.
- `0.1.0` — Added the initial FastAPI backend scaffold, domain model foundation, Alembic setup, and smoke-test tooling.

---

## 0.4.8

First live deployment. Stands up the running product for the first time: the FastAPI backend on Fly.io and the Next.js frontend on Vercel, both pointed at the already-live Supabase database (`0.4.6`). Deployed as an **open preview** — there is no authentication yet (`X-Dev-Actor-Id` is not a credential), so the surface is intentionally world-readable/writable until `0.6.0`. No application code, schema, or migration change — this is deployment scaffolding plus the deploy itself.

### Summary

Through `0.4.7` the apps built clean but had never been deployed — there was zero deployment config in the repo. This phase adds the backend container + Fly configuration, documents the production connection shape, and takes the full stack live against the live DB (empty — no seed data; projects are created through the UI). The Vercel frontend is managed manually via the dashboard.

### Deployment Scaffolding (new)

- `backend/Dockerfile` — uv-based image (`ghcr.io/astral-sh/uv:python3.12-bookworm-slim`); dependencies install from the locked manifest in a cached layer (`uv sync --frozen --no-dev`); production entrypoint `fastapi run app/main.py` on `0.0.0.0:8000`.
- `backend/fly.toml` — app `opentheory-backend`, internal port 8000, `force_https`, a `/api/v1/health` HTTP check, scale-to-zero (`min_machines_running = 0`), and `release_command = "alembic upgrade head"` so migrations run in an ephemeral machine *before* traffic shifts (a bad migration aborts the deploy; the app never races to migrate on boot).
- `backend/.dockerignore` — keeps `.env`/secrets, the local venv, caches, and tests out of the build context/image.

### Configuration

- `backend/.env.example` now documents the production connection shapes: the app over the Supabase **transaction pooler** (`:6543`, `asyncpg`, `ssl=require`), Alembic over the **direct** connection (`:5432`) via `MIGRATION_DATABASE_URL`, and `BACKEND_CORS_ORIGINS` as the deployed frontend origin. Reuses the dual-connection design proven in `0.4.6`; no new settings.

### What Went Live

- **Backend** → Fly.io app `opentheory-backend`: <https://opentheory-backend.fly.dev/api/v1> (region `iad`, single scale-to-zero machine). Secrets (`DATABASE_URL`, `MIGRATION_DATABASE_URL`, `BACKEND_CORS_ORIGINS`) set via `fly secrets`, never committed.
- **Frontend** → Vercel: <https://opentheory.vercel.app> (root directory `frontend/`, `NEXT_PUBLIC_API_BASE_URL` → the Fly backend).
- **Database** → the existing live Supabase Postgres at migration `0003` (unchanged).

### Verification

- Remote Docker build succeeded; the `alembic upgrade head` release step completed against the live DB (a no-op at head — confirms the direct-connection migration path works from Fly).
- Public smoke test: `GET /api/v1/health` → `200 {"status":"ok"}`, `GET /api/v1/projects` → `200 []`.
- Simulated browser preflight from the Vercel origin returns `access-control-allow-origin: https://opentheory.vercel.app` — the CORS loop is closed. (End-to-end frontend page load left to a visual check.)

### Operational Notes / Gotchas

- Fly provisions an **HA pair** on first deploy even with `min_machines_running = 0` (that setting governs how many stay *running* when idle, not how many are *created*); the second machine stuck in `created` made `fly deploy` report a timeout though the service was healthy. Destroyed the extra — one machine is plenty for a scale-to-zero preview.
- `NEXT_PUBLIC_*` is baked at **build** time, so changing the backend URL requires a frontend *redeploy*, not just an env edit.
- `fly secrets import < .env` would clobber `APP_ENV=production` (from `fly.toml [env]`) with the local `.env` value — only the DB/CORS keys are imported.

### Documentation

- `docs/deploy.md` — full runbook (backend → frontend → CORS) with the production connection-string shapes and troubleshooting (IPv6 migration fallback, CORS, prepared-statement errors).
- `docs/design_blueprint.md` and `docs/executing/0.6.0-auth-and-funding.md` also landed in this window — a Kamino console design system, and the `0.6.0` auth + funding implementation plan. These are forward-looking planning/design references, **not** part of this deployment release.

### Still Gating A Production Push (unchanged)

- **The 31 DB-backed tests still have not run green against Postgres** — the standing `0.4.0` Definition-of-Done gate (needs a *separate* `TEST_DATABASE_URL`; the fixture `drop_all`s, so it must never point at the live DB).
- **No authentication/authorization** — `X-Dev-Actor-Id` lets any caller act as any actor; the open preview is world-writable. Deferred to `0.6.0`.

---

## 0.4.7

Developer convenience only — a root `Makefile` so the common workflows have short, memorable names. No application code, schema, or behavior change.

### Tooling

- Added a root `Makefile` wrapping the existing backend (`uv`) and frontend (`npm`) commands as targets: `make dev` (backend dev server), `make fe` (frontend dev server), `make migrate` / `make migration m="…"` / `make downgrade` (Alembic), `make test`, `make lint`, `make sync`, `make fe-install`. Bare `make` (default goal) prints a self-generated target list from each target's `##` comment.
- The targets only *wrap* the canonical commands (each is `cd backend && uv run …` or `cd frontend && npm …`), so every guarantee of `uv run` is preserved — correct `.venv`, locked deps — just behind a shorter name. Nothing previously documented changes.

---

## 0.4.6

First live database. Stands up the chosen managed Postgres (Supabase, per `docs/techstack.md`), applies the existing migrations to a real database for the first time, and hardens the connection configuration for a pooled cloud Postgres. Also fixes two latent configuration bugs that only surface once a populated `.env` exists. No new features, no schema change, no new migration — this closes the **infrastructure half** of the `0.4.0 — Validation And Branching` Definition-of-Done gate.

### Summary

Through `0.4.5` the backend had never connected to a real database: migrations were verified offline and the DB-backed tests skipped. This phase provisions the database, applies `0001 → 0003` against it, and proves both connection paths the app needs (pooled runtime + direct migrations). Bringing up a real `.env` for the first time also flushed out two dormant configuration bugs, both fixed.

### Database

- Applied migrations `0001_baseline → 0002_checkpoint_content → 0003_checkpoint_branch_id` to a live managed Postgres — the first time the schema has been created on a real database. `alembic current` reports `0003` at head and the expected public tables are present.

### Connection Configuration (dual path)

- **App runtime → transaction pooler.** The application engine connects through the connection pooler in transaction mode for connection scalability. asyncpg's prepared-statement cache is disabled (`connect_args={"statement_cache_size": 0}`) so it is safe behind a transaction-mode pooler (which reassigns server connections per transaction). At the platform's current query scale the lost statement caching is negligible, and parameter binding — i.e. injection safety — is unaffected. (`app/db/session.py`.)
- **Migrations → direct connection.** Added an optional `migration_database_url` setting (`MIGRATION_DATABASE_URL`); Alembic prefers it and falls back to `database_url`. DDL and schema introspection run over a stable, non-pooled session — the Prisma `url`/`directUrl` split. (`app/core/config.py`, `alembic/env.py`.)
- **TLS.** Connection URLs carry `?ssl=require`, which the SQLAlchemy asyncpg dialect maps to asyncpg's `ssl` argument (not the psycopg `sslmode`, which asyncpg does not understand). Connection secrets live only in the gitignored `.env`; `.env.example` documents the shape.

### Latent Config Bugs Fixed (surfaced by the first populated `.env`)

- **CORS origins parsing.** `backend_cors_origins` is a `list` field, and pydantic-settings JSON-decodes complex fields *before* validators run — so a plain `BACKEND_CORS_ORIGINS=http://localhost:3000` raised a JSON error at startup. Annotated the field with pydantic-settings' `NoDecode` so the existing comma-splitting validator receives the raw string. Dormant until now because the empty-default path skipped the decode. (`app/core/config.py`.)
- **CORS origin trailing-slash mismatch.** `str(AnyHttpUrl(...))` normalizes to `http://localhost:3000/`, but browsers send the `Origin` header without the trailing slash and Starlette matches origins exactly — so every preflight would have failed. Strip the trailing slash when building `allow_origins`. (`app/main.py`.)

### Tooling And Verification

- `uv run alembic upgrade head` applied all three migrations to the live database; `alembic current` → `0003` (head).
- Verified the app's transaction-pooler path connects and queries with no prepared-statement errors, and that the migrated schema is visible over it.
- In-process smoke test against the live database: `GET /api/v1/health` → `200`, `GET /api/v1/projects` → `200 []` (empty, pre-seed).
- `uv run ruff check .` clean; `uv run pytest` → `5 passed, 31 skipped` (DB-backed tests still skip — see below).

### Still gating a production push

- **The 31 DB-backed tests still need to be run green** against a *separate* test database. The test fixture creates and `drop_all`s the schema per test, so `TEST_DATABASE_URL` must never point at the live/seeded database. This is the remaining half of the `0.4.0` DoD gate; the infrastructure half (DB stood up, migrations applied, both connection modes proven) is now done.
- **No authentication/authorization** — `X-Dev-Actor-Id` lets any caller act as any actor. Deferred to `0.6.0`.

---

## 0.4.5

Review-driven correctness and polish on the completed `0.4.0 — Validation And Branching` slice. No new features, no schema change, no migration — a hardening pass from a full read-through of the `0.4.x` diff against the plan and completion docs.

### Summary

A review of the `0.4.x` implementation found the design sound but surfaced one real correctness bug (the claim signal ignored the *order* of validations), one latent test failure (a `0.3.4` assertion not updated when `0.4.4` widened the counts shape), and a few polish items. All are fixed; the suite, lint, and frontend build stay green.

### Correctness

- **Order-aware claim `signal`.** `compute_signal` now walks the validation history chronologically (oldest first) instead of treating it as an unordered set. Previously, a single `retract` *anywhere* in the history cleared every contradiction — so a `contradicts` recorded *after* a `retract` was wrongly shown as not-contested. Now the latest decisive event wins: `contradicts`/`failed` contests, a later `retract` clears it, a still-later `contradicts` re-contests. The derivation remains a pure display signal (plan Decision #5) — `Claim.status` is still never mutated. (`app/services/claims.py`.)

### Tests

- **Fixed a stale assertion** in `tests/test_read_models.py::test_project_overview_counts`: it asserted `counts == {threads, claims, evidence, checkpoints}`, but `0.4.4` added `validations` and `branches` to `ProjectCounts`. The DB-backed test is skipped offline (no database configured), so this went unnoticed — it would have failed on the first real-DB run. Now asserts the full six-key shape.
- **Added an order-aware signal case** to `test_claim_read_validation_history_and_signal`: `contradicts → retract → contradicts` ends `contested` (locks in the fix above).

### Polish

- **Sealed-branch recording UX.** The checkpoint timeline panel now takes a `lineSealed` flag (derived in `ProjectWorkspace` from the selected branch's status): on a closed/dead-end line it hides the "new checkpoint" affordance and explains that the line is preserved, not extended — instead of offering a form whose submit the backend rejects with `400`. (`project-workspace.tsx`, `checkpoint-timeline-panel.tsx`.)
- **Removed dead frontend exports:** the unused `getBranch` and `listClaimValidations` API-client functions and the `BranchDetail` type (claim validation history has been embedded in the claim read since `0.4.4`; the branch list drives the UI). The backend `GET /branches/{id}` detail endpoint stays — it's a legitimate, tested read for API consumers. (`lib/api.ts`, `types/research.ts`.)
- **Typed the checkpoint ref validator:** `_validate_refs(..., refs: list[CheckpointRefInput])` (was a bare `list` with a comment). (`app/services/checkpoints.py`.)

### Tooling And Verification

- `uv run ruff check .` (clean), `uv run pytest` (`5 passed, 31 skipped` — DB-backed tests still skip without a database), and `npm run typecheck` / `lint` / `build` (all pass).

### Still gating a production push (unchanged from `0.4.4`)

These are not regressions introduced here — they are the standing items before `0.4.0` is truly prod-ready, restated so they aren't lost:

- **The 31 DB-backed tests have never run against Postgres**, and no migration has been applied to a live database. This is the `0.4.0` Definition-of-Done gate: stand up Postgres, `uv run alembic upgrade head`, and get the DB-backed suite green.
- **No authentication/authorization** — `X-Dev-Actor-Id` lets any caller act as any actor. Acceptable for an internal/demo deploy; a blocker for a public one. Deferred to `0.6.0`.

---

## 0.4.4

Read-model enrichment and polish — makes research integrity legible at a glance. Fourth and final phase of `0.4.0 — Validation And Branching`. Backend read models + frontend rendering; no new write paths and no migration. See `docs/completions/0.4.4-read-model-and-polish.md`.

### Summary

Enriches the read side so the workspace shows what's been assessed, what's contested, and which lines are alive vs. abandoned. The claim read now embeds its validation history and a server-derived `signal` (`contested` / `validated` / `none`) computed from that history — without mutating the stored `Claim.status` (plan Decision #5). The project overview gains a validation count, branch-status counts, and a contradictions summary. The branch list carries per-branch checkpoint counts.

### Backend Read Models

- `ClaimRead` now includes `validations` (history, oldest first) and `signal`; the claims service constructs reads explicitly (never via `from_attributes` on the ORM, which would lazy-load the relationship) and batches validation lookups (no N+1, reusing the validations service).
- `GET /projects/{id}/overview` adds `counts.validations`, `counts.branches`, `branch_counts` (open / dead-end / closed), and `contradictions` (contested claims).
- Branch list (`GET /projects/{id}/branches`) returns `BranchSummary` with a per-branch `checkpoint_count` (single grouped outer-join query).
- Shared `compute_signal` lives in the claims service and is reused by the overview's contradictions detection. No schema/migration change.

### Frontend Rendering

- Claim cards render validation history (outcome badges + notes + actor) and a `contested` / `validated` chip from the server `signal`; the claim read's embedded data replaces the separate per-claim validations fetch.
- Workspace header shows six aggregate counts (adds Validations, Branches) and an ember "contested claims" strip listing the contradictions.
- The branch bar shows per-branch checkpoint counts and, for the selected line, its fork point and count.

### Tooling And Verification

- Extended `tests/test_read_models.py` (DB-backed: claim history + signal incl. retract-clears-contradiction, overview branch/validation counts + contradictions, branch `checkpoint_count`).
- Verified with `uv run ruff check .` (clean), `uv run pytest` (`5 passed, 31 skipped`), and `npm run typecheck` / `lint` / `build` (all pass).

### End-To-End Manual Verification Path (the `0.4.0` slice)

Once a database is configured (`DATABASE_URL` set, `uv run alembic upgrade head` applied), the full `0.4.0` flow is reproducible from the UI alone, on top of the `0.3.0` slice:

1. Open a project that already has a thread, a claim, and at least one checkpoint (the `0.3.0` flow), with a dev actor selected (top-right switcher).
2. On a claim, click **Validate**, choose `contradicts`, and submit. The claim shows a **contested** chip and an outcome badge; the header **Validations** count and the **contested claims** strip update; a `validate` checkpoint appears in the timeline.
3. Record another validation on the same claim with `retract` — the **contested** chip clears (history is preserved, oldest first).
4. In the branch bar, **Fork** a branch from a checkpoint (name + reason). It is auto-selected; the **Branches** count and the branch's checkpoint count update.
5. With the branch selected, record a checkpoint — it lands on the branch line (the main-line timeline is unchanged when you switch back to **Main line**).
6. **Close branch** as a dead-end with a reason. The branch chip is struck through and marked `dead end`; `branch_counts.dead_end` increments; the closing reason is preserved (recorded, not deleted).
7. Confirm append-only/provenance: `PUT`/`DELETE` on validations and checkpoints are absent; an ORM update/delete of a `Validation` raises `AppendOnlyError`; recording a checkpoint on the closed branch returns `400`.

This exercises every `0.4.0` primitive end-to-end: validation (recorded through a checkpoint, attributed) and branching (fork → branch checkpoint → close as dead-end), with the contradiction and dead-end states surfaced.

---

## 0.4.3

Frontend validation and branch surfaces. Third phase of `0.4.0 — Validation And Branching`. Frontend only. See `docs/completions/0.4.3-frontend-validation-and-branches.md`.

### Summary

Surfaces the `0.4.1`/`0.4.2` write paths in the research workspace: record validations on claims and checkpoints, fork/close branches, scope the checkpoint timeline to a branch line, and flag contested claims. Built on the existing TanStack Query reads/mutations + query-key invalidation; no new client-state library.

### Product Surface

- Shared validation controls: an outcome→icon/colour vocabulary, an `OutcomeBadge`, and a reusable `RecordValidationForm` used on both claims (with inline history) and checkpoints (record-only — no per-checkpoint history endpoint).
- A branch bar above the panels: a **Main line** chip plus a chip per branch (dead-ends struck through), a **Fork** form anchored on a chosen checkpoint, and a **Close branch** form (dead-end / closed, required reason). Selecting a branch scopes the checkpoint timeline and new-checkpoint `branch_id` to that line; the claims panel stays thread-scoped (branches scope the ledger line, not the claim set, in this model).
- A client-side contradiction indicator on claims (superseded by the server `signal` in `0.4.4`).

### Frontend Structure

- Added `src/components/workspace/validation-controls.tsx` and `branch-bar.tsx`; extended the claim and checkpoint panels and the project workspace; extended `lib/api.ts`, `types/research.ts`, and the query keys with validations and branches.

### Tooling And Verification

- Verified with `npm run typecheck`, `lint`, and `build` (all pass). Live click-through deferred until a database is configured, consistent with the backend phases.

---

## 0.4.2

Branch write path. Second phase of `0.4.0 — Validation And Branching`. Backend + one migration. See `docs/completions/0.4.2-branch-write-path.md`.

### Summary

Activates the `Branch` primitive: fork a parallel line from a checkpoint, record checkpoints on it, and close it as a dead-end/superseded — all recorded through the single checkpoint chokepoint. Merge is deferred (plan Decision #3); `BranchStatus.MERGED` stays reserved.

### Schema

- Added `checkpoints.branch_id` (nullable, FK → `branches.id` `ON DELETE SET NULL`, indexed). `NULL` = the project main line (plan Decision #2); existing checkpoints become main-line. Migration `0003_checkpoint_branch_id` (`down_revision = 0002_checkpoint_content`).
- This is the second FK between `checkpoints` and `branches`, so all relationships spanning the two tables now pin `foreign_keys` explicitly.

### API

- `POST /api/v1/projects/{id}/branches` (fork from a checkpoint), `GET /api/v1/projects/{id}/branches`, `GET /api/v1/branches/{branch_id}` (detail incl. its checkpoints), `POST /api/v1/branches/{branch_id}/close` (outcome `dead_end`/`closed` + reason).
- `CheckpointCreate` accepts an optional `branch_id`; the chokepoint validates it is an in-project, **open** branch before stamping it.

### Service Layer

- Added `app/services/branches.py` (`create_branch`, `close_branch`, `list_branches`, `get_branch`), composing with the checkpoint chokepoint; `create_branch`/`close_branch` actions added to the contributions module. The fork's first checkpoint is recorded on the branch (parented on the fork point); the close checkpoint is main-line and references the branch (atomicity over stamping — see the completion doc).

### Tooling And Verification

- Added `tests/test_branches.py` (DB-backed). Verified with `uv run ruff check .` (clean), `uv run pytest` (DB-backed tests skip until a database is configured), `configure_mappers()` (dual-FK relationships), and offline Alembic checks (`0003` loads as head, renders the expected DDL).

---

## 0.4.1

Validation write path. First phase of `0.4.0 — Validation And Branching`. Backend only; no migration. See `docs/completions/0.4.1-validation-write-path.md`.

### Summary

Activates the `Validation` primitive as a first-class, immutable assessment recorded **through** the checkpoint chokepoint (plan Decision #1): recording a validation writes the `Validation` row and, in the same transaction, mints a checkpoint referencing the validated target (`role=validated`) and the validation (`role=recorded`), attributed by a `validate` contribution.

### API

- `POST /api/v1/projects/{id}/validations` (requires `X-Dev-Actor-Id`), `GET /api/v1/projects/{id}/validations`, `GET /api/v1/claims/{claim_id}/validations`, `GET /api/v1/validations/{validation_id}`. GET/POST only — no mutation methods.
- Targets follow the model: `claim` / `checkpoint` / `branch` / `artifact` (plan Decision #4; `artifact` wired but untested until artifact writes land). No `evidence` target.

### Service Layer

- Added `app/services/validations.py`; extended `CheckpointService.create_checkpoint` minimally (service-supplied `extra_refs` + an optional `contribution_action`) so the validation flow goes through the one chokepoint. Added `validation`/`branch` to the checkpoint-ref vocabulary.

### Append-Only Enforcement

- Added `Validation` to the ORM append-only guard set (`Checkpoint`, `CheckpointRef`, `FundingAllocation`, `Validation`): a re-assessment is a new row, never an edit.

### Tooling And Verification

- Added `tests/test_validations.py` (DB-backed) and extended `tests/test_wiring.py`. Verified with `uv run ruff check .` (clean) and `uv run pytest` (`5 passed`, DB-backed tests skip until a database is configured). No migration (the `validations` table is in the `0001` baseline).

---

## 0.3.4

Makes the checkpoint timeline read like a real research record and surfaces the state of the ledger at a glance. Fourth and final phase of `0.3.0 — Human-Operable Research Ledger`. Backend read models + frontend rendering; no new write paths and no migration (read-model only). See `docs/completions/0.3.4-ledger-read-model.md`.

### Summary

Enriches the read side: a project overview with aggregate counts, per-thread claim counts on the thread list, and a checkpoint read model carrying the creating actor, the contribution kind, and human labels for referenced claims/evidence. The workspace renders all of it — header counts, thread claim-count badges, and a timeline that shows who recorded each checkpoint, what action it was, and which primitives it touched.

### Backend Read Models

- `GET /api/v1/projects/{project_id}/overview` → project detail plus aggregate `counts` (threads, claims, evidence, checkpoints).
- Thread list (`GET /api/v1/projects/{project_id}/threads`) now returns `ThreadSummary` with a per-thread `claim_count` (single grouped outer-join query).
- Checkpoint reads (`list`/`detail`) are enriched with `author` (id, display name, type), `contribution_kind`, and a resolved `label` on each ref (claim statement / evidence/thread title / artifact name), all batched without N+1.
- Added `app/services/projects.py`; extended the thread and checkpoint services and the project/thread route response models. No schema/migration change.

### Frontend Rendering

- Workspace header shows the four aggregate counts (pulsing skeleton while loading); thread list shows a claim-count badge per thread.
- Checkpoint timeline shows the humanized action, the author, and the referenced claims/evidence as `role → label` rows, alongside stage, scope, and parent count; empty-state copy now explains when to record a checkpoint.
- Writes invalidate the overview (and the thread list on claim create) so counts stay live; added the `getProjectOverview` client call and the matching types.

### Tooling And Verification

- Added `tests/test_read_models.py` (DB-backed: overview counts + 404, thread `claim_count` incl. a zero-claim thread, enriched checkpoint author/contribution-kind/ref-labels on detail and list) and extended `tests/test_wiring.py` for the overview path.
- Ran an adversarial multi-agent review of the diff (10 findings → 3 actionable, fixed: render the checkpoint action, counts loading skeleton, richer empty-state copy; the rest were positive confirmations or correctly rejected).
- Verified with `uv run ruff check .` (clean), `uv run pytest` (`5 passed, 18 skipped`), and `npm run typecheck` / `lint` / `build` (all pass).

### End-To-End Manual Verification Path

Once a database is configured (`DATABASE_URL` set, `uv run alembic upgrade head` applied), the full `0.3.0` flow is reproducible from the UI alone:

1. Start the backend (`uv run fastapi dev app/main.py`) and frontend (`npm run dev`); open `http://localhost:3000`.
2. Create a project (via `POST /api/v1/projects` or seed) and open it.
3. In the header dev-actor switcher (top right), create an actor — it is auto-selected and attached as `X-Dev-Actor-Id` on writes.
4. Left panel: create a thread (title + sub-question). It is auto-selected; the header **Threads** count and the thread's claim-count badge update.
5. Center panel: record a claim on the thread (kind + statement). The **Claims** count and the thread badge increment.
6. On that claim, attach evidence (title + source + relation kind: support/weaken/context). It appears under the claim color-coded by relation; the **Evidence** count increments.
7. Right panel: record a checkpoint (summary + optional notes) — scoped to the selected thread. The **Checkpoints** count increments and the timeline shows it newest-first with the action ("create checkpoint"), the author, and the timestamp.
8. Confirm append-only: `PUT`/`DELETE` on `/api/v1/checkpoints/{id}` returns `405`; ORM update/delete raises `AppendOnlyError` (covered by `tests/test_checkpoints.py`).
9. Confirm provenance: each of the four creates recorded a `Contribution` attributing the acting actor (covered by `test_contribution_recorded_for_all_create_flows`).

This exercises every primitive in the human-operable ledger end-to-end: thread → claim → evidence → checkpoint, with attribution and append-only enforcement.

---

## 0.3.3

Surfaces the `0.3.1`/`0.3.2` write paths in the product. Third phase of `0.3.0 — Human-Operable Research Ledger`. Frontend only. See `docs/completions/0.3.3-frontend-research-workspace.md`.

### Summary

Expands `/projects/[projectId]` from a read-only detail page into a three-panel research workspace where a user completes the full research move — thread → claim → evidence → checkpoint — through the UI, with a dev-actor identity attached to every write. Built on TanStack Query for both reads and write mutations with query-key invalidation; no other client-state library.

### Product Surface

- Three-panel workspace: left thread list + create-thread; center claims for the selected thread with per-claim evidence and inline create-claim / attach-evidence; right project checkpoint timeline (newest first) with create-checkpoint scoped to the selected thread.
- Dev-actor switcher in the header: lists actors from `GET /api/v1/actors`, lets the user pick or create one (bootstrap path, no header), persists the selection in `localStorage`, and attaches it as `X-Dev-Actor-Id` on all writes. Replaced by real auth in `0.6.0`.
- Loading, empty, and error states for every panel via a shared `panel-state` helper.
- Minimal create UIs (single-line fields + an optional notes textarea on checkpoints); no rich editors.

### Frontend Structure

- Added `src/types/research.ts` (domain types mirroring the backend read schemas), `src/lib/query-keys.ts` (centralized query keys), `src/providers/dev-actor-provider.tsx`, `src/components/shell/dev-actor-switcher.tsx`, and the `src/components/workspace/` panel set (`panel-state`, `thread-list-panel`, `claim-list-panel`, `checkpoint-timeline-panel`, `project-workspace`).
- Extended `src/lib/api.ts` with all reads, the four create flows, and actor create/list; writes attach `X-Dev-Actor-Id`, and the request helper surfaces the backend `detail` on errors.
- Wrapped the app in `DevActorProvider`; the project route now renders `ProjectWorkspace`; the header hosts the switcher. Removed the superseded `project-detail.tsx`.

### Tooling And Verification

- Ran an adversarial multi-agent review of the diff (8 findings → 3 confirmed, 5 rejected); fixed the confirmed actor/mutation-lifecycle items (capture the acting actor by value at submit, gate the no-actor hint on hydration, guard against double-submit).
- Verified with `npm run typecheck` (clean), `npm run lint` (clean), and `npm run build` (succeeds; `/` static, `/projects/[projectId]` dynamic). A live end-to-end click-through is deferred until a database is configured, consistent with `0.3.1`/`0.3.2`.

---

## 0.3.2

Makes the research ledger real: the checkpoint becomes the only sanctioned way to record a meaningful state change, append-only is enforced at the ORM layer, and every create flow is attributed. Second phase of `0.3.0 — Human-Operable Research Ledger`. Backend only; no frontend changes yet (deferred to `0.3.3`). See `docs/completions/0.3.2-checkpoint-service.md`.

### Summary

Adds `CheckpointService.create_checkpoint` as the single chokepoint for ledger writes, enforces the append-only invariant on `Checkpoint`/`CheckpointRef`/`FundingAllocation` at the ORM layer, and back-fills automatic `Contribution` recording onto the `0.3.1` thread/claim/evidence creates so all four create flows are attributed. Checkpoints are created only by explicit user action — thread/claim/evidence creates do not auto-promote (plan Resolved Decision #3).

### Schema

- Added `checkpoints.content` (`JSON`, NOT NULL) — the free-form JSON payload a user authors on a checkpoint; no structured schema is enforced beyond "valid JSON object".
- Made `checkpoints.stage` nullable — a research-flow `ThreadStage` is optional metadata, not platform law, so a human may record a checkpoint without one.
- Added the second Alembic migration `0002_checkpoint_content` (`down_revision = 0001_baseline`): `ADD COLUMN content`, `ALTER COLUMN stage DROP NOT NULL`. Safe on the empty baseline table; references the existing `thread_stage` enum with `create_type=False`.

### API

- `POST /api/v1/projects/{project_id}/checkpoints` (requires `X-Dev-Actor-Id`) — validates project/thread/parents/refs, writes one `checkpoint_refs` row per ref with a `role`, links parents via `checkpoint_parents`, and auto-records a `create_checkpoint` contribution, all in one transaction.
- `GET /api/v1/projects/{project_id}/checkpoints` (newest first), `GET /api/v1/checkpoints/{checkpoint_id}`.
- No update/delete endpoints exist; the checkpoint paths are GET/POST only.

### Service Layer

- Added `app/services/checkpoints.py` (the sole producer of checkpoints) and `app/services/contributions.py` (`record_contribution` adds to the caller's session without committing, so contributions share the create's transaction).
- Back-filled `threads`/`claims`/`evidence` create services to record a contribution in the same transaction; route handlers now pass the acting actor through.

### Append-Only Enforcement

- Added `app/models/append_only.py`: `AppendOnlyError` plus `before_update`/`before_delete` ORM guards on `Checkpoint`, `CheckpointRef`, and `FundingAllocation`. Registration is idempotent and called explicitly in `create_app()` so the invariant never depends on import order. Enforced even if the route layer is bypassed.

### Tooling And Verification

- Refactored `tests/conftest.py` into shared `db_engine` + `session_factory` + `client` fixtures (one engine, so HTTP writes and direct DB assertions agree).
- Added `tests/test_checkpoints.py` (DB-backed: parents/refs, optional stage, full validation matrix, duplicate-parent dedup, append-only ORM enforcement with a selective negative test, contribution presence for all four flows) and extended `tests/test_wiring.py` (checkpoint paths exist, POST requires the dev-actor header, no mutation methods exposed).
- Ran an adversarial multi-agent review of the diff (19 findings → 6 confirmed, 13 rejected); confirmed items fixed (notably the `FundingAllocation` append-only gap and explicit guard registration).
- Verified with `uv run ruff check .` (clean), `uv run pytest` (`5 passed, 14 skipped`; DB-backed tests skip until a database is configured), and offline Alembic checks (`0002` loads as head, renders valid Postgres DDL, matches `metadata.create_all`).

> Note: a live database has not yet been chosen (Supabase vs. self-hosted). Applying `alembic upgrade head` and running the DB-backed tests are deferred to that step, consistent with `0.3.1`.

---

## 0.3.1

Backend write path for the three primitives that compose a research move. First phase of `0.3.0 — Human-Operable Research Ledger`. Backend + DB only; no checkpoint behavior and no frontend changes yet.

### Summary

Stands up the create/read API surface for threads, claims, and evidence under a project, plus manual dev-actor management and the two relational tables that make the new relations queryable. Establishes the service layer as the home for create logic and the first real Alembic migration. No checkpoint, contribution, or append-only behavior yet (deferred to `0.3.2`).

### Schema

- Added `claim_evidence_links` join table (`app/models/links.py`) — a true many-to-many between claims and evidence with a `relation_kind` `VARCHAR(20)` column (`support` / `weaken` / `context`, validated in the service layer) and a uniqueness guard on `(claim_id, evidence_id, relation_kind)`.
- Added `checkpoint_refs` join table (`app/models/links.py`) — polymorphic `target_type` (`VARCHAR(20)`), `target_id` (UUID, no FK), and `role` (`VARCHAR(40)`). Introduced now though it is consumed in `0.3.2`, to avoid a follow-up migration.
- Added reverse relationships on `Claim`, `Evidence`, and `Checkpoint`; exported both new models from `app/models/__init__.py` for Alembic discovery.
- Added the first real Alembic migration `0001_baseline` covering all `0.1.0` models plus the two join tables. Enum labels are the SQLAlchemy default (the `StrEnum` member names) to match the existing models; no data seeding.

### API

- `POST /api/v1/actors`, `GET /api/v1/actors` — manual dev-actor management (no auto-seeding).
- `POST /api/v1/projects/{project_id}/threads`, `GET /api/v1/projects/{project_id}/threads`, `GET /api/v1/threads/{thread_id}`.
- `POST /api/v1/threads/{thread_id}/claims`, `GET /api/v1/threads/{thread_id}/claims`, `GET /api/v1/claims/{claim_id}` — claims inherit the thread's project; `project_id` is never client-supplied.
- `POST /api/v1/claims/{claim_id}/evidence` (creates the `Evidence` row and its `claim_evidence_links` row in one transaction), `GET /api/v1/claims/{claim_id}/evidence` (joined through the link table, returns `relation_kind`).
- All write endpoints require the acting actor via the `X-Dev-Actor-Id` header, resolved to an existing `Actor`; missing, malformed, or unknown ids are rejected.

### Service Layer

- Added thin create/read services in `app/services/` for actors, threads, claims, and evidence. No checkpoint interaction yet.
- Added `app/api/deps.py` with the shared `DbSession` alias and the `get_acting_actor` dev-identity dependency.

### Tooling And Verification

- Added `tests/conftest.py` with a DB-backed `client` fixture that creates/drops tables per test and skips cleanly when no `TEST_DATABASE_URL`/`DATABASE_URL` is configured.
- Added `tests/test_wiring.py` (DB-free OpenAPI checks) and `tests/test_research_flow.py` (full flow, every relation kind, header enforcement, 404s).
- Verified with `uv run ruff check .` (clean) and `uv run pytest` (green; DB-backed tests skip until a database is configured).
- Verified the migration offline: it loads as the Alembic head, renders valid Postgres DDL via `alembic upgrade head --sql`, and its DDL matches `metadata.create_all` exactly (no spurious constraints/indexes).

> Note: a live database has not yet been chosen (Supabase vs. self-hosted). Applying the migration (`alembic upgrade head`) and running the DB-backed tests are deferred to that step. See `docs/completions/0.3.1-backend-write-path.md`.

---

## 0.2.0

Initial frontend scaffold for OpenTheory.

### Summary

This release establishes the frontend root at `frontend/` as a Next.js application aligned with `docs/techstack.md`. It is intentionally minimal but product-shaped: the first screen is a research project surface that connects to the FastAPI project endpoints instead of a generic starter page.

### Frontend Structure

- Added `frontend/package.json` and `frontend/package-lock.json` configured for Next.js, React, TypeScript, Tailwind CSS, TanStack Query, lucide icons, ESLint, and local scripts.
- Added `frontend/README.md` with local setup and verification commands.
- Added `frontend/.env.example` with `NEXT_PUBLIC_API_BASE_URL` for the FastAPI API prefix.
- Added `frontend/.gitignore` for Next.js build output, dependencies, local env files, and TypeScript build cache files.
- Added Next.js, TypeScript, PostCSS, Tailwind, and ESLint configuration files.
- Added the application source under `frontend/src/` with:
  - `app/` for App Router pages and global styling
  - `components/` for shell and project UI
  - `lib/` for backend API access
  - `providers/` for TanStack Query setup
  - `types/` for shared frontend domain types

### Product Surface

- Added the root project index page.
- Added a project detail route at `/projects/[projectId]`.
- Added typed reads for:
  - `GET /api/v1/projects`
  - `GET /api/v1/projects/{project_id}`
- Added loading, empty, and backend-error states for project reads.

### Tooling And Verification

- Installed frontend dependencies with npm.
- Verified the scaffold with:
  - `npm run typecheck`
  - `npm run lint`
  - `npm run build`

---

## 0.1.0

Initial backend scaffold for OpenTheory.

### Summary

This release establishes the backend root at `backend/` as a FastAPI modular monolith aligned with `docs/techstack.md`, `docs/primitives.md`, and the research-ledger model described in the vision docs. It is intentionally minimal but domain-shaped: the scaffold starts with real OpenTheory primitives instead of generic placeholder resources.

### Backend Structure

- Added `backend/pyproject.toml` configured for Python, FastAPI, Pydantic settings, SQLAlchemy 2.0 async support, Alembic, asyncpg, uv, pytest, and ruff.
- Added `backend/README.md` with local setup, test, lint, and migration commands.
- Added `backend/.env.example` with app, API prefix, database URL, and CORS configuration.
- Added the application package under `backend/app/` with:
  - `api/` for route registration and API modules
  - `core/` for settings/configuration
  - `db/` for SQLAlchemy base classes and async session handling
  - `models/` for database models
  - `schemas/` for Pydantic request/response schemas
  - `services/` as the reserved home for domain service logic

### API Foundation

- Added FastAPI app creation in `backend/app/main.py`.
- Added API router mounting under `/api/v1`.
- Added `GET /api/v1/health` as a smoke-test endpoint.
- Added initial project endpoints:
  - `POST /api/v1/projects`
  - `GET /api/v1/projects`
  - `GET /api/v1/projects/{project_id}`

### Domain Model Foundation

Added SQLAlchemy models for the first-pass OpenTheory primitives:

- `Actor`
- `Project`
- `Thread`
- `Claim`
- `Artifact`
- `Evidence`
- `Checkpoint`
- `Branch`
- `Validation`
- `Contribution`
- `FundingAllocation`

The model layer includes UUID primary keys, timestamp mixins, relationship wiring, and enum-backed states for actors, projects, research stages, threads, claims, funding events, branches, and validations.

### Research Ledger Groundwork

- Added `Checkpoint` as the core immutable research state-change primitive.
- Added `checkpoint_parents` join table to support parent checkpoint DAG relationships.
- Added explicit branch support for parallel research paths, dead ends, and later merge flows.
- Added append-only-friendly primitives for checkpoints and funding allocations.
- Added contribution records as the attribution/provenance substrate for humans, agents, and system actors.

### Database And Migrations

- Added Alembic configuration under `backend/alembic.ini`.
- Added async Alembic environment in `backend/alembic/env.py`.
- Wired Alembic metadata to the SQLAlchemy model registry.
- Added `backend/alembic/versions/.gitkeep` so the migration directory is retained before the first generated revision.

### Tooling And Verification

- Added pytest configuration and a health endpoint smoke test.
- Added ruff lint configuration.
- Verified the scaffold with:
  - `uv run ruff check .`
  - `uv run pytest`
- Confirmed SQLAlchemy metadata loads and registers 12 tables:
  - `actors`
  - `artifacts`
  - `branches`
  - `checkpoint_parents`
  - `checkpoints`
  - `claims`
  - `contributions`
  - `evidence`
  - `funding_allocations`
  - `projects`
  - `threads`
  - `validations`
