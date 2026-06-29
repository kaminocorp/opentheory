# Identity — `Account` owns `Actor`

> Introduce an **`Account`** (the authentication *principal* — one per `auth.users` login) that
> **owns** one or more **`Actor`s** (the provenance/action identities the ledger attributes to). The
> IdP subject (`sub`) and principal-level concerns (email, **roles**, **funding/money**, later billing
> & prefs) move up to `Account`; the `human` Actor becomes the account's primary actor; future
> `agent` Actors hang off the **same** account as their owner. `Actor` stays the action identity the
> research ledger attributes to. The `ActingActor` *contract* (a resolved `Actor`) is unchanged.

## North star (the bottom line this enables)

> A person can **sign up / register** (future), **log in as a user**, and then **spawn new lines of
> enquiry** (threads/branches) **if they fund them**.

That sentence is the whole point. It implies: the user-facing thing you register/log in as is the
**`Account`** (the principal with a login and money); funding is an **Account** act; and the research
moves the funding unlocks are performed by the account's **`Actor`**. This document makes the schema
match that mental model.

## When to build this (trigger condition — read first)

Not needed today; do **not** build speculatively. As of `0.6.10` the `human` Actor *is* the platform
user and that is correct for a human-only ledger. Adopt this when **either** forcing function lands
(both `0.7.0`-era):

1. **Agent ownership.** An `agent` Actor is not a login; it acts *on behalf of* a human/org with
   scoped credentials, not a session. "One person operates themselves **and** owns N agents" cannot
   be expressed on today's flat `actors` table, where `external_id == sub` forces exactly **one**
   `auth.users` row ⇄ **one** Actor.
2. **Real money + account settings.** Billing / payment methods, prefs, and API keys are mutable,
   sensitive, principal-level data that must not live on a row the immutable ledger attributes to.

Until then, keep account-ish fields in `actor_metadata` and leave the schema alone. This document is
the ready-to-execute plan for the moment the trigger fires.

## The load-bearing fact: `Actor` stays the provenance identity; `Account` is the new principal

The architecture's rule is "agents use the **same** primitives as humans" (CLAUDE.md, `vision.md`). A
`User` table that *replaces* `Actor` for humans would fork that model — forbidden. So we add a
principal that *owns* actors, never a `User`.

| | `auth.users` (Supabase, `auth` schema) | **`Account`** (`public.accounts`, **new**) | `Actor` (`public.actors`, existing) |
|---|---|---|---|
| Concern | **Authentication** — credentials, sessions, MFA | **Principal** — the owning human/org; identity, **roles**, **money**, billing/prefs (later) | **Provenance** — who performed a *research* action |
| Holds `sub` | is the `sub` (`auth.users.id`) | **`external_id` = `sub`** | `account_id` FK (no longer holds `sub`) |
| Mutability | owned by GoTrue | mutable principal state (not the ledger) | identity referenced by **immutable** checkpoints |
| Cardinality | 1 login | **1** per human login | **1..N** per account (1 `human` + N `agent`); `system` has no account |
| Ledger FKs → it | no | **funding only** (money is principal-level) | checkpoint / contribution / validation |

Chain: `auth.users.id (sub)` → `Account.external_id` → `Account` **owns** → `Actor`(s) → the ledger.

## Decisions (locked — resolved from review)

1. **Add `Account`; never a `User`; never replace `Actor`.** `Actor` stays the universal action
   identity (`human | agent | system`); `Account` is additive.
2. **`get_acting_actor` still returns an `Actor`** — only `_resolve_or_provision` changes (resolve the
   Account, return its primary human Actor), with the Actor's `account` **eager-loaded** so role/money
   checks need no extra query. Every service signature is unchanged.
3. **(Q1) Fully move `external_id` to `Account`; drop it from `actors`.** Cleanest model — a single
   source of truth, no denormalized mirror to keep in sync. The unique constraint moves to
   `accounts.external_id`. (Downgrade re-derives the column; see *Migration*.)
4. **(Q2) Roles are principal-level → move `roles` to `Account`.** The most conceptually sound split:
   `internal` (and future billing/admin) describe the *principal*, not a specific action identity, so
   they live on `accounts.roles`. Per-actor **capability scopes** (e.g. what an individual agent may
   do) are a **separate, future** per-actor concept — **not built now** (no speculative column).
   `actors.roles` is dropped (it only ever held `internal`).
5. **(Q3) Funding/money attribution → `Account`.** `FundingAllocation.actor_id` becomes
   `account_id` (FK `accounts.id`) — money comes from the *principal* (the thing with a payment
   method). This is the **one** ledger FK that moves. The `fund` **`Contribution`** stays
   actor-attributed (it is the activity-log entry "actor X performed a fund action," uniform with
   every other action; `action="fund"` keeps it distinguishable so credit systems never conflate
   funding with intellectual contribution). So: *allocation = the account's money; contribution =
   the actor's act.*
6. **Provenance (research) stays attributed to `Actor`.** `Checkpoint.author_id`,
   `Contribution.actor_id`, `Validation.actor_id` keep pointing at `actors.id`. An agent-authored
   checkpoint is attributed to the **agent Actor**; walk `actor → account` for the owner.
7. **One `human` Actor per Account, enforced in the DB** — partial unique index
   `UNIQUE (account_id) WHERE type = 'human'`. `agent` actors are unconstrained; `system` actors have
   `account_id IS NULL`.
8. **(Q4) No seeding — at all.** No demo/seed scripts, no auto-minted accounts. Dev-bootstrap actors
   (`X-Dev-Actor-Id`) stay **account-less** (`account_id IS NULL`). Tests that exercise account-level
   roles/funding construct the `Account` they need **explicitly** (fixture/`AccountCreate`) — that is
   test setup, not seeding.
9. **(Q5) `system` actor has no account** (`account_id IS NULL`); there is **no** singleton "platform"
   account. Keep it simple — the platform is no one's principal.
10. **(Q6) Expose `Account` in the API now.** Add `AccountRead`/`AccountSummary` and nest `account`
    in the `/me` response, since account-level datapoints (billing/prefs) are coming soon. `roles`
    move with it (the frontend's `isInternal` now reads `me.account.roles`).

## Schema

### New table: `accounts`

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID` pk | via `IdMixin` |
| `external_id` | `String(255)`, `unique`, **nullable** | the IdP `sub`; nullable so future org/service accounts without a single `sub` are representable. The human-provision path always sets it. |
| `display_name` | `String(200)`, not null | account label |
| `email` | `String(255)`, nullable | promoted out of `actor_metadata`; the principal's contact email |
| `roles` | `ARRAY(String)`, not null, default `{}` | **moved from `actors`** (Decision 4). `internal` lives here. **Not** append-only guarded (mutable identity, like the old `actors.roles`). |
| `account_metadata` | `JSON`, not null, default `{}` | `<entity>_metadata` naming rule (CLAUDE.md) |
| `created_at` / `updated_at` | via `TimestampMixin` | |

`Account` is a mutable identity row — like `Branch.status` it is **not** append-only guarded; do
**not** register it in `models/append_only.py`.

### Changed table: `actors`

| Change | Detail |
|---|---|
| **+ `account_id`** | `UUID` FK → `accounts.id`, `ondelete="SET NULL"`, **nullable** (`system` / dev / not-yet-owned actors are NULL) |
| **− `external_id`** | dropped (Decision 3); unique constraint moves to `accounts.external_id` |
| **− `roles`** | dropped (Decision 4); moves to `accounts.roles` |
| relationship | `account = relationship("Account", back_populates="actors")` |

### Changed table: `funding_allocations`

| Change | Detail |
|---|---|
| **`actor_id` → `account_id`** | FK `accounts.id`, `ondelete="SET NULL"`, `index=True` — the funder is the **principal** (Decision 5) |
| relationship | `actor` → `account = relationship("Account", back_populates="funding_allocations")` |
| append-only | still guarded — unchanged; only the FK target changes |

### `models/__init__.py`

Add `Account` to the imports **and** `__all__` — Alembic's `env.py` does `from app.models import *`,
so a model missing from `__all__` is silently absent from autogenerate (CLAUDE.md).

### Model sketch (`models/account.py`)

```python
from typing import Any
from sqlalchemy import ARRAY, JSON, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, IdMixin, TimestampMixin

class Account(IdMixin, TimestampMixin, Base):
    __tablename__ = "accounts"

    external_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    roles: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default=text("'{}'")
    )
    account_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    actors = relationship("Actor", back_populates="account")
    funding_allocations = relationship("FundingAllocation", back_populates="account")
```

On `Actor` (`models/actor.py`): drop `external_id` and `roles`; add `account_id` + `account`
relationship; drop the `funding_allocations` relationship (moves to `Account`).

## Migration (`0006_accounts.py`)

Numbered/styled like `0005_funding_source.py`; `down_revision = "0005_funding_source"`. The data
migration runs **between** schema add and drop. Use raw `op.get_bind().execute(sa.text(...))` for the
backfills (as the enum migrations do), not the ORM.

```
upgrade():
  1. create_table("accounts", ...)              # id, external_id (unique), display_name, email,
                                                 # roles (ARRAY, server_default '{}'), *_metadata, ts
  2. add_column("actors", account_id UUID NULL FK accounts.id ON DELETE SET NULL)
  3. DATA — accounts from human actors:
       INSERT INTO accounts (id, external_id, display_name, email, roles, account_metadata, created_at, updated_at)
         SELECT gen_random_uuid(), a.external_id, a.display_name,
                a.actor_metadata->>'email', a.roles, '{}'::json, a.created_at, a.updated_at
         FROM actors a WHERE a.type='human' AND a.external_id IS NOT NULL;
       UPDATE actors a SET account_id = acc.id
         FROM accounts acc WHERE acc.external_id = a.external_id;     -- links the human actors
  4. add_column("funding_allocations", account_id UUID NULL FK accounts.id ON DELETE SET NULL, index)
  5. DATA — funding to accounts:
       UPDATE funding_allocations f SET account_id = a.account_id
         FROM actors a WHERE f.actor_id = a.id;                       -- funder actor → its account
  6. create partial unique index uq_actors_one_human_per_account
       ON actors (account_id) WHERE type='human'
  7. drop_column("funding_allocations", "actor_id")
  8. drop_column("actors", "external_id")        # also drops its unique constraint
  9. drop_column("actors", "roles")

downgrade(): re-add the dropped columns (actors.external_id unique, actors.roles, funding.actor_id),
  backfill each from accounts (external_id, roles) and funding.account_id→account.actors(human),
  drop the partial index, drop the two account_id columns, drop table accounts.
```

Pre-migration data audit (run against the live DB **first**, see *Verification*) gates this: every
`human` actor must have a unique non-null `external_id`; `agent`/`system` actors have
`external_id IS NULL` (asserted by the email-password doc) and get **no** account.

## `_resolve_or_provision` and `external_id` — the exact change

The only behavioral change. Today (`api/deps.py:30`) it keys on `Actor.external_id` and stamps roles
on the Actor. After: key on `Account.external_id`; on first login create **Account + primary human
Actor** in one transaction; eager-load `account` so role checks need no extra query; stamp roles on
the **Account**.

```python
# AFTER (Account-owns-Actor)
from sqlalchemy.orm import contains_eager

async def _resolve_or_provision(db, identity) -> Actor:
    # Resolve by the auth PRINCIPAL (Account); return its primary human Actor with account loaded.
    stmt = (
        select(Actor)
        .join(Account, Actor.account_id == Account.id)
        .options(contains_eager(Actor.account))                      # role checks read actor.account
        .where(Account.external_id == identity.subject, Actor.type == ActorType.HUMAN)
    )
    actor = (await db.execute(stmt)).scalar_one_or_none()
    if actor is not None:
        return actor

    email = identity.email
    is_internal = bool(email) and email.lower() in settings.internal_actor_emails
    account = Account(
        external_id=identity.subject,
        display_name=identity.display_name or identity.subject,
        email=email,
        roles=[INTERNAL_ROLE] if is_internal else [],                # roles live on the Account now
    )
    actor = Actor(
        type=ActorType.HUMAN,
        display_name=identity.display_name or identity.subject,
        account=account,                                             # ORM sets account_id on flush
        actor_metadata={"email": email} if email else {},
    )
    db.add(account)
    db.add(actor)
    try:
        await db.commit()
    except IntegrityError:                                            # lost the unique(external_id) race
        await db.rollback()
        return (await db.execute(stmt)).scalar_one()                 # winner committed both rows
    await db.refresh(actor)
    return actor
```

Key points:
- **Idempotency unchanged in spirit:** the unique guard moves from `actors.external_id` to
  `accounts.external_id`; a lost first-login race re-reads the winner's Account → primary Actor.
  Account+Actor share **one** `commit`, so no partial row can orphan.
- **`account` is eager-loaded** (`contains_eager` on the resolve path; set directly on the provision
  path), so `actor.account.roles` is available synchronously to `require_internal` and the funding
  service — no async lazy-load surprise.
- **`get_acting_actor` is otherwise untouched** — same return type (`Actor`), same `401`/dev-header
  branches, same `ActingActor` annotation.
- **`_resolve_dev_actor` is unaffected** — resolves an existing actor by UUID; never used
  `external_id`. Dev actors have `account_id IS NULL` (Decision 8).

## Roles: `core/roles.py` becomes account-aware

```python
INTERNAL_ROLE = "internal"

def account_is_internal(account: "Account | None") -> bool:
    return account is not None and INTERNAL_ROLE in (account.roles or [])

def actor_is_internal(actor: "Actor") -> bool:        # convenience: walk to the principal
    return account_is_internal(actor.account)
```

`require_internal` (deps) keeps its signature (receives the `ActingActor`) and reads
`actor.account` (eager-loaded above). The funding service's native gate uses the same predicate.

## Funding: actor → account (the one ledger FK that moves)

`services/funding.py::create_funding`:
- native gate: `if payload.source == NATIVE and not actor_is_internal(actor)` — now resolves through
  `actor.account.roles`. A dev/account-less actor has no account → no `internal` role → `403`, which
  is the intended behavior.
- `allocation = FundingAllocation(..., account_id=actor.account_id, ...)` (was `actor_id=actor.id`).
- the `fund` **Contribution stays `actor=actor`** (Decision 5) — `record_contribution(...,
  action=ACTION_FUND, actor=actor, funding_allocation_id=...)` is unchanged.
- `_enrich` / `_to_read` resolve the funder **Account** (not Actor); `FundingRead.actor_id`/`actor`
  become `account_id`/`account: AccountSummary`. `project_budget` reads `FundingAllocation` only, so
  budget totals are now principal-attributed for free.

`schemas/funding.py`: `FundingRead.actor_id` → `account_id`, `actor` → `account`.

## API surface (expose `Account` now — Decision 10)

- **`GET /me`** returns the `Actor` plus a nested `account` (new `schemas/account.py` →
  `AccountRead`/`AccountSummary`): `{ ...actor, account: { id, display_name, email, roles } }`. Either
  extend `ActorRead` with an `account` field or add a `MeRead` wrapper.
- **`ActorRead`** loses `external_id` and `roles` (both moved). **`ActorCreate`** loses `external_id`
  and `roles`; those dev/test seed fields move to a new **`AccountCreate`** (the dev/test path creates
  an Account, then an Actor linked to it).
- **Frontend:** `lib/use-identity.ts` — `isInternal` and any role/`external_id` reads now come from
  `me.account.*`. Grep the frontend for `external_id`/`roles` off the actor before shipping.
- No new write endpoints required here; agent-creation / API-key endpoints are separate `0.7.0` work
  that *consumes* this schema.

## What does **not** change (audited)

- **Research provenance FKs** → still `actors.id`: `Checkpoint.author_id` (`checkpoint.py:35`),
  `Contribution.actor_id` (`contribution.py:21`), `Validation.actor_id` (`validation.py:22`).
- **The checkpoint chokepoint** (`services/checkpoints.py`) and every composing service — untouched;
  they receive a resolved `Actor` as before.
- **`core/auth.py`** — still maps a JWT to `VerifiedIdentity(subject, email, display_name)`; the
  `subject` now lands on the Account, but the verifier doesn't know or care.
- **`auth_dev_header_enabled` path, `/auth/callback`, `lib/api.ts` token attach** — untouched.
- **`ActorSummary`** (checkpoint authors etc.) — unaffected (it carries id/display_name/type, not
  roles/external_id).

> Honesty note: Decisions 4–5 deliberately widen the blast radius beyond the original "tiny" sketch
> (now: `core/roles.py`, `actor_is_internal`, funding model/service/schema, `/me`, the frontend
> `isInternal`). That cost buys the conceptually correct placement of money and authorization on the
> principal — which the review explicitly chose ("whatever is most conceptually sound").

## Verification

- **Pre-migration data audit (live DB, first):**
  - `SELECT count(*) FROM actors WHERE type='human' AND external_id IS NULL;` → **0**.
  - `SELECT external_id FROM actors WHERE external_id IS NOT NULL GROUP BY 1 HAVING count(*)>1;` →
    **empty** (required by the unique move).
  - `SELECT count(*) FROM actors WHERE type IN ('agent','system') AND external_id IS NOT NULL;` → **0**.
  - `SELECT count(*) FROM funding_allocations f JOIN actors a ON f.actor_id=a.id WHERE a.type<>'human';`
    → **0** (only human/internal actors fund today; confirm before the funding backfill).
- **Migration round-trips** on a **throwaway** copy (per repo policy — never the live DB without an
  explicit greenlight): `alembic upgrade head` then `downgrade -1` restores the dropped columns with
  values intact.
- **Backend tests** (DB-backed, need `TEST_DATABASE_URL`):
  - JIT-provision: first authed request mints **one** Account **and** one human Actor; second reuses
    both; concurrent first-login race → exactly one Account, no orphan Actor.
  - Partial unique index rejects a second `human` actor per account.
  - `internal` granted on the **Account** at provision (allowlist); native funding still `403`s a
    non-internal / account-less actor and succeeds for an internal one; the allocation's `account_id`
    is the funder's account; the `fund` Contribution is still actor-attributed.
  - `project_budget` unchanged in output (reads allocations).
  - DB-free suite (`9 passed, 47 skipped`) green; update any model-count / `WRITE_PATHS` assertions
    and the actor PII-gate tests for the moved fields.
- **Frontend:** `typecheck` / `lint` / `build` green; `/me` drives the identity menu and `isInternal`
  reads `me.account.roles`.

## Risks & watch-items

- **Backfill correctness is the whole risk.** A human actor with NULL/duplicate `external_id`, or a
  funding row whose actor isn't human, breaks a backfill. The audit gates this; don't run until clean.
- **Dropping `actors.external_id`/`roles` and `funding.actor_id` is destructive.** Downgrade
  re-derives them from `accounts`; only data for actors/funding that got an `account_id` survives a
  round-trip. Acceptable given the audit guarantees full coverage pre-drop.
- **Eager-loading discipline.** `require_internal` / funding read `actor.account` synchronously; if a
  future code path resolves an `Actor` *without* loading `account`, the role check silently sees
  `None`. Centralize resolution through `_resolve_or_provision` (already the single provision path).
- **Provision writes two rows.** Slightly larger first-login transaction; still one `commit`.
- **Scope creep into 0.7.0.** This is *only* identity layering + the money/role relocation it forces.
  No agent/API-key/billing columns now — they land with their features.

## Changelog / versioning

A structural identity change with a real migration → land it as the **opening slice of `0.7.0`**
(Agent-Ready Execution Surface); agent ownership is its forcing function. If pulled ahead of agent
work it could ship as a standalone `0.6.x` schema release. On completion, add a `docs/changelog.md`
entry: `Account` added and owning `Actor`s; `external_id`, `roles`, and funding attribution moved to
`accounts`; research provenance FKs and the `ActingActor` contract unchanged; migration `0006`; the
pre-migration data audit + round-trip as the gate.
