# 0.58.1 — Lock public PostgREST

**Goal.** Record the live public-schema lock in the repo
before anything else on slice G (#56). Live PostgREST already
returns `401` / `42501` on `accounts` / `checkpoints` /
`actors` / `projects`; `anon` / `authenticated` have zero
table grants; every public table has RLS enabled **and**
forced. The backend connects as `postgres` (owner /
`bypassrls`), so app traffic is unaffected. This revision is
idempotent so a later `alembic upgrade head` matches that
state. Sits on shipped `0.58.0` (`c1a4ca5`, #55).

**Shape.** One Alembic revision, no policies, no application
behavior change.

## What shipped

- `0023_lock_public_api_rls` revises `0022_agent_actor_identity`.
  One transaction. Shared SQL in `app/db/rls_lock.py`.
- Upgrade: `LOCK_PUBLIC_TABLES_SQL` loops `pg_tables` and
  `ENABLE` + `FORCE` RLS on every `public` table present at
  apply time (not a hard-coded list). Then
  `REVOKE_POSTGREST_GRANTS_SQL` revokes all table and
  sequence privileges — and default privileges — from `anon`
  and `authenticated` when those roles exist.
- No `CREATE POLICY`. Empty forced RLS denies non-bypass
  roles.
- Downgrade: `NO FORCE` then `DISABLE` only. Does **not**
  re-GRANT. Re-GRANT is a deliberate ops step.
- Round-trip test: after upgrade, every public base table
  has `relrowsecurity` and `relforcerowsecurity`; those roles
  have no table privileges; a second upgrade is a no-op;
  after downgrade, RLS flags are off and grants stay absent.
- Alembic-head CI hook: fails if any public table (or any
  SQLAlchemy public table in `Base.metadata`) lacks
  ENABLE+FORCE after `alembic upgrade head`. Later revisions
  that create a public table must call
  `LOCK_PUBLIC_TABLES_SQL` in the same revision.
- Docs: changelog, this note, `docs/operations/deploy.md`,
  CLAUDE.md rule, techstack sentence. Frontend uses Supabase
  Auth only, never PostgREST table access.

## What did not change

- No Fly deploy. No live Supabase write from the agent.
- No policies that open any table.
- `AGENT_LOOP_ENABLED` stays dark. Gateway / MCP child stay
  dark. Five tabs.
- Slice G (`agent_definitions`) is #56, rebased onto this
  lock as `0024`. Neither PR merges until the 0022 Fly
  deploy is verified.

## Judgment calls

- **`pg_tables` loop, not today's 24 names.** A hard-coded
  list would miss a table created earlier in the same
  upgrade chain.
- **REVOKE is role-existence-guarded.** Live Supabase has
  `anon` / `authenticated`; CI Postgres may not. Creating
  those roles is test-only, not in the migration.
- **Downgrade does not re-GRANT.** Restoring PostgREST table
  access is an ops decision, not an automatic rollback.
- **CI hook is Alembic-head, not `create_all`.** Pytest
  fixtures still `DROP SCHEMA` + `create_all` and do not set
  RLS; the backend test user is a superuser. The lock is
  enforced on the deploy path (`alembic upgrade head`).

## Tests

- `ruff` clean.
- With `TEST_DATABASE_URL`: **1205 passed, 4 skipped**. +6 vs
  `0.58.0` (1199): 0023 linkage / only-head / `pg_tables` loop /
  transactional, Alembic-head RLS+FORCE hook, downgrade
  round-trip does not re-GRANT.
- Frontend `typecheck` / `lint` / `test` / `build` clean.
  **75 passed** (unchanged).
