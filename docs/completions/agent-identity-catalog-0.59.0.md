# 0.59.0 — Definition catalog + built-in pass cap clamp

**Goal.** Land slice G (definition catalog) of the approved
agent-actor identity design, and close the leftover 0.58.0
soft cap on the built-in pass. Stay dark: no Fly, no
`AGENT_LOOP_ENABLED`. No live Supabase apply. Sits on shipped
`0.58.1` (#57, public PostgREST lock) / shipped `0.58.0`
(`c1a4ca5`, #55). Live prod is still at 0021; this merge
waits on that verify. Rebased onto #57 so the catalog
revision is `0024`.

**Decision.** The clamp still ships in this `0.59.0` PR (not
a separate patch). `0.58.1` (#57) is the public PostgREST
lock, stacked under this branch.

**Shape.** Migration `0024_agent_definitions` revises
`0023_lock_public_api_rls`. One transaction (plain
`CREATE INDEX` / `DROP INDEX`; no `CONCURRENTLY` /
autocommit). After `create_table` it runs
`LOCK_PUBLIC_TABLES_SQL` so `agent_definitions` is
ENABLE+FORCE. Downgrade drops `actors.agent_definition_id`
then `agent_definitions`.

## What shipped

- `agent_definitions` as the design's table: Account-owned
  versioned kind, unique `(family_id, version)`, indexes on
  `account_id` and `family_id`. Not append-only.
- `actors.agent_definition_id` nullable FK in the **same**
  revision. Deploy-time pointer on named agents. Research
  crew stays pointer-less (`422` if a definition is supplied).
- Same-Actor retarget rejected (`before_update` + no PATCH
  field). Upgrade = new version + new project Actor; previous
  seat revoked and visible. Caps copy. `author_id` untouched.
- Cosmetic rename = same version. Config fingerprint change
  (model id / harness pin / Cordis inventory / persona hash)
  = new version of the same `family_id`.
- Read-only family rollup: `JOIN` actors on versions of the
  family, then Σ checkpoints authored, incoming `Validation`
  rows that target those checkpoints, billed `ComputeDebit`.
- HTTP human-only. Catalog writes are the acting Account.
  Family read is the owner or a member of a project that has
  a pointing actor.
- Built-in pass: each pass's token budget is
  `min(agent_pass_max_tokens, remaining at start)`. Reserve
  envelope and `BudgetPolicy` (injected or default) wrap with
  that ceiling. Start check still releases the project-row
  lock so 0.32 campaign cycles can overlap.
- Crew: optional pointer / kind picker / register-kind /
  upgrade. Catalog `404` is a quiet "not on this backend yet"
  line. New roster fields are optional (0.57.1 skew rule).
  Five tabs.

## Known limit — leftover overshoot bound

Two concurrent built-in passes on the same seat can both
pass the start check after the lock is released. Each is
then clamped to the remaining room **as of that start**, so
both may spend up to that clamped budget. Leftover overshoot
is **at most one pass budget per concurrent pass**. The
harness path is unchanged: `authorize()` still holds the
project row until the remaining-room hold writes, and that
hold occupies the whole remaining daily room.

## What did not change

- Merging Actors. Rewriting `author_id`. Lighting the loop.
- Shared project daily cap. Unfunded ≠ exhausted. Debit only
  when `tokens_used > 0`.
- FastAPI does not import `app.harness`. `fly.toml [env]`
  has no secrets. Nothing enabled on Fly.
- 0022 is still not applied to live Supabase. This revision
  does not assume it is.

## Judgment calls

- **One PR (0.59.0), not 0.58.1 + 0.59.0.** Loop is dark;
  merge already waits on the 0022 deploy.
- **Fingerprint keys** are `model_id`, `harness_pin`,
  `cordis_inventory`, `persona_hash`. Extra config keys are
  stored for display and do not bump the version.
- **Research crew never gets a pointer.** The built-in name
  is not a catalog kind.
- **Upgrade copies caps** onto the new seat. Design is
  silent; the lifetime ceiling is a property of the roster
  slot the human is replacing.
- **Upgrade does not require the acting account to own the
  target version** (any project manager can move a seat to a
  newer version of the same family). Creating versions still
  requires ownership. Deploy-with-pointer still requires the
  acting account owns the definition.
- **Rollup incoming validations** are `Validation` rows
  whose `checkpoint_id` is a checkpoint authored by a family
  actor. Claim-only validations with no checkpoint are not
  counted.
- **Family read auth:** owner of any version, or member of a
  project that has an actor pointing at a family version.
  Outsiders get `404` (no existence leak).
- **Crew does not add a catalog tab.** Pointer, kind picker,
  register-kind, and upgrade live on the existing Crew bay.

## Tests

- Fingerprint stable across display-only keys; changes when
  a fingerprint input changes.
- Create / list / cosmetic PATCH / new version / same
  fingerprint `409` / outsider `404`.
- Deploy pointer; Research crew + definition `422`; upgrade
  new Actor + revoke; same version / other family `409`;
  ORM retarget rejected.
- Family rollup counts checkpoints, incoming validations,
  billed tokens; project member can read; outsider `404`.
- Agent session on catalog HTTP is `403`.
- 0024 linkage, only head, transactional indexes, not
  append-only, upgrade-head schema (including RLS+FORCE on
  `agent_definitions`), downgrade round-trip, unique
  `(family_id, version)`.
- Pass token budget = `min(safety, remaining)`; reserve
  envelope shrinks; injected `BudgetPolicy` still clamped;
  existing mid-pass skip still `agent_budget_cap_exhausted`.

## Verification

- `ruff check .` clean.
- With `TEST_DATABASE_URL`: **1213 passed, 4 skipped**. +14 vs
  `0.58.0` (1199). Lean / Mathlib stay off.
- Frontend typecheck / lint / test (**76 passed**, +1 vs
  `0.58.0`) / build clean.

## Unverified

- Live MCP / gateway child speaking as an agent on Fly
  (not enabled).
- Browser walk of Crew kind / upgrade against a seeded
  project (depends on local Next + FastAPI + throwaway
  Postgres).
- Applying 0022 / 0023 / 0024 to live Supabase.
