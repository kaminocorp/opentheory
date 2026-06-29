# Implementation Plan — `Account` owns `Actor`

> Methodical, phase-by-phase execution plan for the design in
> [`account-owns-actor.md`](./account-owns-actor.md). Read that proposal first — this file is the
> *how* and *in what order*, not the *why*. Each phase has concrete tasks, the exact files touched,
> and an acceptance gate. Do not start a phase until the previous gate is green.

## Scope recap (from the proposal's locked decisions)

- Add `Account` (the auth principal, one per `auth.users` login); it **owns** `Actor`s.
- Move to `accounts`: `external_id` (the `sub`), `roles`, and **funding attribution**
  (`FundingAllocation.actor_id → account_id`).
- Keep on `actors`: research provenance (`Checkpoint.author_id`, `Contribution.actor_id`,
  `Validation.actor_id`) and the `ActingActor` return type (still an `Actor`).
- No seeding; dev actors stay `account_id IS NULL`; `system` actor has no account.
- Expose `Account` now via a nested `account` on `/me`.

## Sequencing & deploy strategy

This is a **destructive** migration (it drops `actors.external_id`, `actors.roles`,
`funding_allocations.actor_id`), so the **backend code and migration must ship together** — old code
reading `actor.roles` breaks the instant the column is gone. Phases 1–8 are one logical release built
and verified end-to-end; Phase 9 is the coordinated cutover.

```
Phase 0  Pre-flight & live data audit        (GATE — read-only, no code)
Phase 1  Backend domain models
Phase 2  Pydantic schemas
Phase 3  Auth resolution + roles  ──┐ depend on Phase 1
Phase 4  Funding service rewiring  ──┘
Phase 5  API routes (/me, account bootstrap)   depends on Phases 2–4
Phase 6  Alembic migration 0006                depends on Phases 1–2 (final metadata)
Phase 7  Backend tests                          depends on Phases 1–6
Phase 8  Frontend (types + identity hook)       independent of 3–7; depends on Phase 5 shape
Phase 9  Throwaway-DB round-trip → live cutover → changelog
```

> **Optional zero-downtime variant (expand/contract).** If the live app ever has concurrent users,
> split Phase 6/9: first migration *adds* `accounts` + the two `account_id` columns and backfills
> while **keeping** the old columns (dual-write in code); a later migration drops the old columns once
> nothing reads them. The proposal chose the clean single-migration path (Decision 3) given current
> solo/low-traffic scale — this plan follows that, and flags expand/contract here so it's a
> conscious choice, not an oversight.

> **Testing/deploy policy (repo memory).** Default test runs are DB-free. DB-backed tests and the
> migration round-trip require a **throwaway** Postgres and an **explicit greenlight** — never the
> live DB. Verify behavior against the live deployment after cutover.

---

## Phase 0 — Pre-flight & live data audit  ·  GATE (no code)

The whole risk is backfill correctness. Confirm the preconditions on the **live** DB (read-only
`SELECT`s only) before writing any migration.

- [ ] **A0.1** Run, expecting **0** rows / counts:
  - `SELECT count(*) FROM actors WHERE type='human' AND external_id IS NULL;`
  - `SELECT external_id FROM actors WHERE external_id IS NOT NULL GROUP BY 1 HAVING count(*)>1;`
  - `SELECT count(*) FROM actors WHERE type IN ('agent','system') AND external_id IS NOT NULL;`
  - `SELECT count(*) FROM funding_allocations f JOIN actors a ON f.actor_id=a.id WHERE a.type<>'human';`
- [ ] **A0.2** Record current counts (`actors` by type, `funding_allocations`) for a post-migration
  reconciliation check.
- [ ] **A0.3** Decide the cutover window (brief; backend + migration deploy together).

**Gate:** all A0.1 queries return empty/0. If any fails, stop and resolve the data before proceeding.

---

## Phase 1 — Backend domain models

- [ ] **A1.1** Create `backend/app/models/account.py` — the `Account` model per the proposal sketch
  (`external_id` unique nullable, `display_name`, `email`, `roles` ARRAY w/ `server_default "'{}'"`,
  `account_metadata` JSON, `actors` + `funding_allocations` relationships).
- [ ] **A1.2** Edit `backend/app/models/actor.py`:
  - remove `external_id` and `roles` columns;
  - add `account_id: Mapped[UUID | None]` FK → `accounts.id` `ondelete="SET NULL"`;
  - add `account = relationship("Account", back_populates="actors")`;
  - remove the `funding_allocations` relationship (moves to `Account`).
- [ ] **A1.3** Edit `backend/app/models/funding.py`: rename `actor_id` → `account_id` (FK
  `accounts.id`, `ondelete="SET NULL"`, `index=True`); `actor` relationship → `account`
  (`back_populates="funding_allocations"`).
- [ ] **A1.4** Edit `backend/app/models/__init__.py`: import `Account`, add `"Account"` to `__all__`
  (required for Alembic autogenerate discovery).
- [ ] **A1.5** Confirm `models/append_only.py` is **unchanged** — `Account` is a mutable identity row
  and must **not** be guarded (sanity-check `FundingAllocation` is still guarded).

**Gate:** `uv run python -c "from app.models import *"` imports cleanly; `uv run ruff check .` passes.

---

## Phase 2 — Pydantic schemas

- [ ] **A2.1** Create `backend/app/schemas/account.py`:
  - `AccountRead` (`id`, `external_id`, `display_name`, `email`, `roles`, timestamps;
    `ConfigDict(from_attributes=True)`);
  - `AccountSummary` (`id`, `display_name`, `email` — the funder display shape);
  - `AccountCreate` (`external_id?`, `display_name`, `email?`, `roles`) — the dev/test bootstrap that
    inherits the seed fields removed from `ActorCreate`.
- [ ] **A2.2** Edit `backend/app/schemas/actor.py`:
  - `ActorRead`: drop `external_id` and `roles`; add `account_id: UUID | None`;
  - `ActorCreate`: drop `external_id` and `roles`; add optional `account_id`;
  - define the `/me` response shape — either add `account: AccountRead | None` to `ActorRead`, or a
    dedicated `MeRead { ...actor fields, account }`. **Recommend `MeRead`** so `ActorRead` stays the
    plain entity and `/me` owns the nested view.
- [ ] **A2.3** Edit `backend/app/schemas/funding.py`: `FundingRead.actor_id → account_id`,
  `actor: ActorSummary | None → account: AccountSummary | None`. `FundingCreate` unchanged.

**Gate:** `ruff` clean; no remaining references to `ActorRead.roles` / `.external_id` in schemas.

---

## Phase 3 — Auth resolution + roles

- [ ] **A3.1** Edit `backend/app/core/roles.py`: add
  `account_is_internal(account) -> bool`; redefine `actor_is_internal(actor)` to delegate
  (`account_is_internal(actor.account)`). Keep `INTERNAL_ROLE`.
- [ ] **A3.2** Rewrite `_resolve_or_provision` in `backend/app/api/deps.py` per the proposal:
  - resolve `Actor` by joining `Account` on `Account.external_id == sub` and
    `Actor.type == HUMAN`, with `contains_eager(Actor.account)`;
  - on miss, create `Account` (with `roles` from the email allowlist) + primary `human` `Actor`
    (`account=account`, `actor_metadata={"email": …}`), single `commit`, `IntegrityError` race
    re-read;
  - return the `Actor`.
- [ ] **A3.3** Confirm `require_internal` (deps) is unchanged in signature and reads
  `actor.account` (now eager-loaded). `get_acting_actor`, `_resolve_dev_actor`, and the
  `auth_dev_header_enabled` branch are otherwise untouched.

**Gate:** `ruff` clean; DB-free auth tests still import/collect (full run in Phase 7).

---

## Phase 4 — Funding service rewiring

- [ ] **A4.1** Edit `backend/app/services/funding.py::create_funding`:
  - native gate uses `actor_is_internal(actor)` (now via `actor.account`);
  - `FundingAllocation(..., account_id=actor.account_id, ...)` (was `actor_id`);
  - the `fund` `Contribution` **stays `actor=actor`** (unchanged `record_contribution` call) — the
    allocation is the account's money, the contribution is the actor's act (Decision 5).
- [ ] **A4.2** Edit `_enrich` / `_to_read` to resolve the funder **`Account`** (batch query
  `Account` by `account_id`) and populate `FundingRead.account_id` / `account: AccountSummary`.
- [ ] **A4.3** Confirm `project_budget` needs **no change** (it reads `FundingAllocation` amounts,
  not the funder) — re-read to be sure.

**Gate:** `ruff` clean; `services/checkpoints.py` and other services confirmed untouched.

---

## Phase 5 — API routes (`/me`, account bootstrap)

- [ ] **A5.1** Edit `backend/app/api/routes/me.py`: return `MeRead` — the resolved `Actor` plus its
  nested `account` (already eager-loaded by `_resolve_or_provision`).
- [ ] **A5.2** Account bootstrap for dev/test (Decision 8 — no seeding, but tests need to *build* an
  internal account explicitly): add a **dev-gated** `POST /accounts` mirroring the `POST /actors`
  guard (`404` unless `auth_dev_header_enabled`), backed by a new
  `services/account.py::create_account`. Mount an `accounts` router in `api/router.py`.
- [ ] **A5.3** Edit `backend/app/api/routes/actors.py` / `services/actors.py`: `create_actor` now
  accepts an optional `account_id` (link a dev actor to a bootstrap account). The **PII gate is
  preserved** — `GET /actors` and `GET /accounts` stay dev-gated because `AccountRead` exposes
  `external_id` + email + roles (the `0.6.1` leak class moved with the fields).

**Gate:** `ruff` clean; OpenAPI builds (`uv run python -c "from app.main import create_app; create_app()"`).

---

## Phase 6 — Alembic migration `0006_accounts.py`

Author by hand (the backfills are not autogeneratable); use autogenerate only to cross-check the DDL.
`down_revision = "0005_funding_source"`.

- [ ] **A6.1** `upgrade()` in this exact order (per the proposal's migration block):
  1. `create_table("accounts", …)`;
  2. `add_column("actors", account_id …)`;
  3. backfill `accounts` from `human` actors (`INSERT … SELECT`), then
     `UPDATE actors SET account_id` by `external_id` join;
  4. `add_column("funding_allocations", account_id …, index)`;
  5. backfill `funding.account_id` from `actors.account_id` via `f.actor_id = a.id`;
  6. create partial unique index `uq_actors_one_human_per_account ON actors(account_id) WHERE type='human'`;
  7. `drop_column("funding_allocations","actor_id")`;
  8. `drop_column("actors","external_id")`; `drop_column("actors","roles")`.
- [ ] **A6.2** `downgrade()` reverses: re-add the three dropped columns; backfill
  `actors.external_id`/`actors.roles` from `accounts`, `funding.actor_id` from the account's `human`
  actor; drop the partial index, the two `account_id` columns, and `accounts`.
- [ ] **A6.3** Use raw `op.get_bind().execute(sa.text(...))` for backfills (as the enum migrations
  do). Mind enum/ARRAY casts (`'{}'::text[]` etc.).

**Gate:** migration file lints; **round-trip deferred to Phase 9** (needs a throwaway DB).

---

## Phase 7 — Backend tests

Run the DB-free suite continuously; run DB-backed tests in Phase 9 against a throwaway DB.

- [ ] **A7.1** `tests/conftest.py`: add an account helper/fixture (create `Account` with roles +
  `Actor` linked) so role/funding tests can build an internal funder without seeding.
- [ ] **A7.2** `tests/test_auth.py`: JIT provision now mints **one** `Account` + one `human` `Actor`;
  second authed request reuses both; concurrent first-login race → exactly one account, no orphan.
- [ ] **A7.3** `tests/test_actors.py`: the PII-gate tests assert the moved fields (`external_id`,
  email, `roles`) are gated wherever they now surface (`GET /actors`, `GET /accounts`, and `/me`'s
  nested account requires auth). Keep them DB-free where possible (mutation-verified, per `0.6.8`).
- [ ] **A7.4** `tests/test_funding.py`: funder is the **account**; native funding `403`s a
  non-internal / account-less actor and succeeds for an internal account; allocation `account_id` is
  the funder's account; the `fund` contribution is still actor-attributed; `project_budget`
  output unchanged.
- [ ] **A7.5** New: the partial unique index rejects a second `human` actor per account.
- [ ] **A7.6** `tests/test_wiring.py` + any model-count assertions: account for the new `accounts`
  table / `/accounts` write path.

**Gate:** `uv run pytest` green (DB-free subset) with the new collection; DB-backed assertions ready
to run in Phase 9.

---

## Phase 8 — Frontend (types + identity hook)

The consumers (`auth-menu.tsx`, `funding-panel.tsx`) read `isInternal`/`displayName` through
`useActingIdentity()`, so **only the type and the hook change** — the components are insulated.

- [ ] **A8.1** `frontend/src/types/research.ts`: remove `external_id`/`roles` from `Actor`; add an
  `Account` type (`id`, `display_name`, `email`, `roles`); make the `/me` (`Me`) type carry a nested
  `account`. Update `FundingRead`/funding types: `actor_id`/`actor` → `account_id`/`account`.
- [ ] **A8.2** `frontend/src/lib/use-identity.ts`: source `roles` from `me?.account?.roles ?? []`;
  `isInternal = roles.includes("internal")`. Keep the hook's public shape identical
  (`{ displayName, isInternal, canWrite, roles }`) so consumers don't change.
- [ ] **A8.3** Update the `lib/api.ts:89` comment + any funder-display in `funding-panel.tsx` that
  read `actor` off an allocation → `account`.
- [ ] **A8.4** Confirm `dev-actor-provider.tsx` still works: it sets `X-Dev-Actor-Id`; `/me` resolves
  the actor + its account, so `isInternal` reflects the linked account. (Dev ergonomics: to test
  funding locally, bootstrap an internal `Account` via `POST /accounts`, link a dev actor to it.)

**Gate:** `npm run typecheck` / `lint` / `build` green; 6/6 routes generate.

---

## Phase 9 — Round-trip, live cutover, changelog

- [ ] **A9.1** **Throwaway DB (greenlight required):** provision a scratch Postgres, restore a copy of
  prod (or load representative rows), `alembic upgrade head`, run the full DB-backed pytest suite,
  then `alembic downgrade -1` and confirm the dropped columns return with values intact. Reconcile
  counts against A0.2.
- [ ] **A9.2** **Cutover (live):** during the Phase 0 window — apply migration `0006` and deploy the
  new backend together (Fly release command runs the migration; old code must not run against the new
  schema). Then redeploy Vercel (frontend types/`NEXT_PUBLIC_*` baked at build).
- [ ] **A9.3** **Live verification:** sign in → `/me` returns the nested `account` with `roles`; the
  identity menu shows the internal badge for an allowlisted email; an internal user can fund a project
  and the allocation/budget reflect it; a non-internal user is `403`'d. Spot-check the funding history
  shows the account as funder.
- [ ] **A9.4** **Changelog:** add a `docs/changelog.md` entry (propose the opening slice of `0.7.0`,
  or a standalone `0.6.x` schema release if pulled ahead): `Account` added owning `Actor`s;
  `external_id`/`roles`/funding attribution moved to `accounts`; research provenance FKs + the
  `ActingActor` contract unchanged; migration `0006`; the data audit + round-trip as the gate.
- [ ] **A9.5** Move this plan + the proposal from `docs/executing/` to `docs/completions/` (matching
  the repo's executing→completions lifecycle) and write the completion note.

**Gate:** live verification (A9.3) passes; changelog updated.

---

## File-change index (quick reference)

| File | Phase | Change |
|---|---|---|
| `backend/app/models/account.py` | 1 | **new** `Account` model |
| `backend/app/models/actor.py` | 1 | − `external_id`, − `roles`, + `account_id`/`account`, − `funding_allocations` |
| `backend/app/models/funding.py` | 1 | `actor_id` → `account_id`; `actor` → `account` |
| `backend/app/models/__init__.py` | 1 | export `Account` |
| `backend/app/schemas/account.py` | 2 | **new** `AccountRead`/`AccountSummary`/`AccountCreate` |
| `backend/app/schemas/actor.py` | 2 | move seed fields out; `MeRead` |
| `backend/app/schemas/funding.py` | 2 | `actor*` → `account*` |
| `backend/app/core/roles.py` | 3 | `account_is_internal`; `actor_is_internal` delegates |
| `backend/app/api/deps.py` | 3 | rewrite `_resolve_or_provision` (account-keyed, eager-loaded) |
| `backend/app/services/funding.py` | 4 | account-attributed allocation + enrich |
| `backend/app/api/routes/me.py` | 5 | `MeRead` w/ nested account |
| `backend/app/api/routes/accounts.py` + `services/account.py` | 5 | **new** dev-gated bootstrap |
| `backend/app/api/routes/actors.py` + `services/actors.py` | 5 | accept `account_id`; keep PII gate |
| `backend/app/api/router.py` | 5 | mount `accounts` router |
| `backend/alembic/versions/0006_accounts.py` | 6 | **new** migration |
| `backend/tests/{conftest,test_auth,test_actors,test_funding,test_wiring}.py` | 7 | account-aware |
| `frontend/src/types/research.ts` | 8 | nested `account`; funding `account*` |
| `frontend/src/lib/use-identity.ts` | 8 | `isInternal` from `me.account.roles` |
| `frontend/src/lib/api.ts`, `components/workspace/funding-panel.tsx` | 8 | funder = account |
