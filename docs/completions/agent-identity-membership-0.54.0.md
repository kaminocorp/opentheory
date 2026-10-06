# 0.54.0 — Agent identity membership gate

**Goal.** Land slice B (membership gate) of the approved
agent-actor identity design so a rostered `Actor(type=agent)`
can pass research writes, cannot govern or fund or validate,
and is suspended + token-revoked when the deploying OWNER
transfers the project. Stay dark: no token mint, no Fly, no
`AGENT_LOOP_ENABLED`. No live Supabase apply (no migration).
Sits on shipped `0.53.0` (`2b2a135`, #49).

**Shape.** Service + route behaviour on the existing 0022
schema. No new table, no new column, no Alembic revision.

## What shipped

- `ensure_is_member` is type-aware:
  - `human` — `account_id` + `ProjectMember` (unchanged).
  - `agent` — ACTIVE `project_agent_members` row for
    `(project_id, actor.id)`. Sponsor-account membership is
    not consulted.
  - `system` — `403`.
- `ensure_can_manage` rejects `type=agent` before the account
  lookup (an agent whose `account_id` is the owner cannot
  invite, PATCH models, or transfer).
- `ensure_is_human_member` on `POST …/funding`,
  `POST …/validations`, and invite-accept / decline
  (`_require_invitee` requires `type=human`).
- OWNER-transfer hook in `set_member_role` (same transaction,
  helper `db.add`s and does not commit): suspend Research crew
  + `responsible_account_id = outgoing` rows; revoke their
  live tokens. ADMIN-deployed agents whose responsible account
  is not the outgoing owner stay `ACTIVE`.
- `get_or_create_project_agent_actor` ensures an ACTIVE
  RESEARCHER roster row when the project exists and none does.
  Does not revive `SUSPENDED` / `REVOKED`. Attaches the OWNER
  account when the Actor is still account-less.
- Dark-loop `start_agent_pass` 403s when a Research-crew Actor
  already exists without an ACTIVE roster. `run_agent_pass`
  re-checks after `get_or_create` (failed trace, mints nothing).
- Service-level `resume_project_agent` (OWNER only): only
  `SUSPENDED` is resumable (what OWNER-transfer produces).
  Sets `status=ACTIVE` and `responsible_account_id` = acting
  account. `ACTIVE` → `409` "agent is already active".
  `REVOKED` is terminal → `409` "agent is revoked; deploy a
  new agent". Does not rewrite `Actor.account_id` /
  `deployed_by`. Does not un-revoke tokens. No HTTP surface
  (Crew UI is slice E).
- `get_or_create_project_agent_actor` heals a *missing*
  roster row for an existing Research-crew Actor only on
  paths that call it directly: `run_agent_pass` (`_execute`),
  `orchestration.py` (pre-wave mint), and `campaigns.py`
  (pre-cycle mint). `start_agent_pass` does **not** heal —
  an existing un-rostered crew is `403` there. After
  migration 0022 every migrated crew is rostered, so this
  is an orphan / test-insert edge case. A `SUSPENDED` /
  `REVOKED` row is never revived.

## What did not change

- Token mint / rotate / resolver / `typ=agent_session`.
- `authorize()` still resolves the human JWT / flagged
  `OPENTHEORY_DEV_ACTOR_ID` and calls `ensure_is_member`
  (now type-aware). The 0.52.0 human-JWT swap is slice C.
- `create_checkpoint` signature (no `sponsored_by` yet).
- `record_compute_debit` signature (no `actor_id` yet).
- Hold/release amount `0`, literal `harness_session_turn`
  prefix, `hold_id`. Debit only when `tokens_used > 0`.
- FastAPI does not import `app.harness`. `fly.toml [env]`
  has no secrets. Nothing enabled on Fly. Five tabs.
- No migration. 0022 is still not applied to live Supabase.

## Tests

- Type-aware gate: un-rostered / account-less / owner's
  `account_id` but no roster / `SUSPENDED` / `REVOKED` /
  `system` → `403`; rostered agent may write a checkpoint
  (`author_id` = agent) and cannot fund, validate, invite,
  PATCH, or assign models.
- Human member write stays the human; no invented sponsor.
- `get_or_create` on an owned project attaches the OWNER
  account + ACTIVE RESEARCHER roster; second call is
  idempotent; a `SUSPENDED` row is not revived.
- Dark-loop `start_agent_pass` 403s on an existing
  un-rostered crew; first pass with no crew yet is allowed.
- OWNER transfer: Research crew + outgoing-responsible
  suspend, their tokens get `revoked_at`; ADMIN-deployed
  stays `ACTIVE` with a live token; `account_id` /
  `deployed_by` unchanged. Resume by the new OWNER of a
  `SUSPENDED` row sets `responsible_account_id` and leaves
  old tokens revoked. Resume of `ACTIVE` / `REVOKED` is
  `409` (revoked stays revoked; tokens stay revoked).
- Agent sharing an invitee's `account_id` cannot accept.
- Existing 0.51.1 / 0.52.0 pins updated to insert a raw
  un-rostered crew (so `get_or_create` cannot heal a seat).

## Verification

- `ruff check .` clean.
- With `TEST_DATABASE_URL`: **1154 passed, 4 skipped**. +10 vs
  `0.53.0` (1144) — type-aware gate, roster ensure, OWNER-transfer
  hook, dark-loop commission, human-only fund/validate/invite.
  Lean / Mathlib stay off. Harness suite **139 passed**.
- Frontend untouched.

## Unverified

- Live MCP child speaking as an agent (needs slice C token).
- Per-agent cap enforcement (slice F).
- Crew roster bay (slice E).
