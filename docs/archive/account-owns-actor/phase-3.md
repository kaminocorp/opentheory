# `Account` owns `Actor` — Phase 3 Completion (Auth resolution + roles)

> Implements **Phase 3** of `docs/executing/account-owns-actor-implementation-plan.md`. This is
> **the one behavioral change** in the whole effort: JIT-provisioning and role resolution move from
> the flat `Actor` to the `Account` principal. `get_acting_actor`'s contract (returns a resolved
> `Actor`) is unchanged, so no downstream service signature changes.

**Status:** ✅ **GATE GREEN.** `uv run ruff check .` passes; all 56 tests collect; the DB-free
suite is **9 passed / 47 skipped** (identical to the pre-change baseline); the eager-load SQL was
verified offline (see below).

> ⚠️ **Intermediate-state warning.** The auth path is now account-correct, but `services/funding.py`
> (Phase 4) still builds `FundingAllocation(actor_id=…)` and `FundingRead(actor=…)` — both
> runtime-broken until Phase 4. The DB-backed `test_auth` / `test_funding` (in the 47 skipped) still
> assert the **old** response shape and will fail against a real DB until Phase 7 updates them. This
> is the planned ship-together release boundary, not a regression.

---

## What landed, where, and why

### A3.1 — `backend/app/core/roles.py` (account-aware)

- Added **`account_is_internal(account: Account | None) -> bool`** — the principal-level predicate;
  `None` (an account-less actor) is never internal.
- Redefined **`actor_is_internal(actor)`** to delegate: `account_is_internal(actor.account)`. It
  now requires `actor.account` to be loaded — guaranteed by `_resolve_or_provision` (the single
  resolution path), which eager-loads it.
- `INTERNAL_ROLE = "internal"` kept. Added `Account` to the `TYPE_CHECKING` block (no runtime
  import — avoids a cycle, since `core` is imported by both `api` and `services`).

### A3.2 — `backend/app/api/deps.py::_resolve_or_provision` (rewritten)

The resolution is now **keyed on the `Account`**:

- **Resolve:** `select(Actor).join(Account, Actor.account_id == Account.id)
  .options(contains_eager(Actor.account)).where(Account.external_id == sub, Actor.type == HUMAN)`.
  Returns the account's primary human Actor with `account` eager-loaded.
- **Provision (first login):** create `Account` (with `roles` from the `internal_actor_emails`
  allowlist) **and** its one primary `human` `Actor` (`account=account`), `db.add` both, **single
  `commit`** — so neither row can orphan.
- **Race recovery:** on `IntegrityError` (lost the unique-`accounts.external_id` race), rollback and
  re-run the eager-loading `stmt` → the winner's Account → primary Actor.
- **Imports added:** `contains_eager` (sqlalchemy.orm) and `Account` (app.models.account); both
  used. `INTERNAL_ROLE` / `actor_is_internal` / `select` / `IntegrityError` / `ActorType` all still
  used (ruff confirms no orphans).

Two implementation decisions worth recording:

1. **Dropped the `db.refresh(actor)`** the proposal sketch ended with. The session uses
   `expire_on_commit=False` (`db/session.py`), and `id`/`created_at`/`updated_at` are all
   **Python-side** defaults (`uuid4` / `datetime.now(UTC)`), so the in-memory object is already
   complete after commit. Refreshing would re-`SELECT` and risk **expiring the eager-loaded
   `account` into an async lazy-load** (`MissingGreenlet`). Returning the in-memory actor (with
   `account` attached) is both correct and safer. This is why `expire_on_commit=False` is
   load-bearing here.
2. **Kept the proposal's explicit-condition join** (`join(Account, Actor.account_id == Account.id)`)
   rather than the relationship-path `join(Actor.account)`. Verified via the compiled SQL that
   `contains_eager(Actor.account)` still pulls `accounts.*` into the SELECT (so the relationship is
   populated, not lazy).

### A3.3 — `get_acting_actor` / `_resolve_dev_actor` / dev-header branch confirmed unchanged

- `get_acting_actor` — signature, `401` branches, dev-header branch, and `ActingActor` annotation
  untouched; only its docstring was corrected (it said "maps to one Actor by `external_id == sub`",
  now "maps to its owning Account by `Account.external_id == sub` and returns the primary human
  Actor"). No behavior change.
- `require_internal` — unchanged signature; reads `actor.account` (now eager-loaded) via the
  redefined `actor_is_internal`. An account-less dev actor → not internal → `403`, the intended
  behavior.
- `_resolve_dev_actor` — unaffected (resolves by UUID via `db.get`; never used `external_id`). Dev
  actors stay `account_id IS NULL` (Decision #8).

---

## Gate verification (reproduced, not asserted)

```
$ uv run ruff check .
All checks passed!

# Offline eager-load proof (no DB needed): the compiled resolve statement selects accounts.*
SELECT accounts.external_id, accounts.display_name, accounts.email, accounts.roles, … ,
       actors.type, actors.display_name, actors.actor_metadata, actors.account_id, actors.id, …
FROM actors JOIN accounts ON actors.account_id = accounts.id
WHERE accounts.external_id = 'sub-x' AND actors.type = 'HUMAN'
→ OK: accounts columns in SELECT ⇒ contains_eager populates actor.account (no lazy-load)

$ uv run pytest --collect-only -q   → 56 tests collected
$ uv run pytest -q                  → 9 passed, 47 skipped   (== baseline)
```

- The `WHERE actors.type = 'HUMAN'` in the emitted SQL also confirms the enum-label-case fix from
  Phase 0 is respected end-to-end (the ORM emits the uppercase member name, matching the DB enum).

## Deferred to later phases (cannot be done / verified here)

- **Runtime behavior of provisioning** (one Account + one human Actor minted; second request reuses
  both; race → one Account, no orphan; `internal` granted on the Account) needs a **real DB** —
  Phase 7 tests + Phase 9 live verification.
- `services/funding.py` reading `actor.account` for the native gate and writing `account_id`
  (Phase 4); `routes/me.py` returning `MeRead` (Phase 5).

## Gate result

**Ruff clean, tests collect, DB-free suite at baseline, eager-load SQL verified → Phase 3 gate is
GREEN.** The requested Phases 0–3 are complete. Next: Phase 4 (funding service rewiring).
