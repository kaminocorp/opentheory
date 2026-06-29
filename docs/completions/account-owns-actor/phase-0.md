# `Account` owns `Actor` — Phase 0 Completion (Pre-flight & live data audit)

> Implements **Phase 0** of `docs/executing/account-owns-actor-implementation-plan.md`
> (design: `docs/executing/account-owns-actor.md`). Phase 0 is a **GATE, no code** — a
> read-only audit of the **live** Supabase Postgres to confirm the one real risk of the whole
> change (backfill correctness) before any migration is written.

**Status:** ✅ **GATE GREEN.** Every A0.1 precondition holds. As a bonus de-risking finding,
the live DB currently holds **zero `actors` and zero `funding_allocations`**, so the migration's
backfill (Phase 6) is a **no-op against current data** — the destructive column moves carry
essentially no data-loss risk on this database today.

**Change to the repo:** none to application code. This note + the audit SQL
(`scratchpad/phase0_audit.sql`, transient) are the only artifacts. No schema, no migration, no
backend/frontend code.

---

## What was run, where, and how

- **Target:** the live Supabase Postgres, over the **direct** (non-pooled, `:5432`) connection
  from `backend/.env`'s `MIGRATION_DATABASE_URL` — the same connection Alembic uses for DDL, and
  the right one for ad-hoc introspection (the app's `:6543` transaction pooler is for app
  traffic). Converted `postgresql+asyncpg://…?ssl=require` → libpq `postgresql://…?sslmode=require`
  for `psql`. The password was never printed.
- **Read-only only.** Every statement is a `SELECT` (counts / group-bys). This is consistent with
  repo memory policy ("verify against the live deployment; no destructive ops without an explicit
  greenlight") — an audit is non-destructive. The SQL file is `scratchpad/phase0_audit.sql`.

## ⚠️ Correction to the plan's audit SQL — enum label case

The proposal/plan write the audit predicates as `type='human'` / `type IN ('agent','system')`.
**That SQL would error against this database** with `invalid input value for enum actor_type`.
This repo's convention (see `alembic/versions/0001_baseline.py` and the `0005_funding_source`
note) is that named PG enums use the **StrEnum member *names*** as labels — so `actor_type` has
labels **`HUMAN` / `AGENT` / `SYSTEM`** (uppercase), not the lowercase `.value`s. The audit was
run with the correct uppercase labels. **This is a real bug in the Phase 6 migration sketch too:**
any raw-SQL `WHERE type='human'` in `0006_accounts.py` must be `WHERE type='HUMAN'`. Flagged here
so Phase 6 doesn't inherit it.

## A0.1 — preconditions (all must be 0 / empty) → all pass

| Check | Query (uppercase enum labels) | Result | Required |
|---|---|---|---|
| A0.1.1 | `count(*) FROM actors WHERE type='HUMAN' AND external_id IS NULL` | **0** | 0 |
| A0.1.2 | `external_id … GROUP BY external_id HAVING count(*)>1` | **0 rows** | empty |
| A0.1.3 | `count(*) FROM actors WHERE type IN ('AGENT','SYSTEM') AND external_id IS NOT NULL` | **0** | 0 |
| A0.1.4 | `count(*) FROM funding_allocations f JOIN actors a ON f.actor_id=a.id WHERE a.type<>'HUMAN'` | **0** | 0 |

Interpretation: there are **no** human actors that would fail the unique-`external_id` move; **no**
duplicate `external_id`s; **no** agent/system rows illegally carrying a `sub`; **no** funding row
whose funder isn't a human actor. The backfill's stated invariants are satisfiable.

## A0.2 — baseline counts (for post-migration reconciliation)

| Metric | Value |
|---|---|
| `actors` by type | **(none — 0 rows)** |
| human actors with non-null `external_id` (→ become accounts) | **0** |
| actors holding any role (`roles <> '{}'`, i.e. internal funders) | **0** |
| `funding_allocations` total / with non-null `actor_id` | **0 / 0** |
| `funding_allocations` by (source, status) | **(none — 0 rows)** |

**Reconciliation target for Phase 9:** after `upgrade()` the migration should create **0 accounts**
(`SELECT count(*) FROM accounts` → 0), link **0** actors, and backfill **0** funding rows — because
there is nothing to migrate. (If real users sign in between now and cutover, re-run A0.1/A0.2 at the
cutover window and reconcile against fresh numbers — see *Watch-item* below.)

## A0.3 — cutover window

Given an empty `actors`/`funding_allocations` table, the data-migration portion of cutover is a
**no-op**, so the window is low-stakes: the only live effect of `0006` is the additive DDL
(`accounts` table, `account_id` columns, the partial unique index) plus dropping three now-empty
columns. The plan's single-migration clean path (Decision 3, no expand/contract) remains the right
call at this scale. **Concrete window choice is deferred to the human operator at Phase 9 cutover**
(it's an ops/deploy decision, not a code one); recommend "deploy backend + run `0006` together,
then redeploy Vercel," exactly as the plan's A9.2 states.

---

## Why this matters (the load-bearing point)

The proposal names backfill correctness as **"the whole risk"** — a human actor with a
NULL/duplicate `external_id`, or a non-human funder, would corrupt the one-time data move that
relocates `external_id`/`roles`/funding attribution onto `accounts`. Phase 0 proves those hazards
are absent. The empty-table finding strengthens this: the migration will be exercised structurally
(DDL + index) but moves **no rows**, so the destructive drops cannot lose data on the current DB.

## Watch-items carried forward

- **The DB can gain rows before cutover.** Auth is live and enforcing; the empty result means no
  one has signed in (or the DB was reset), but a first sign-in would mint a human actor with an
  `external_id`. **Re-run `phase0_audit.sql` immediately before the Phase 9 cutover** and reconcile
  against whatever A0.2 returns then — don't trust today's zeros at deploy time.
- **Enum-label case** (above) must be carried into the Phase 6 raw-SQL backfills.
- **Migration must still round-trip** on a throwaway DB (Phase 9 / A9.1) even though current data is
  empty — the DDL + downgrade path must be proven regardless of row count.

## Gate result

**A0.1 all empty/0 → Phase 0 gate is GREEN.** Cleared to proceed to Phase 1 (backend domain models).
