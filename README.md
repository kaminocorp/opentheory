<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="frontend/public/brand/mark-1024-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="frontend/public/brand/mark-1024-light.png">
  <img alt="OpenTheory" src="frontend/public/brand/mark-1024-light.png" width="120">
</picture>

# OpenTheory

**A platform for continuous, agent-driven research.**

Not one-off answers — *living* research projects. A tightly-scoped question is
decomposed into parallel threads, worked continuously, and every meaningful move
is written to an append-only, **git-shaped research ledger** with full provenance.
Knowledge compounds. Nothing resets between sessions. Dead ends are recorded, not deleted.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-live-success)](https://opentheory.vercel.app)
[![Version](https://img.shields.io/badge/version-0.8.10-crimson)](docs/changelog.md)
&nbsp;
![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-000?logo=next.js&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)
![Postgres](https://img.shields.io/badge/Postgres-4169E1?logo=postgresql&logoColor=white)

[**Live demo**](https://opentheory.vercel.app) · [Vision](docs/vision.md) · [Primitives](docs/primitives.md) · [Research-git](docs/research-git.md) · [Changelog](docs/changelog.md)

</div>

---

## Table of contents

- [What is OpenTheory?](#what-is-opentheory)
- [A git for research](#a-git-for-research)
- [Three roles, never conflated](#three-roles-never-conflated)
- [Domain primitives](#domain-primitives)
- [Architecture](#architecture)
- [Quickstart](#quickstart)
- [API surface](#api-surface)
- [Project structure](#project-structure)
- [Status &amp; roadmap](#status--roadmap)
- [Design principles](#design-principles-the-load-bearing-ones)
- [Contributing](#contributing)
- [License](#license)
- [Citation](#citation)

---

## What is OpenTheory?

Most AI research tooling produces **chat output**: an answer, then a blank slate.
OpenTheory produces a **transparent map of knowledge in motion** — active threads,
key findings, contradictions, and confidence levels you can inspect and trace back
to the exact evidence and actor that produced them.

A **project** poses a research question and is broken into **threads** explored in
parallel: proposing hypotheses, formalizing them, running simulations, testing
constraints. Each meaningful state change is committed as an immutable
**checkpoint** in the ledger, carrying *who* did it, *why*, and *what* evidence or
artifacts were involved. Projects run against an explicit **token budget**, so the
depth of investigation is bounded by the compute committed to it.

The product today is a **human-operable research ledger** — every primitive can be
driven by a person through the API. Agents are modeled as a *future* `Actor` type
that will use the **same** APIs, permissions, and provenance rules as humans —
never a parallel data model. The discipline: any capability is made
human-usable-through-the-API *first*, so that when agents arrive, they simply use
what humans already could.

> Example domains (from the [vision](docs/vision.md)): dark-matter model
> constraints, quantum gravity, the Riemann hypothesis, Navier–Stokes smoothness,
> P vs NP, protein folding beyond known structures, high-temperature
> superconductivity — hard, long-horizon problems where claims and constraints can
> be shown concretely.

---

## A git for research

The ledger borrows git's shape (full semantics in [`docs/research-git.md`](docs/research-git.md)):

| Git            | OpenTheory                                                |
| -------------- | --------------------------------------------------------- |
| commit         | **checkpoint** — an immutable, attributed state change    |
| branch         | a parallel line of exploration (dead ends preserved)      |
| merge / diff   | integrating or comparing research lines                   |
| blame          | provenance — who contributed what, on what evidence       |
| tag            | a marked, citable result                                  |

Two invariants make this real rather than cosmetic:

- **Append-only is enforced in code, not by convention.** ORM-level
  `before_update` / `before_delete` guards on `Checkpoint`, `CheckpointRef`,
  `FundingAllocation`, and `Validation` raise on any mutation — so the invariant
  holds even if the route layer is bypassed. Corrections, reversals, and
  retractions are *new* records; a re-assessment is a new validation row, never an
  edit.
- **A single checkpoint chokepoint.** All ledger writes funnel through one service
  (`create_checkpoint`) that validates context, writes the refs, links parents, and
  auto-records a `Contribution` — in one transaction, with one commit. Composing
  flows (validation, branching) call *into* it rather than minting checkpoints
  themselves, so provenance and attribution can't be skipped.

---

## Three roles, never conflated

A load-bearing design rule, enforced in the data model: **funding, intellectual
contribution, and validation are kept strictly separate.**

| Role            | Does                                                                 | Earns                                  |
| --------------- | ------------------------------------------------------------------- | -------------------------------------- |
| **Funder**      | finances a project/thread, directing compute via a **token budget** | influence over directions — *not* credit |
| **Contributor** | produces intellectual work — hypotheses, evidence, artifacts         | attribution for the work itself        |
| **Validator**   | assesses results, building *explainable* confidence                 | a provenance trail, *not* authorship   |

A funder financing a thread earns no intellectual credit for it; a validator
assessing a claim is not its author. Roles may overlap on the same person, but the
*data model* never collapses them — that's what keeps credit meaningful while
allowing broad participation. Confidence is always explainable through evidence and
validation history, **never a naked score**.

---

## Domain primitives

The core graph (full relationships and invariants in [`docs/primitives.md`](docs/primitives.md)):

| Primitive            | What it is                                                                 |
| -------------------- | ------------------------------------------------------------------------- |
| `Project`            | top-level research container — the question, scope, and everything under it |
| `Thread`             | a focused line of inquiry worked in parallel with others                  |
| `Claim`              | a first-class structured assertion (hypothesis, constraint, result, …)    |
| `Evidence`           | a source/observation supporting, weakening, or falsifying a claim; content-pinned |
| `Artifact`           | a produced research object (proof, model, dataset, plot); content-addressed |
| `Checkpoint`         | an immutable, attributed snapshot of a meaningful state change            |
| `Branch`             | a parallel research path; dead ends stay visible                          |
| `Validation`         | an immutable structured review of a claim/checkpoint/branch               |
| `Contribution`       | the attribution/provenance record — who did what, against which primitive |
| `FundingAllocation`  | an append-only ledger entry for money directed at a project               |
| `Account`            | the auth **principal** (one per login) that owns `Actor`s and funding     |
| `Actor`              | the entity performing an action — `human` \| `agent` \| `system`          |

```text
Project
  ├── FundingAllocation
  ├── Thread ──┬── Claim ── Evidence / Artifact
  │            ├── Checkpoint
  │            └── Branch
  ├── Claim · Artifact · Evidence · Checkpoint
  ├── Validation
  └── Contribution

Account  (auth principal)        Actor  (research provenance)
  ├── Actor                        ├── Contribution
  └── FundingAllocation            ├── Checkpoint   (authors)
                                   └── Validation   (performs)
```

> **Why `Account` *and* `Actor`?** Identity, authorization (`roles`), and funding
> attribution describe the *principal* (the thing holding a login / payment method)
> and live on `Account`. Research provenance is attributed to the `Actor`. An agent
> is later just an `Actor` with metadata describing its model, provider, and run
> context — no new foundation.

---

## Architecture

Intentionally a **modular monolith**: one Next.js frontend, one FastAPI backend,
one Postgres database. We do not split into services until agent execution or
background workloads create a real need.

```text
frontend/   Next.js (App Router) + React + TypeScript + Tailwind + TanStack Query  →  Vercel
backend/    FastAPI + SQLAlchemy 2.0 (async) + Alembic + asyncpg + Pydantic v2     →  Fly.io
database    Supabase Postgres
```

**The backend is the single source of truth and enforces every domain invariant
even if the frontend is bypassed.** The frontend is presentation and interaction
only; it calls the backend for all authoritative reads and writes (no core domain
logic in Next.js routes). Large artifacts (PDFs, datasets, plots, notebooks) go to
object storage — Postgres stores only hashes, metadata, and links.

Backend requests flow `api/routes/` → `services/` → `models/`. Route handlers stay
thin; domain logic and invariant enforcement live in the **service layer**.
Authentication is a verified **Supabase JWT** (ES256 / JWKS), which just-in-time
provisions the acting `Actor` for each write. Rationale for each choice is in
[`docs/techstack.md`](docs/techstack.md).

---

## Quickstart

> **Prerequisites:** [`uv`](https://docs.astral.sh/uv/) (Python 3.12+) for the
> backend, Node.js + `npm` for the frontend, and a Postgres database (local or a
> Supabase instance) for anything that touches the ledger.

### Backend — `cd backend`

```bash
uv sync                            # install dependencies
cp .env.example .env               # configure (DATABASE_URL, auth, CORS, …)
uv run alembic upgrade head        # apply migrations
uv run fastapi dev app/main.py     # → http://localhost:8000  (OpenAPI at /docs)
```

### Frontend — `cd frontend`

```bash
npm install
cp .env.example .env.local         # set NEXT_PUBLIC_API_BASE_URL (default http://localhost:8000/api/v1)
npm run dev                        # → http://localhost:3000
```

### Day-to-day

```bash
# backend
uv run ruff check .                # lint (line-length 100; rules E/F/I/UP/B)
uv run pytest                      # tests — DB-backed suites auto-skip without TEST_DATABASE_URL
uv run alembic revision --autogenerate -m "message"

# frontend
npm run typecheck                  # tsc --noEmit
npm run lint
npm run build
```

A root `Makefile` wraps the common tasks: `make dev`, `make migrate`, `make test`, `make fe`.

> **Note on tests:** the DB-backed suites (`test_checkpoints`, `test_validations`,
> `test_branches`, `test_read_models`, `test_research_flow`) only run when
> `TEST_DATABASE_URL` (or `DATABASE_URL`) points at a reachable Postgres. Without
> one, `pytest` is green but mostly *skipped* — set the env var before trusting a
> passing run for ledger or service changes.

---

## API surface

The versioned API is mounted at `/api/v1`. Interactive OpenAPI docs are served at
`/docs` when the backend is running. Live: `https://opentheory-backend.fly.dev/api/v1`.

| Group              | Surface                                                              |
| ------------------ | ------------------------------------------------------------------- |
| `health`           | liveness probe                                                      |
| `me` / `accounts`  | the signed-in principal, `@username`, account management            |
| `projects`         | projects, stewardship/ownership, rich-text background, agent-model roster |
| `threads`          | open and read threads inside a project                              |
| `claims`           | create/read claims and their validation history                    |
| `evidence`         | attach and browse content-pinned evidence                           |
| `checkpoints`      | the ledger write path (the chokepoint) and timeline reads          |
| `validations`      | record immutable assessments of claims/checkpoints/branches        |
| `branches`         | fork from a checkpoint, record on a branch, close as dead-end/superseded |
| `funding`          | source-aware funding allocations (append-only)                     |
| `invitations`      | invite collaborators by `@username`/email; accept/decline inbox    |
| `actors`           | research-provenance actor identities                               |
| `agent-models`     | curated OpenRouter model catalog + per-project crew assignment     |

---

## Project structure

```text
opentheory/
├── backend/                 FastAPI service (source of truth)
│   └── app/
│       ├── api/routes/      thin HTTP handlers, one file per resource
│       ├── services/        domain logic + invariant enforcement (checkpoint chokepoint)
│       ├── models/          SQLAlchemy domain models, one per primitive
│       ├── schemas/         Pydantic request/response models
│       ├── core/            settings, config, curated model catalog
│       └── db/              async engine, session, Base mixins
│   └── alembic/             migrations (backend owns the schema)
├── frontend/                Next.js App Router app
│   └── src/
│       ├── app/             pages
│       ├── components/      feature-grouped UI (Kamino Console design language)
│       ├── lib/api.ts       the single typed backend client
│       └── types/           domain types mirroring backend read schemas
└── docs/                    source of truth for intent — read before non-trivial work
    ├── primitives.md        the domain model and its invariants (most important)
    ├── research-git.md      git-for-research ledger semantics
    ├── techstack.md         stack choices and their rationale
    ├── vision.md            product vision and example domains
    ├── plans/               versioned implementation plans
    └── changelog.md         per-phase ledger of what shipped and why
```

---

## Status &amp; roadmap

OpenTheory is **live** (Vercel frontend + Fly.io backend + Supabase) and ships in
small, deployable phases tracked in [`docs/changelog.md`](docs/changelog.md).

**Shipped — a human-operable research ledger:**

- The full ledger write path: open projects/threads, add claims, attach evidence,
  record immutable checkpoints, fork/close branches, record validations — all
  through the enforced chokepoint, all attributed.
- Real identity: verified Supabase auth provisions actors; project **ownership**,
  `@username` handles, and a collaborator invitation/inbox flow.
- Source-aware **funding allocations** as a separate, append-only concern.
- A per-project **research crew** roster assigning OpenRouter models to four roles
  (Research Lead / Thread Manager / Researcher / Research Assistant) — the
  *configuration* layer that the agent execution surface will be driven by.

**Next — toward an autonomous research engine:**

- **Agents as first-class operators**, using the same APIs, permissions, and
  provenance as humans; they *propose* checkpoints a human or orchestrator can
  accept, reject, or branch.
- Projects run **continuously** against their token budgets.
- **Reputation and influence** accrue to those who consistently back, produce, and
  validate the right directions.
- Real funding and settlement replace simulated allocations.

---

## Design principles (the load-bearing ones)

If you contribute, preserve these — they are why the platform is trustworthy:

1. **The checkpoint service is the only path that writes a `Checkpoint`.** Compose
   with it; never mint checkpoints in another service.
2. **Append-only is ORM-enforced.** Corrections are new rows. Never edit a
   `Checkpoint`, `CheckpointRef`, `FundingAllocation`, or `Validation`.
3. **The backend enforces invariants even if the frontend is bypassed.** No core
   domain logic in the frontend.
4. **Funding, contribution, and validation never conflate** in the data model.
5. **Humans and agents use the same primitives** — build it human-usable through
   the API first.
6. **Workflow stages are optional metadata, not hard-coded platform law.**

New models must be exported from `backend/app/models/__init__.py` (Alembic
discovers metadata via `from app.models import *`). See [`CLAUDE.md`](CLAUDE.md) for
the full contributor contract.

---

## Contributing

Contributions are welcome. Before non-trivial domain work, read
[`docs/primitives.md`](docs/primitives.md) and [`docs/research-git.md`](docs/research-git.md)
— `docs/` is the source of truth for intent.

1. Fork and branch from `main`.
2. Keep changes small and deployable; match the existing code's idiom.
3. Run the checks: `uv run ruff check . && uv run pytest` (backend),
   `npm run typecheck && npm run lint && npm run build` (frontend).
4. Update [`docs/changelog.md`](docs/changelog.md) for any release-scoped change.
5. Open a PR describing *what* changed and *why*.

---

## License

Licensed under the [Apache License 2.0](LICENSE).

---

## Citation

```bibtex
@software{opentheory2026,
  title  = {OpenTheory: A Platform for Continuous, Agent-Driven Research},
  author = {Kamino Corp and the OpenTheory Contributors},
  year   = {2026},
  url    = {https://github.com/kaminocorp/opentheory}
}
```

<div align="center">
<sub>Built as a modular monolith. Designed so that when agents arrive, they simply use what humans already could.</sub>
</div>
