# 0.58.0 — Per-agent lifetime caps

**Goal.** Land slice F (optional caps) of the approved
agent-actor identity design: enforce `token_budget_cap` /
`usd_budget_cap` on `project_agent_members` at
`HarnessSession.authorize()` and on the built-in pass; expose
Crew edit and cap-reached on Crew / ops reads. Stay dark: no
Fly, no `AGENT_LOOP_ENABLED`, no definition catalog. No live
Supabase apply (no migration — columns exist on 0022). Sits
on shipped `0.57.1` (`2ed3d23`, #54).

**Shape.** Behavior on the existing 0022 schema. No new table,
no new column, no Alembic revision.

## What shipped

- Lifetime per roster seat (the design names no period).
  Null = no per-agent limit.
- Remaining tokens = cap − billed `ComputeDebit` for
  `(project_id, actor_id)` (`tokens_used > 0`, hold/release
  excluded) − that agent's unmatched remaining-room holds.
  USD remaining = cap − billed `amount` (holds are amount 0).
  Loaded under the project-row `FOR UPDATE`.
- Cap reached is `TurnRefused` with a distinct reason
  (`agent token budget cap exhausted` /
  `agent usd budget cap exhausted`) and no hold.
- Turn clamp is `min(daily room, pot room, agent remaining)`.
  The ledger hold still occupies the whole remaining daily
  room — not a per-agent split of the project daily cap.
- Built-in pass: start refuse before the planner; mid-pass
  skip remaining instruments after planning tokens are billed
  (`agent_budget_cap_exhausted`).
- Crew `PATCH` edits caps (`OWNER` / `ADMIN`). Roster and
  ops `spend_by_agent` send `*_cap_reached`. Frontend treats
  those fields as optional and derives from billed vs cap
  when a pre-0.58 backend omits them.

## What did not change

- Shared project daily cap. Unfunded ≠ exhausted. Debit only
  when `tokens_used > 0`. Mid-turn billing after a successful
  authorize.
- `agent_definitions` (slice G).
- FastAPI does not import `app.harness`. `fly.toml [env]` has
  no secrets. Nothing enabled on Fly. Five tabs.
- No migration. 0022 is still not applied to live Supabase.

## Judgment calls

- **Lifetime per seat.** Design is silent on the window.
- **Billed spend includes the built-in pass prefix**, not
  only `harness_session_turn`. The user required enforcement
  on both paths; one cap per roster seat covers both.
- **Outstanding holds count toward token remaining** (defense
  in depth). Concurrent same-agent second authorize still
  usually hits the shared daily cap first, because the hold
  occupies all remaining daily room.
- **Hold occupancy is not clamped to agent remaining.** That
  would split the project daily cap and re-open 0.47–0.51.
  Only `max_tokens` / turn clamp is the min.
- **Built-in pass releases the project-row lock after the
  start check** (`commit` before the planner). Holding it
  through an injected `budget_policy` planner serialized
  0.32 concurrent campaign cycles. A later start re-takes
  the lock; mid-pass stop sees tokens billed after that
  commit. Harness `authorize()` still holds until the
  remaining-room hold writes.
- **USD converts at a known live/catalog rate only.** An
  unknown rate does not invent a blended price; USD already-
  reached still refuses without a price.
- **Crew / ops `*_cap_reached` are optional on the client.**
  Backend 0.58 always sends them; a pre-0.58 response must
  not throw (0.57.1 skew). Display derives from billed vs
  stored caps when the flag is missing. Holds are not spend,
  so the readout is billed-based.
- **Crew edit uses the existing PATCH** (status optional +
  cap fields). `OWNER` / `ADMIN` via `ensure_can_manage`.
  `null` clears a cap.

## Tests

- Null caps still authorize. Human authorize (no roster row)
  has no per-agent cap.
- Token / USD cap reached → `TurnRefused`, no hold.
- Remaining tokens clamp `max_tokens`; hold occupancy stays
  the whole remaining daily room.
- Unfunded + a set cap is not pot-exhausted.
- Overlapping authorize: second refuses, one hold.
- Mid-turn spend over the cap still writes; next authorize
  refuses.
- Clearing a reached cap authorizes again.
- Built-in pass refuses before the planner when already
  reached; mid-pass skips remaining after planning debit.
- PATCH caps: OWNER / ADMIN; outsider 403; empty body 422;
  roster / ops expose reached after billed spend.

## Verification

- `ruff check .` clean.
- With `TEST_DATABASE_URL`: **1199 passed, 4 skipped**. +14 vs
  `0.57.0` (1185). Lean / Mathlib stay off.
- Frontend typecheck / lint / test (**75 passed**, +2 vs
  `0.57.1`) / build clean.

## Unverified

- Live MCP / gateway child speaking as an agent on Fly
  (not enabled).
- Browser walk of Crew cap edit against a seeded project
  (depends on local Next + FastAPI + throwaway Postgres).
- Two overlapping authorizes that would pass the daily cap
  and only race the agent cap — today's hold occupies the
  whole remaining daily room, so the second hit is daily-cap
  first. Outstanding-hold math is the defense if occupancy
  is ever smaller.
