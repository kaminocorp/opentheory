# Changelog

## Index

- `0.3.1` — Backend write path for threads, claims, and evidence, plus dev actors, two join tables, and the first real Alembic migration.
- `0.2.0` — Added the initial Next.js frontend scaffold with Tailwind, TanStack Query, typed API client, project index, and project detail surfaces.
- `0.1.0` — Added the initial FastAPI backend scaffold, domain model foundation, Alembic setup, and smoke-test tooling.

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
