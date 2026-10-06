# 0.56.0 — Spend attribution

**Goal.** Land slice D (spend) of the approved agent-actor
identity design: stamp `compute_debits.actor_id` on the harness
turn path and the built-in agent pass. Stay dark: no Fly, no
`AGENT_LOOP_ENABLED`, no Crew UI, no ops `actor_*` readout, no
per-agent cap enforcement. No live Supabase apply (no
migration — 0022 already has the column). Sits on shipped
`0.55.0` (`149c36e`, #51).

**Shape.** Writer + session bind on the existing 0022 schema.
No new table, no new column, no Alembic revision.

## What shipped

- `record_compute_debit(..., actor_id=)` and
  `write_daily_cap_adjustment(..., actor_id=)`.
- `HarnessSession` binds the resolved actor at `authorize()`
  (`bound_actor_id` / `bound_jti`). Session `env` wins over a
  per-turn `actor_env` (outsider / confused-deputy override
  closed).
- Hold and release rows carry `actor_id` for audit. Amount
  stays `0`. Notes still start with the literal
  `harness_session_turn` prefix and pair by `hold_id`.
- `record_spend` loads `jti` to stamp `actor_id` even when the
  token was revoked mid-turn. It does **not** refuse: tokens
  that moved after a successful authorize are billed (0.52.0
  mid-turn rule). The next `authorize()` refuses.
- Built-in `run_agent_pass` planning debit stamps
  `AgentRun.agent_actor_id`.
- Shared project daily cap. Per-agent `token_budget_cap` /
  `usd_budget_cap` stay stored, unenforced.
- Unfunded ≠ exhausted. Debit only when `tokens_used > 0`.

## What did not change

- Crew UI / blame sponsor / ops `actor_*` + spend-by-agent
  (slice E).
- Per-agent cap enforcement (slice F).
- `agent_definitions` (slice G).
- FastAPI does not import `app.harness`. `fly.toml [env]` has
  no secrets. Nothing enabled on Fly. Five tabs.
- No migration. 0022 is still not applied to live Supabase.

## Tests

- Agent-token authorize + `record_spend`: spend, hold, and
  release stamp the agent.
- Mid-turn revoke: in-flight `record_spend` with
  `tokens_used > 0` still writes with `actor_id`; next
  `authorize()` refuses.
- Session bind wins over a member `actor_env` (spend stays the
  bound agent).
- `tokens_used == 0` writes no spend row; hold/release stay
  amount `0` with `actor_id`.
- Built-in pass debit `actor_id == AgentRun.agent_actor_id`.
- Existing human DEV_ACTOR_ID harness spend now stamps that
  human (pins flipped from null).

## Verification

- `ruff check .` clean.
- With `TEST_DATABASE_URL`: counts pending local suite.
- Frontend untouched.

## Unverified

- Live MCP child speaking as an agent on Fly (not enabled).
- Per-agent cap enforcement (slice F).
- Crew roster bay / ops actor fields (slice E).
