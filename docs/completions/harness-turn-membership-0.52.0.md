# 0.52.0 — Harness turn-spend membership

**Goal.** Close the leftover 0.51.1 membership gap on the harness
turn-spend path (`HarnessSession` / gateway / `supervise_turn` →
`authorize` / `record_spend` → `record_compute_debit` with notes
`harness_session_turn`). Spend must fail closed unless the actor
the session / turn is running for is a current member of that
project. Do not light `AGENT_LOOP_ENABLED`. Do not enable the
gateway or MCP child on Fly. **No schema, no migration.** Sits on
shipped `0.51.1` (`3eeeaf5`, #46).

**Shape.** Membership check at the existing `authorize()`
chokepoint, using the existing actor injection and
`ensure_is_member`. No new column. No new table.

## Why this shape

- The 0.51.1 audit found no write-path gap: MCP
  `run_instrument` / `create_checkpoint` already resolve the JWT
  Actor and call `ensure_is_member`. `ComputeDebit` has no
  `actor_id`; remapping spend onto an Actor would be a schema
  change this slice refuses.
- The real leftover was the spend path. The gateway child is
  project-bound (`OPENTHEORY_PROJECT_ID`) and authenticated by
  `OPENTHEORY_GATEWAY_TOKEN`. An outsider `actor_env` on
  `supervise_turn` could still take a hold, call the provider,
  and debit. The 0.51.1 regression pinned that.
- The actor on the turn path is already there: `actor_env` on
  `supervise_turn` (the same credential `live_mcp` uses), and
  `env` on the session-owned campaign / gateway child
  (operator-supplied JWT file / JWT / flagged
  `OPENTHEORY_DEV_ACTOR_ID`). `0.43` `HarnessSession` is the
  session owner, not an Actor — it does not mint one. Binding
  `actor_env` onto that in-memory owner is enough. No schema.
- The clean helper is `ensure_is_member` (account membership;
  account-less is `403`). `resolve_mcp_actor` is the same
  resolver as the MCP door. HTTP status maps to `TurnRefused` so
  the gateway stays 422 with no provider call.

## Decision: no re-check at `record_spend`

A member *can* be removed mid-turn (`ProjectMember` is mutable;
the provider call can last up to the turn deadline). Re-checking
at `record_spend` is cheap (one membership SELECT) but not
correct: after a successful `authorize()` the provider may
already have been called. Skipping the debit would leave the
project pot uncharged for tokens that moved. Raising
`TurnRefused` after the model ran would confuse a turn that
already started.

Membership is a start-of-turn gate, same as pot / daily cap /
floor. Tokens that moved after a successful authorize are billed.
The next authorize fails closed. The mid-session removal test
pins both sides.

## What shipped

- `HarnessSession.actor_env` (in-memory). `authorize()` calls
  `assert_turn_member` → `resolve_mcp_actor` +
  `ensure_is_member` *before* the project-row lock writes a hold
  or releases a stale one. Missing credential →
  `TurnRefused("actor required")`. Non-member / account-less /
  missing project → `TurnRefused("not a project member")`.
- `supervise_turn` passes `actor_env` onto the session owner.
  `open_session` / `session_from_env` accept the same lookup.
- `record_spend` does not re-check (decision above).
- 0.51.1 outsider regression flipped to refusal. New tests:
  member allowed; non-member / account-less `Research crew`
  refuse with no hold, no debit, no provider call; removed
  mid-session as designed.
- `docs/harness/attribution.md` records the new check.
  Changelog `0.52.0` newest-first. Roadmap banner updated in
  place on shipped `0.51.1`.

## What did not change

- `create_checkpoint` remains the only Checkpoint writer.
- Append-only guards. Account ≠ Actor. Funder ≠ contributor ≠
  validator.
- `ComputeDebit` has no `actor_id`. `FundingAllocation` is
  untouched.
- Unfunded ≠ exhausted. Debit only when `tokens_used > 0`.
- Hold/release amount `0`, literal `harness_session_turn`
  prefix, `hold_id`.
- `0.47`–`0.51` serialization / TTL / deadline / clamp / hold
  occupancy.
- Five tabs. `AGENT_LOOP_ENABLED` default `false`. Fly `[env]`
  still has no secrets. FastAPI still does not import
  `app.harness`.
- No Alembic revision. `docs/plans/agent-actor-identity.md`
  untouched.

## Tests

- DB-gated: member `actor_env` authorizes, calls the provider,
  and debits when tokens moved.
- Outsider `actor_env` is `TurnRefused` — no hold, no debit, no
  provider call, no mint. `FundingAllocation` unchanged.
- Account-less project agent (`Research crew`) refuses the same
  way.
- Collaborator removed after a successful authorize: mid-turn
  `record_spend` still bills; the next authorize refuses and
  writes no hold.
- Existing 0.47–0.51 session-ledger races keep passing with a
  member `actor_env` on the owner.

## Verification

- `ruff check .` clean.
- With `TEST_DATABASE_URL`: **1128 passed, 4 skipped**. +3 vs shipped
  `0.51.1` (1125) — member allowed, account-less refuse,
  removed-mid-session (outsider flipped in place). Harness suite
  **139 passed**. Lean / Mathlib stay off.
- Frontend untouched: typecheck / lint / build clean; **64 tests**.

## Unverified

- Live OpenRouter / `dsh` round-trip (still dark).
- Fly enablement of the harness child.
