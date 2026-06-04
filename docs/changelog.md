# Changelog

## Index

- `0.3.4` — Enriched ledger read models: project aggregate counts, per-thread claim counts, and a checkpoint timeline showing author, action, and referenced claims/evidence. Completes `0.3.0`.
- `0.3.3` — Three-panel research workspace (threads / claims+evidence / checkpoint timeline) wired to all create/read flows, plus a localStorage-backed dev-actor switcher attached as `X-Dev-Actor-Id`.
- `0.3.2` — Checkpoint service as the sole append-only ledger write path, ORM-enforced append-only on checkpoints/refs/funding, and automatic contribution recording for all four create flows.
- `0.3.1` — Backend write path for threads, claims, and evidence, plus dev actors, two join tables, and the first real Alembic migration.
- `0.2.0` — Added the initial Next.js frontend scaffold with Tailwind, TanStack Query, typed API client, project index, and project detail surfaces.
- `0.1.0` — Added the initial FastAPI backend scaffold, domain model foundation, Alembic setup, and smoke-test tooling.

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
