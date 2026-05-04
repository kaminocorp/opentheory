# Tech Stack

OpenTheory will use a split frontend/backend architecture:

```text
frontend/   Next.js app deployed to Vercel
backend/    FastAPI service deployed to Fly.io
database    Supabase Postgres
```

The platform should remain a modular monolith at the product level: one frontend, one backend API, one primary Postgres database. Avoid splitting into services until agent execution, background workloads, or scaling pressure creates a real need.

## Frontend

Use `Next.js` for the web application.

Core stack:

- `Next.js`
- `React`
- `TypeScript`
- `Tailwind CSS`
- `TanStack Query`
- `Vercel`

Why:

- Strong default routing and page structure.
- Excellent deployment path on Vercel.
- Good fit for public project pages, shareable research pages, and SEO-sensitive content.
- Large ecosystem for auth, payments, dashboards, graph views, editors, and rich product UI.
- Keeps the frontend focused on presentation and interaction while the backend owns domain invariants.

Frontend responsibilities:

- project discovery and public project pages
- authenticated contributor dashboard
- project/thread/claim navigation
- research ledger views
- funding/top-up flows
- evidence and artifact browsing
- validation and contribution UI
- graph or DAG visualization later

The frontend should call the FastAPI backend for authoritative reads and writes. Next.js API routes should not contain core domain logic.

## Backend

Use `FastAPI` for the backend API.

Core stack:

- `FastAPI`
- `Python`
- `Pydantic v2`
- `SQLAlchemy 2.0`
- `Alembic`
- `asyncpg`
- `uv`
- `pytest`
- `ruff`
- `Fly.io`

Why:

- Python is a better long-term fit for math, data, simulations, evaluation scripts, and future agent integration.
- FastAPI gives typed request/response models and clean OpenAPI generation.
- SQLAlchemy and Alembic provide mature control over a complex relational domain.
- Fly.io is a good fit for a standalone API service with background-worker options later.

Backend responsibilities:

- domain models and database schema
- project, thread, claim, checkpoint, branch, validation, contribution, and funding APIs
- append-only ledger invariants
- authorization and permissions
- funding ledger writes
- artifact metadata and storage coordination
- agent-facing APIs later
- background jobs later

The backend is the source of truth. It should enforce invariants even if the frontend is bypassed.

## Database

Use `Supabase Postgres` as the primary database.

Why:

- Postgres fits the domain: relational primitives, graph-like relationships, provenance, funding ledger entries, and audit history.
- Supabase provides managed Postgres, backups, dashboard tooling, and optional auth/storage features.
- The backend can connect directly to Postgres using SQLAlchemy rather than coupling domain logic to Supabase client APIs.

Initial database principles:

- `FundingAllocation` is append-only.
- `Checkpoint` is append-only.
- Claims are first-class records.
- Evidence and artifacts are separately addressable.
- Branches preserve parallel exploration and dead ends.
- Contributions record actor provenance.
- Agents and humans eventually use the same actor model.

## Storage

Use database records for metadata and object storage for large artifacts.

Likely options:

- Supabase Storage
- Cloudflare R2
- S3-compatible storage

Store large files outside Postgres:

- PDFs
- datasets
- generated plots
- simulation outputs
- notebooks
- reports

Postgres should store hashes, metadata, ownership, visibility, and links to object storage.

## Background Work

Do not introduce a queue immediately unless needed.

Likely later options:

- Fly.io worker process
- `arq`
- `Celery`
- `RQ`
- external workflow tools such as `Inngest` or `Trigger.dev`

Background jobs will become relevant for:

- artifact processing
- expensive validation
- long-running simulations
- agent runs
- periodic project summarization
- notification delivery

## Deployment

Frontend:

- deployed from `frontend/` to Vercel
- configured with backend API URL
- no direct database access

Backend:

- deployed from `backend/` to Fly.io
- connects to Supabase Postgres
- owns migrations
- exposes public API and later agent-facing API

Database:

- hosted on Supabase
- migrations managed from backend
- direct writes should go through backend application code

## Repository Layout

```text
opentheory/
  frontend/
    package.json
    src/
    app/
    public/

  backend/
    pyproject.toml
    alembic/
    app/
      api/
      core/
      db/
      models/
      schemas/
      services/
      main.py

  docs/
    vision.md
    primitives.md
    research-flow.md
    research-git.md
    techstack.md
```

## Current Decision

Chosen stack:

```text
Frontend: Next.js + React + TypeScript + Tailwind CSS + TanStack Query
Backend:  FastAPI + Python + Pydantic + SQLAlchemy + Alembic
Database: Supabase Postgres
Deploy:   Vercel frontend, Fly.io backend
```
