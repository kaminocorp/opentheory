# `Account` owns `Actor` — Phase 6 Completion (Alembic migration `0006_accounts`)

> Implements **Phase 6** of `docs/executing/account-owns-actor-implementation-plan.md`. Hand-authors
> the destructive migration that creates `accounts`, relocates `external_id` / `roles` / funding
> attribution onto it, and drops the three now-moved columns. This is the schema half of the
> ship-together release; the round-trip proof is **deferred to Phase 9** (needs a throwaway DB).

**Status:** ✅ **GATE GREEN** (the Phase 6 gate is *lint + DDL/metadata cross-check*; round-trip is
explicitly a Phase 9 step). `uv run ruff check .` passes; `alembic history` is linear with
`0006_accounts` as the single head off `0005_funding_source`; the ORM metadata and the migration DDL
agree (verified field-by-field, below); DB-free suite **9 passed / 47 skipped** (== baseline).

**Files:** `backend/alembic/versions/0006_accounts.py` (**new**), plus a small refinement to
`backend/app/models/actor.py` (the partial unique index, see *Deviation* below).

---

## What landed, where, and why

### A6.1 — `upgrade()` (additive DDL → backfill → drop, in that exact order)

1. **`create_table("accounts", …)`** — `id` (uuid pk), `external_id` (String(255), **unique**,
   nullable), `display_name` (not null), `email` (nullable), `roles` (`ARRAY(String)`, not null,
   `server_default '{}'`), `account_metadata` (JSON, not null), `created_at`/`updated_at`. The pk
   and timestamps carry **no** server default — the ORM supplies them (`IdMixin.uuid4`,
   `TimestampMixin.datetime.now`), matching every baseline table. `roles` keeps the `'{}'` server
   default so it mirrors the model and `alembic check` stays clean. The unique constraint is
   **unnamed** (→ Postgres `accounts_external_id_key`), the same idiom the baseline used for
   `actors.external_id`.
2. **`add_column("actors", account_id …)`** + FK `fk_actors_account_id_accounts`
   (`ondelete="SET NULL"`). No plain index — the partial unique index (step 6) is the only index on
   `account_id`, matching the model.
3. **Backfill accounts from human actors**, then **link** them: `INSERT … SELECT gen_random_uuid(),
   a.external_id, a.display_name, a.actor_metadata->>'email', a.roles, '{}'::json, a.created_at,
   a.updated_at FROM actors a WHERE a.type = 'HUMAN' AND a.external_id IS NOT NULL`, then
   `UPDATE actors SET account_id = acc.id … WHERE acc.external_id = a.external_id AND a.type='HUMAN'`.
4. **`add_column("funding_allocations", account_id …)`** + FK + index
   `ix_funding_allocations_account_id` (the old `actor_id` was indexed; the funder is now the
   principal).
5. **Backfill funding** → the funder actor's account: `UPDATE funding_allocations f SET
   account_id = a.account_id FROM actors a WHERE f.actor_id = a.id`.
6. **`create_index("uq_actors_one_human_per_account", …, unique=True, postgresql_where="type =
   'HUMAN'")`** — one primary `human` Actor per Account (Decision #7), created *after* the backfill
   (so the one-human-per-account invariant already holds).
7–9. **Drop** `funding_allocations.actor_id`, `actors.external_id`, `actors.roles`. Postgres
   cascades each column's dependents (the funding `actor_id` index + FK, the `actors_external_id_key`
   unique constraint).

### A6.2 — `downgrade()` (reverse: re-add → re-derive → tear down)

Re-adds `actors.external_id` (+ `actors_external_id_key`), `actors.roles` (`'{}'` default),
`funding_allocations.actor_id` (+ FK + index); **re-derives** `external_id`/`roles` from the owning
account and `funding.actor_id` from the account's `human` actor (**human-only**, restoring the
original invariant that only `human` actors carry `external_id`/`roles`; the still-present partial
unique index guarantees no duplicate `external_id`); then drops the partial index, both `account_id`
columns (+ their FK/index), and the `accounts` table.

### A6.3 — enum-label case + raw-SQL casts

Every raw-SQL predicate uses the **uppercase** enum label `'HUMAN'` — the Phase 0 trap: this DB's
named enums use the StrEnum *member names*, so lowercase `type='human'` errors with
`invalid input value for enum actor_type`. Casts: `'{}'::json` for `account_metadata`,
`gen_random_uuid()` for the server-side pk (core in Postgres 13+; Supabase is 15, so no extension).

## Deviation (flagged): the partial unique index is now declared on the model

The plan put the index only in the migration, and the Phase 1 model comment said it was "not
declarable on the column." That is **wrong in a way that would have silently broken Phase 7**: the
test harness builds its schema with `Base.metadata.create_all` (`conftest.py`), **not** Alembic — so
an index that lives only in the migration would be **absent in tests**, and A7.5 ("reject a second
`human` per account") would pass-by-vacuity (no index → no rejection). Fixed by declaring it in
`Actor.__table_args__` as a partial `Index(..., unique=True, postgresql_where=text("type =
'HUMAN'"))`, which `create_all` emits identically to the migration. Net effect: `create_all` (tests)
and Alembic (prod) now build the **same** constraint — the drift this repo explicitly guards against
(cf. the `0005` "so `alembic check` stays clean" note). The stale model comment was corrected to
point at `__table_args__`.

## Gate verification (reproduced, not asserted)

```
$ uv run ruff check .                         → All checks passed!
$ uv run alembic history | head -1
  0005_funding_source -> 0006_accounts (head), accounts: the auth principal that owns actors …
$ uv run python  (metadata ↔ migration cross-check)
  accounts cols: account_metadata, created_at, display_name, email, external_id, id, roles, updated_at
  accounts unique on external_id: True
  actors cols: account_id, actor_metadata, created_at, display_name, id, type  (no external_id/roles)
  index uq_actors_one_human_per_account: unique=True cols=['account_id'] where="type = 'HUMAN'"
  funding has account_id: True | has actor_id: False
  migration revision: 0006_accounts | down_revision: 0005_funding_source
$ uv run pytest -q                            → 9 passed, 47 skipped   (== baseline)
```

## Deferred to Phase 9 (not skipped — sequenced)

- **The migration round-trip** (`alembic upgrade head` → `downgrade -1`, values intact, counts
  reconciled to the Phase 0 baseline of 0/0/0) runs on a **throwaway** Postgres under an explicit
  greenlight (repo policy: never the live DB). This is the Phase 6 gate's outstanding half, owned by
  A9.1 — the DDL is *structurally* verified here (metadata cross-check), but only a real engine
  proves the backfill SQL, the cascade-on-drop, and the downgrade re-derivation. **Empty-DB caveat:
  today the backfills move 0 rows, so the round-trip must be run regardless of row count to exercise
  the SQL paths at all.**
- **Live cutover** (apply `0006` + deploy the new backend together) is A9.2.

## Gate result

**Ruff clean, linear single head, metadata ↔ DDL agree, DB-free at baseline → Phase 6 gate is
GREEN** (lint + cross-check; round-trip is a Phase 9 step by design). Cleared to proceed to Phase 7
(backend tests), which the model-side index now makes enforceable under `create_all`.
