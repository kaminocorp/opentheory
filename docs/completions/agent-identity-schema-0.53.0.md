# 0.53.0 — Agent identity schema

**Goal.** Land slice A (schema only) of the approved agent-actor
identity design so later slices can roster agents, mint session
tokens, and attribute harness writes without another `actors` /
`checkpoints` / `compute_debits` reshape. Stay dark: no API, MCP,
UI, or auth behaviour change. Do not light `AGENT_LOOP_ENABLED`.
Do not enable the gateway or MCP child on Fly. Do not apply to
the live Supabase project in this PR — the owner reviews before
prod. Sits on `0.52.0` (PR #48).

**Shape.** Alembic `0022_agent_actor_identity` + SQLAlchemy
models in lockstep with `create_all`. Schema-on, behavior-off.

Owner overrides vs the design doc (2026-10-06): **no**
`actors.agent_definition_id` in v1 (deferred with
`agent_definitions`); keep `Research crew` display name; one
shared project daily cap; `ProjectAgentRole = RESEARCHER` only,
no validator role ever; OWNER-only token mint (later slice);
roster readable by members only (later slice); per-agent caps
stored now, enforced later; revoked agents remain visible.

## What shipped

- Enums `project_agent_role` (`RESEARCHER`) and
  `project_agent_status` (`ACTIVE` / `SUSPENDED` / `REVOKED`).
- `project_agent_members` — mutable roster, **not** append-only.
- `agent_session_tokens` — hash at rest; no mint/verify code.
- Nullable `checkpoints.sponsored_by_actor_id` and
  `compute_debits.actor_id` (FK `actors`, `ON DELETE SET NULL`).
- Index surgery: drop `uq_actors_one_agent_per_project`; add
  `uq_actors_one_research_crew_per_project`.
- Backfill: Research crew `account_id` = project OWNER + ACTIVE
  RESEARCHER roster row; `ComputeDebit.actor_id` from
  `AgentRun.agent_actor_id` only.

## What did not change

- `ensure_is_member` / `ensure_can_manage`. Crew tab. Five tabs.
- `create_checkpoint` signature (no `sponsored_by` yet).
- `record_compute_debit` signature (no `actor_id` yet).
- Hold/release amount `0`, literal `harness_session_turn` prefix,
  `hold_id`. Debit only when `tokens_used > 0`.
- FastAPI does not import `app.harness`. `fly.toml [env]` has no
  secrets. Nothing enabled on Fly.
- `docs/plans/agent-actor-identity.md` untouched (PR #47).

## Exact DDL summary

Postgres labels are StrEnum **member names**.

```sql
CREATE TYPE project_agent_role AS ENUM ('RESEARCHER');
CREATE TYPE project_agent_status AS ENUM ('ACTIVE', 'SUSPENDED', 'REVOKED');

CREATE TABLE project_agent_members (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    actor_id UUID NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    deployed_by_account_id UUID REFERENCES accounts(id) ON DELETE SET NULL,
    responsible_account_id UUID REFERENCES accounts(id) ON DELETE SET NULL,
    role project_agent_role NOT NULL,
    status project_agent_status NOT NULL DEFAULT 'ACTIVE',
    token_budget_cap INTEGER,
    usd_budget_cap NUMERIC(12, 6),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_project_agent_member UNIQUE (project_id, actor_id)
);
CREATE INDEX ix_project_agent_members_project_id ON project_agent_members (project_id);
CREATE INDEX ix_project_agent_members_actor_id ON project_agent_members (actor_id);
CREATE INDEX ix_project_agent_members_project_status ON project_agent_members (project_id, status);
CREATE INDEX ix_project_agent_members_responsible ON project_agent_members (project_id, responsible_account_id);

CREATE TABLE agent_session_tokens (
    id UUID PRIMARY KEY,                    -- also JWT jti
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    actor_id UUID NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
    minted_by_account_id UUID REFERENCES accounts(id) ON DELETE SET NULL,
    minted_by_actor_id UUID REFERENCES actors(id) ON DELETE SET NULL,
    token_hash BYTEA NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_agent_session_tokens_hash UNIQUE (token_hash)
);
CREATE INDEX ix_agent_session_tokens_project_id ON agent_session_tokens (project_id);
CREATE INDEX ix_agent_session_tokens_lookup
    ON agent_session_tokens (actor_id, project_id, revoked_at, expires_at);

ALTER TABLE checkpoints
    ADD COLUMN sponsored_by_actor_id UUID
        REFERENCES actors(id) ON DELETE SET NULL;
CREATE INDEX ix_checkpoints_sponsored_by_actor_id
    ON checkpoints (sponsored_by_actor_id);

ALTER TABLE compute_debits
    ADD COLUMN actor_id UUID
        REFERENCES actors(id) ON DELETE SET NULL;
CREATE INDEX ix_compute_debits_actor_id
    ON compute_debits (actor_id);

-- NOT added: actors.agent_definition_id (deferred with agent_definitions)

CREATE UNIQUE INDEX uq_actors_one_research_crew_per_project
    ON actors ((actor_metadata ->> 'project_id'))
    WHERE type = 'AGENT' AND display_name = 'Research crew';
DROP INDEX uq_actors_one_agent_per_project;
```

Backfill (idempotent: `WHERE account_id IS NULL` / `actor_id IS NULL`,
`ON CONFLICT DO NOTHING`):

```sql
UPDATE actors AS a
SET account_id = pm.account_id
FROM project_members pm
WHERE a.type = 'AGENT'
  AND a.display_name = 'Research crew'
  AND a.account_id IS NULL
  AND (a.actor_metadata->>'project_id') ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
  AND pm.project_id = (a.actor_metadata->>'project_id')::uuid
  AND pm.role = 'OWNER';

INSERT INTO project_agent_members (
    id, project_id, actor_id, deployed_by_account_id, responsible_account_id,
    role, status, token_budget_cap, usd_budget_cap, created_at, updated_at
)
SELECT gen_random_uuid(), (a.actor_metadata->>'project_id')::uuid, a.id,
       a.account_id, a.account_id, 'RESEARCHER', 'ACTIVE', NULL, NULL, now(), now()
FROM actors a
JOIN projects p ON p.id = (a.actor_metadata->>'project_id')::uuid
WHERE a.type = 'AGENT'
  AND a.display_name = 'Research crew'
  AND a.account_id IS NOT NULL
  AND (a.actor_metadata->>'project_id') ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
ON CONFLICT ON CONSTRAINT uq_project_agent_member DO NOTHING;

UPDATE compute_debits AS d
SET actor_id = r.agent_actor_id
FROM agent_runs r
WHERE d.agent_run_id = r.id
  AND d.actor_id IS NULL
  AND r.agent_actor_id IS NOT NULL;
-- harness_session_turn rows are not touched.
```

Downgrade refuses if any `actor_metadata.project_id` has more than
one `type=agent` Actor, then recreates the old unique index,
nulls debit `actor_id`, drops the new columns/tables/enums, and
restores Research-crew `account_id` to NULL.

## Prod-apply runbook

Do **not** apply until the owner reviews. Target is the live
Supabase Postgres (`iaokmtutxponegwebvdu`) over
`MIGRATION_DATABASE_URL` (direct session, not the pooler).
Review-time (2026-10-06, live read-only): **checkpoints 0,
compute_debits 0, actors 2, agent actors 0, alembic at 0021**.
The SHARE lock from transactional `CREATE INDEX` is negligible
at that size. A future large-table migration should revisit
`CREATE INDEX CONCURRENTLY` and must check `pg_index.indisvalid`
before treating an existing index as done — a failed concurrent
unique build can leave an `INVALID` index that `IF NOT EXISTS`
would then skip. Concurrent writers keep working: new checkpoints
insert without a sponsor; new harness debits insert without
`actor_id`. The AgentRun backfill is indexed on `agent_run_id`.

### Pre-checks

```sql
-- Alembic head before apply should be 0021.
-- Research crew rows and whether they have an OWNER to attach:
SELECT a.id, a.account_id, a.actor_metadata->>'project_id' AS project_id,
       pm.account_id AS owner_account_id
FROM actors a
LEFT JOIN project_members pm
  ON pm.project_id = (a.actor_metadata->>'project_id')::uuid
 AND pm.role = 'OWNER'
 AND (a.actor_metadata->>'project_id') ~*
     '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
WHERE a.type = 'AGENT' AND a.display_name = 'Research crew';

-- Expected backfill counts (record these):
SELECT COUNT(*) AS crew_with_owner
FROM actors a
JOIN project_members pm
  ON pm.project_id = (a.actor_metadata->>'project_id')::uuid
 AND pm.role = 'OWNER'
WHERE a.type = 'AGENT' AND a.display_name = 'Research crew'
  AND a.account_id IS NULL;

SELECT COUNT(*) AS crew_without_owner
FROM actors a
WHERE a.type = 'AGENT' AND a.display_name = 'Research crew'
  AND a.account_id IS NULL
  AND NOT EXISTS (
    SELECT 1 FROM project_members pm
    WHERE pm.role = 'OWNER'
      AND (a.actor_metadata->>'project_id') ~*
          '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
      AND pm.project_id = (a.actor_metadata->>'project_id')::uuid
  );

SELECT COUNT(*) AS debits_from_agent_run
FROM compute_debits d
JOIN agent_runs r ON r.id = d.agent_run_id
WHERE r.agent_actor_id IS NOT NULL;

SELECT COUNT(*) AS harness_session_turn_rows
FROM compute_debits
WHERE notes LIKE 'harness_session_turn%';

-- Two Research-crew rows on one project would fail the new unique:
SELECT actor_metadata->>'project_id', COUNT(*)
FROM actors
WHERE type = 'AGENT' AND display_name = 'Research crew'
GROUP BY 1 HAVING COUNT(*) > 1;
-- Expect 0 rows.
```

### Apply

```bash
cd backend
# Direct session URL — not the transaction pooler.
# Do not point this at prod from a laptop without the owner's OK.
uv run alembic upgrade 0022_agent_actor_identity
```

The revision is **one transaction** (plain `CREATE INDEX` /
`DROP INDEX`). No `CONCURRENTLY`, no `autocommit_block`, no
`IF NOT EXISTS` / `IF EXISTS` hedges. A failure rolls the
whole revision back — `create_table` is not idempotent, so a
mid-migration commit would leave a half-applied schema a
re-run cannot recover.

### Verify

```sql
SELECT extname FROM pg_extension;  -- unchanged; no new extension

SELECT typname FROM pg_type
WHERE typname IN ('project_agent_role', 'project_agent_status');

SELECT COUNT(*) FROM project_agent_members;          -- = crew_with_owner
SELECT COUNT(*) FROM project_agent_members
WHERE status = 'ACTIVE' AND role = 'RESEARCHER';     -- same
SELECT COUNT(*) FROM actors
WHERE type = 'AGENT' AND display_name = 'Research crew' AND account_id IS NULL;
-- = crew_without_owner (plus any already-owned rare rows)

SELECT COUNT(*) FROM compute_debits WHERE actor_id IS NOT NULL;
-- = debits_from_agent_run
SELECT COUNT(*) FROM compute_debits
WHERE notes LIKE 'harness_session_turn%' AND actor_id IS NOT NULL;
-- = 0

SELECT indexname FROM pg_indexes
WHERE indexname IN (
  'uq_actors_one_research_crew_per_project',
  'uq_actors_one_agent_per_project'
);
-- first present, second absent

SELECT column_name FROM information_schema.columns
WHERE table_name = 'actors' AND column_name = 'agent_definition_id';
-- 0 rows
```

### Rollback

```bash
cd backend
uv run alembic downgrade 0021_concurrent_campaign_cycles
```

Refuses if any project already has two `type=agent` Actors
sharing `actor_metadata.project_id` (fail closed; do not DISTINCT
guess). After a successful downgrade, Research-crew `account_id`
is NULL again and the old one-agent-per-project unique is back.

## Tests

- DB-free: revision linkage, single head, enum labels, model /
  migration column agreement, no `agent_definition_id` column,
  new tables not in append-only guards.
- DB-gated: `upgrade head` on empty Postgres; backfill
  correctness (owned crew rostered; owner-less and invalid
  project_id left null/unrostered; AgentRun debit stamped;
  harness / null-run / other debits stay null; amounts/notes
  untouched); upgrade/downgrade round-trip; downgrade refuse
  when two agents share a project; roster unique pair; Research
  crew partial unique + named agent legal; invalid enum rejected;
  `create_checkpoint` / `record_compute_debit` leave the new
  columns null; roster is mutable, Checkpoint is not;
  indexes are transactional (no CONCURRENTLY / autocommit);
  an owner whose Account also owns a Research-crew agent still
  resolves to their human Actor via bearer and MCP, and
  member / actor / account listings do not double-count.
- Existing suite green. Frontend untouched.

## Verification

- `ruff check .` clean.
- With `TEST_DATABASE_URL`: **1144 passed, 4 skipped**. +16 vs
  `0.52.0` (1128) — 0022 upgrade/downgrade/backfill/constraints +
  named-agent unique + transactional-index pin + owner+Research-crew
  human-resolution regression. Two 0.52.0 "no `actor_id` attribute"
  pins flipped to "column exists, harness writes leave it null."
  Harness suite **139 passed**. Lean / Mathlib stay off.
- Frontend untouched: typecheck / lint / build clean; **64 tests**.

## Unverified

- Live Supabase apply (owner reviews first).
- Token mint / membership gate / Crew bay (later slices).
