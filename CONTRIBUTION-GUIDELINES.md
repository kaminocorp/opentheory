# Contribution Guidelines

Thanks for considering a contribution to **OpenTheory**. This document is the
contributor contract: the principles the codebase is built on, the invariants you
must not break, and the practical workflow.

It's long-ish on purpose. OpenTheory is a *ledger* — its value is that its records
can be trusted — so a handful of rules are genuinely load-bearing rather than
stylistic. Read [The prime directives](#the-prime-directives) and
[Do's and don'ts](#dos-and-donts) before your first PR; skim the rest as needed.

---

## Contents

- [Before you start](#before-you-start)
- [The prime directives](#the-prime-directives)
- [Do's and don'ts](#dos-and-donts)
- [Development setup](#development-setup)
- [Testing (read this part)](#testing-read-this-part)
- [Backend conventions](#backend-conventions)
- [Frontend conventions](#frontend-conventions)
- [Migrations](#migrations)
- [Security](#security)
- [Commits, changelog, and PRs](#commits-changelog-and-prs)
- [Good first contributions](#good-first-contributions)
- [Scope: what we're deliberately not building yet](#scope-what-were-deliberately-not-building-yet)

---

## Before you start

**`docs/` is the source of truth for intent.** The code tells you *what* is; the docs
tell you *what was meant*.

`docs/` is split along exactly that line, and the distinction matters — reading a
`vision/` doc as if it described the current build is the most common way to get
confused about this project:

| Folder | Contains | Read it as |
| --- | --- | --- |
| **`docs/blueprints/`** | The current model and architecture. | **What is.** If a blueprint disagrees with the code, the code wins and the blueprint is the bug — please report or fix it. |
| **`docs/vision/`** | Target state and design intent. | **What's meant — not what's built.** Each doc carries a status banner. |
| **`docs/operations/`** | Runbooks for deploying and operating the live system. | How to run it. |
| **`docs/plans/`** | Versioned implementation plans and the roadmap. | What's coming, and what's deferred on purpose. |

Before non-trivial domain work, read:

| Doc | Why |
| --- | --- |
| [`docs/blueprints/primitives.md`](docs/blueprints/primitives.md) | The domain model and its invariants. **The most important document.** |
| [`docs/blueprints/conceptual-model.md`](docs/blueprints/conceptual-model.md) | The mental model on one screen — the fastest orientation. |
| [`docs/vision/research-git.md`](docs/vision/research-git.md) | The git-for-research ledger semantics. **Target semantics** — operations are annotated *(built)* / *(planned)*: commit, branch, and log are built; merge, tag, blame, and semantic diff are not. |
| [`docs/blueprints/techstack.md`](docs/blueprints/techstack.md) | Stack choices, and the rationale and boundaries behind them. |
| [`docs/changelog.md`](docs/changelog.md) | The per-phase ledger of what shipped and why. **The fastest way to learn current state.** |
| [`docs/plans/roadmap-next-steps.md`](docs/plans/roadmap-next-steps.md) | What's next and what's deliberately deferred. |

For anything larger than a bug fix, **open an issue first** and describe the intent.
We'd rather discuss a design for ten minutes than have you build the right thing in a
way that has to be unwound.

---

## The prime directives

These six rules are why the platform is trustworthy. A PR that breaks one will be
asked to change, however good the rest of it is.

### 1. The checkpoint service is the *only* code path that writes a `Checkpoint`

`services/checkpoints.py::create_checkpoint` validates project/thread/branch/parent/ref
context, writes `checkpoint_refs`, links parents, and auto-records a `Contribution` —
all in one transaction.

**Compose with it; never mint checkpoints elsewhere.** The pattern to copy is
`create_validation`: write your own row, then call `create_checkpoint(...)` with
`extra_refs=[...]` and a `contribution_action`, so the event is recorded *through* the
chokepoint. Tool runs (`services/tool_runs.py`) and agent passes
(`services/agent_runs.py`) do the same thing — that's why an agent has no privileged
write path.

Two sub-rules that are easy to miss:

- **The chokepoint owns the single `commit`.** Helper writers
  (`contributions.record_contribution`, and composing services like validation and
  branching) `db.add(...)` to the caller's session and **never commit**. The whole flow
  is one atomic transaction — if any part fails, nothing orphans.
- **`extra_refs` are trusted; `payload.refs` are not.** Refs passed by a composing
  service are already validated in the same transaction, so they're not re-validated.
  Client-supplied refs are *always* validated. Don't blur this.

### 2. Append-only is enforced, not requested

`models/append_only.py` registers `before_update` / `before_delete` mapper guards on
`Checkpoint`, `CheckpointRef`, `FundingAllocation`, and `Validation`, raising
`AppendOnlyError` — so the invariant holds even if the route layer is bypassed.

**Corrections, reversals, and retractions are *new* records.** A re-assessment is a new
`Validation` row, never an edit to the old one. A dead end is a *closed branch*, not a
deleted one.

*Known caveat:* the guards fire on the ORM unit-of-work only. Bulk Core
`UPDATE`/`DELETE` and DDL (`drop_all` in tests) bypass them by design. Don't treat that
as a loophole for production code.

### 3. The backend enforces invariants even if the frontend is bypassed

The backend is the **single source of truth**. The frontend is presentation and
interaction only. If a rule matters, it lives in the backend service layer — assume
someone is calling the API with `curl`, because eventually an agent will be.

### 4. Funding, contribution, and validation never conflate

A funder finances; a contributor produces; a validator assesses. Roles may overlap on
the same *person*, but the **data model must never collapse them**. A funder earns no
intellectual credit; a validator is not an author. This is what keeps attribution
meaningful — it is not a detail to optimize away.

### 5. Humans and agents use the same primitives

Agents are an `Actor` type, not a parallel data model. **Build every capability
human-usable through the API first**, so that when agents use it, they're simply using
what humans already could. If you catch yourself writing an agent-only endpoint,
service, or table, stop and reconsider.

### 6. Honesty over confidence

Instruments answer with three outcomes: `result`, `refuted`, `undecided`.

- **`undecided` is never rendered as a pass.** If a tool can't settle the question, the
  system says so and the seam to escalate (to a proof) stays open.
- **A tool that *fails* mints nothing.** A failure is an error, not a ledger record —
  only genuine, citable outcomes reach the ledger. This is "the failure split", and
  it's deliberate.
- **Confidence is explainable through evidence and validation history, never a naked
  score.**

If your change would make the system sound more certain than it is, it's the wrong
change.

---

## Do's and don'ts

### Ledger and domain

| | |
| --- | --- |
| ✅ **Do** | Compose new write flows through `create_checkpoint` with `extra_refs` + `contribution_action`. |
| ❌ **Don't** | Instantiate `Checkpoint(...)` anywhere but `services/checkpoints.py`. |
| ✅ **Do** | Record a correction as a new row. |
| ❌ **Don't** | Update or delete a `Checkpoint`, `CheckpointRef`, `FundingAllocation`, or `Validation` — the ORM will raise `AppendOnlyError`, and if it doesn't, you've found a bug worth reporting. |
| ✅ **Do** | `db.add(...)` in helper writers and let the chokepoint commit. |
| ❌ **Don't** | `await db.commit()` inside a helper or composing service — it breaks transaction atomicity. |
| ✅ **Do** | Validate client-supplied refs. |
| ❌ **Don't** | Re-validate `extra_refs` from a composing service, or *skip* validating `payload.refs`. |
| ❌ **Don't** | Write to the database directly (scripts, SQL, bulk Core updates) for anything ledger-shaped — it bypasses invariants and contribution recording. |

### Models and schema

| | |
| --- | --- |
| ✅ **Do** | Export **every** new model from `backend/app/models/__init__.py`'s `__all__`. |
| ❌ **Don't** | Forget this. Alembic's `env.py` does `from app.models import *` — a model missing from `__all__` is **silently absent** from autogenerated migrations. This fails quietly, which is the worst way to fail. |
| ✅ **Do** | Name metadata columns `<entity>_metadata` (e.g. `claim_metadata`). |
| ❌ **Don't** | Use a bare `metadata` attribute — it's reserved by SQLAlchemy. |
| ✅ **Do** | Put enums in `models/enums.py` as `StrEnum`, mapped to **named** Postgres types: `Enum(ClaimStatus, name="claim_status")`. |
| ❌ **Don't** | Change an existing `name=` — it *is* the database type name. |
| ✅ **Do** | Compose `IdMixin` + `TimestampMixin` from `db/base.py` on every model. |

### Layering

| | |
| --- | --- |
| ✅ **Do** | Keep route handlers thin: authenticate → authorize → delegate to a service. |
| ❌ **Don't** | Put domain logic or invariant enforcement in `api/routes/` or in Next.js API routes. |
| ✅ **Do** | Declare the `ActingActor` dependency on every write endpoint. |
| ❌ **Don't** | Invent or infer an actor inside a handler. |
| ✅ **Do** | Route all frontend backend-calls through `frontend/src/lib/api.ts`'s `request` helper. |
| ❌ **Don't** | `fetch()` the backend directly from a component. |
| ✅ **Do** | Store large artifacts (PDFs, datasets, plots, notebooks) in object storage. |
| ❌ **Don't** | Put blobs in Postgres — it stores hashes, metadata, and links only. |

### General

| | |
| --- | --- |
| ✅ **Do** | Keep changes small, deployable, and demoable — the release cadence is deliberate (`0.4.1`–`0.4.5` each landed one slice of `0.4.0`). |
| ❌ **Don't** | Open a 3,000-line PR that changes the data model, the API, and the UI at once. |
| ✅ **Do** | Match the surrounding code's idiom, naming, and comment density. |
| ❌ **Don't** | Introduce a new pattern, library, or abstraction for something the codebase already solves — look for the existing helper first. |
| ✅ **Do** | Comment the *constraint the code can't show* (a why, an invariant, a caveat). |
| ❌ **Don't** | Comment what the next line does, or leave notes addressed to the reviewer. |
| ❌ **Don't** | Split the monolith. One frontend, one backend, one database — until agent execution or background workloads create a *real* need. |

---

## Development setup

**Prerequisites:** [`uv`](https://docs.astral.sh/uv/) (Python 3.12+), Node.js + `npm`,
and Postgres for anything touching the ledger.

```bash
# Backend  → http://localhost:8000  (OpenAPI at /docs)
cd backend
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run fastapi dev app/main.py

# Frontend → http://localhost:3000
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

A root `Makefile` wraps the common tasks — run `make` to list every target:
`make dev`, `make migrate`, `make migration m="…"`, `make test`, `make lint`,
`make sync`, `make fe`.

### Checks that must pass before you open a PR

```bash
cd backend  && uv run ruff check . && uv run pytest
cd frontend && npm run typecheck && npm run lint && npm run build
```

---

## Testing (read this part)

> [!WARNING]
> **A green `pytest` proves very little by default.** The DB-backed suites — the ones
> covering the ledger, services, toolbench, and agent loop — **auto-skip** unless
> `TEST_DATABASE_URL` (or a *localhost* `DATABASE_URL`) points at a reachable Postgres.
> Without one you'll see something like `199 passed, 117 skipped` and a false sense of
> safety. **Set the env var before trusting a passing run for any ledger, service,
> toolbench, or agent change.**

```bash
# The real gate for ledger/service/toolbench/agent work:
TEST_DATABASE_URL='postgresql+asyncpg://user:pass@localhost:5432/opentheory_test' uv run pytest

# Narrow runs
uv run pytest tests/agent/ tests/toolbench/
uv run pytest tests/test_app.py::test_health_endpoint
```

> [!CAUTION]
> **The test suite is destructive — it resets the entire `public` schema.** Point
> `TEST_DATABASE_URL` at a **throwaway database only**. Never at a database holding
> data you care about, and never at production.
>
> `tests/conftest.py` guards against the most likely accident: it accepts the implicit
> `DATABASE_URL` fallback *only* when the host is `localhost`, `127.0.0.1`, or `::1`,
> and treats a missing host (socket-form URLs) as "not proof of localhost", failing
> safe by skipping. That guard protects a stray `export DATABASE_URL=<prod>`. It does
> **not** protect an explicit `TEST_DATABASE_URL` — that one is on you.

**Conventions:**

- `asyncio_mode = "auto"` (pytest-asyncio) — no `@pytest.mark.asyncio` needed.
- `TestClient` works for sync endpoint tests against `create_app()`.
- Prefer a **DB-free gate test** where one is possible (e.g. "unauthenticated `POST`
  → `401`", "flag off → `404`"), because it runs in everyone's default suite. Pair it
  with DB-backed round-trip tests for the real behavior.
- Test the invariant, not just the happy path: that a failure **minted nothing**, that
  an append-only edit **raised**, that a non-member got `403`.

---

## Backend conventions

- **Python 3.12+, modern typing:** `X | None`, `list[...]`, `StrEnum`. Async
  throughout — DB access is async SQLAlchemy.
- **Lint:** `ruff`, line length 100, rules `E`/`F`/`I`/`UP`/`B`.
- **Layout:** requests flow `api/routes/` → `services/` → `models/`.
  - `core/config.py` — `Settings` (pydantic-settings) from `.env`; access via the
    module-level `settings` singleton.
  - `db/session.py` — async engine + the `get_db` dependency yielding `AsyncSession`.
  - `schemas/` — Pydantic models; use `ConfigDict(from_attributes=True)` for read models.
  - `api/router.py` — assembles the versioned router mounted at `settings.api_v1_prefix`.
- **New settings** get a sensible, *safe* default. New capabilities land **dark** where
  practical (see `agent_loop_enabled`) so deploying is a no-op until deliberately enabled.

### Writing a new instrument

The best-paved path into the codebase. Follow `app/toolbench/instruments/calc_eval.py`:

1. Define `InputModel` / `OutputModel` (Pydantic) and implement the adapter contract.
2. Register it in the registry — the public catalog is generated from the **code**
   registry, so it can never advertise an instrument the runtime lacks.
3. Return one of the three honest outcomes. Raise (mint nothing) on failure.
4. Run the conformance harness (`app/toolbench/conformance.py`).
5. Reuse the shared helpers in `instruments/_sympy_support.py` (`parse`,
   `split_relation`, `relation_holds`) rather than re-rolling them.
6. Add `*_latex` companions for renderable output if applicable. Note that
   `_canonical_output_hash` recursively strips `*_latex` keys — **presentation must
   never change dedup semantics**.

---

## Frontend conventions

- **Next.js App Router + TypeScript + Tailwind + TanStack Query.**
- `lib/api.ts` is the single typed backend client — all calls go through its `request`
  helper. Base URL from `NEXT_PUBLIC_API_BASE_URL`.
- `types/` mirrors backend read schemas. Keep them in sync when a schema changes.
- `components/` is grouped by feature (`projects/`, `shell/`, …).
- The design language is **OpenTheory Console** — a warm-obsidian command bridge: recessed
  bays, hairlines, IBM Plex Mono/Sans, a single crimson signal. Reuse the existing
  primitives (`Bay`, `Action`, …) rather than introducing new visual vocabulary.
- **Accessibility is part of "done":** accessible field names, `aria-live` for async
  console output, `aria-pressed` for toggles, inert zones where appropriate. Several
  past releases were pure a11y punch-lists — we care about this.
- Carry the honesty rules into the UI: `refuted` reads as a fail, `undecided` reads as
  a warning, **never** as a pass.

---

## Migrations

**The backend owns the schema.** The frontend has no database access.

```bash
uv run alembic revision --autogenerate -m "message"   # or: make migration m="message"
uv run alembic upgrade head                            # or: make migrate
```

- ✅ **Do** review the autogenerated migration by hand before committing it. Autogenerate
  is a first draft, not an oracle.
- ✅ **Do** prefer **additive** migrations. Most of this project's migrations are
  additive on purpose.
- ✅ **Do** state in the PR whether a migration is additive or destructive.
- ❌ **Don't** edit a migration that has already been applied to a deployed environment.
- ❌ **Don't** forget the `models/__init__.py` export — an unexported model produces an
  empty migration and no error.

---

## Security

The toolbench executes user-supplied expressions. Treat it as hostile input, always.

> [!CAUTION]
> **SymPy's `parse_expr` compiles to `eval`, and a namespace allow-list does *not*
> sandbox it.** An allow-listed object leaks the real builtins via `sqrt.__globals__`;
> a constant leaks the class hierarchy via `(1).__class__.__mro__[-1].__subclasses__()`.
> This was a confirmed, member-reachable **RCE** in this codebase (closed in `8de2a29`).
>
> The fix, which you must not regress: `_reject_unsafe_source` validates the AST against
> a strict allow-list — arithmetic and calls to bare math names only; **no attribute
> access**, no underscore names — *before* `parse_expr` ever sees the text. If you add an
> instrument that parses expressions, **go through `_sympy_support.parse`.** Never call
> `parse_expr` directly.

Also:

- **Bound every input.** Past DoS holes: a power tower (`2**(2**30)`) that a
  constant-exponent cap missed, and unbounded geometry inputs. Assume adversarial size.
- **Never block the event loop** with synchronous CAS work — run it off the loop through
  the sandbox executors.
- **Respect the sandbox.** Instrument runs go through `acquire_run_slot` + the bounded
  executors: killable subprocess, wall-clock timeout, memory cap, concurrency limit.
  Timeout/OOM → `422`; busy → `503`.
- **Authorize explicitly.** Public reads are public; writes are membership-gated
  (`ensure_is_member`). Order matters: authenticate → resolve → authorize → act.
- **Pin external sources reproducibly:** URI + retrieval timestamp + response hash
  (`source.pin`, proven by `oeis.search`).

**Found a vulnerability?** Please **don't** open a public issue. Report it privately to
the maintainers via [GitHub Security Advisories](https://github.com/kaminocorp/opentheory/security/advisories/new).

---

## Commits, changelog, and PRs

### Changelog

**Update [`docs/changelog.md`](docs/changelog.md) for any release-scoped change.** It's
the project's own ledger — versioning is tracked there and in `docs/plans/`. Add your
entry to the index *and* the body, and state the blast radius explicitly, in the house
style:

> *"Backend-only — no schema, no migration."*
> *"Frontend-only — no backend, schema, or migration."*
> *"Migration `0013_agent_runs` (additive)."*

### Commit messages

Commits here are unusually descriptive, and that's deliberate — they're the narrative
record of *why*. Lead with a bolded one-line summary, then explain the reasoning, the
tradeoffs, and the blast radius. Look at `git log` for the house style.

### Pull requests

1. Fork and branch from `main`.
2. Keep the change small, deployable, and focused on one slice.
3. Run every check (see [Development setup](#development-setup)); run the **DB-backed**
   suite if you touched the ledger, services, toolbench, or the agent loop.
4. Update `docs/changelog.md`, and any `docs/` intent that your change makes stale.
5. Open the PR describing **what** changed and **why** — and what you *verified*, not
   just what you wrote. If tests fail or a step is unverified, say so; an honest PR
   beats a confident one.

---

## Good first contributions

- **A new Tier 0 instrument** — the adapter contract, code registry, and conformance
  harness make this the best-paved path. See
  [`docs/plans/toolbench-catalog.md`](docs/plans/toolbench-catalog.md) for the menu.
  Tier 1 retrieval pins (Crossref / arXiv / OpenAlex) on the proven `source.pin` shape
  are the current priority; a **Z3** instrument is next after that.
- **Read-model surfaces** — the workspace has more ledger structure available than it
  currently shows.
- **Tests** — particularly DB-free gate tests for security controls, and invariant
  tests ("this failure minted nothing").
- **Docs** — if something in `docs/` is stale or contradicts the code, that's a real
  bug in the source of truth. Fixing it is a genuine contribution.
- **Accessibility** — see [Frontend conventions](#frontend-conventions).

---

## Scope: what we're deliberately not building yet

Please don't submit these without discussing first — they're deferred *on purpose*, and
the reasoning is in [`docs/plans/roadmap-next-steps.md`](docs/plans/roadmap-next-steps.md):

| Item | Why not yet |
| --- | --- |
| **Splitting into services** | Modular monolith until agent execution or background workloads create a real need. |
| **Demo seed data** | Team preference: projects start from scratch. |
| **Real funding / settlement (Stripe, …)** | `FundingAllocation` is recorded; payment rails are future work. |
| **Reputation / influence** | In the vision doc; no data model yet — needs design, not code. |
| **Lean 4 / Mathlib** | Tier 2; forces a heavier execution substrate. Not until the sandbox and agent loop are stable. |
| **Continuous / scheduled agent loops** | The loop is deliberately bounded. Autonomy expands only behind budgets and human review. |
| **Object storage for large artifacts** | Planned; upload path not built. |

---

## A note on `CLAUDE.md`

[`CLAUDE.md`](CLAUDE.md) at the repo root is the same contract, written for AI coding
assistants working in this repo. If you change a convention here, change it there too —
and vice versa. Divergence between them is a bug.

---

**Questions?** Open an issue. Thanks for helping build a research record worth trusting.
