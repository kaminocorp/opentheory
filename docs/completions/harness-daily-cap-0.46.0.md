# 0.46.0 — Harness daily token cap

**Goal.** Stop a restarted or long-lived session-owned harness child
from spending the whole project pot in a day. The 0.43–0.44 owner has
a process-local turn cap (default 4) and a funded-pot check; turn
index resets to 0 on restart, so it is not a daily ceiling. Count
today's harness spend from the existing `ComputeDebit` ledger and
refuse before the model when that day's cap is hit. Do not light
`AGENT_LOOP_ENABLED`. Prefer no schema / no migration. Default CI
stays green without `OPENROUTER_API_KEY` or a live network.

**Shape.** `HarnessSession.authorize()` on the campaign child /
bound gateway (not only `supervise_turn`). Meter is today's
`ComputeDebit` rows whose notes start with `harness_session_turn`.
Default **20_000** tokens per UTC day, operator-overridable via
`OPENTHEORY_HARNESS_DAILY_TOKEN_CAP`. **No schema, no migration,
no campaign table.** Sits on shipped `0.45.0` (`43f419c`, #38).

## What shipped

- **Daily token cap on the session-owned path.** Before a completion:
  composition re-verify, process-local `OPENTHEORY_HARNESS_MAX_TURNS`,
  today's harness token sum vs `OPENTHEORY_HARNESS_DAILY_TOKEN_CAP`,
  then funded-pot exhaust (`funded > 0` and `available <= 0`). A
  refused start writes nothing and does not call OpenRouter.
- **The ledger is the meter.** `harness_tokens_used_today` sums
  `ComputeDebit.tokens_used` for the project since UTC midnight
  where notes start with the literal `harness_session_turn` prefix
  (`startswith(..., autoescape=True)` — `_` / `%` are not LIKE
  wildcards). `record_compute_debit` may append a rate-fallback
  suffix; that still counts. A new `HarnessSession` at
  `turn_index=0` still refuses. Yesterday does not count.
  Agent-pass debits and a LIKE-lookalike note
  (`harness-session-turn extra`) do not count.
- **Default 20_000 tokens / UTC day.** Small: a handful of short
  planning completions. Not a process-local 4-turn replay after every
  restart. Operators raise `OPENTHEORY_HARNESS_DAILY_TOKEN_CAP`
  (integer `>= 1`).
- **Honesty unchanged.** Unfunded ≠ exhausted. Debit only when
  `tokens_used > 0`. Exceptions mint nothing. `create_checkpoint`
  remains the only Checkpoint writer. FastAPI still does not import
  the package.

## What did not change

- `create_checkpoint` remains the only Checkpoint writer.
- Append-only guards, membership, instruments, built-in campaigns,
  orchestrator.
- `AGENT_LOOP_ENABLED` default `false`. Fly `[env]` still has no
  secrets. The gateway / MCP child is **not** enabled on Fly.
- Funder ≠ contributor ≠ validator. Account ≠ Actor.
- No Alembic revision. No frontend. No ops dashboard. No UI chart.
- Process-local turn index still resets to 0 on restart. That is
  why the daily cap exists.

## Honest caveats

- A green default pytest is not a live OpenRouter / `dsh` session.
- Two overlapping in-flight completions can both pass `authorize()`
  and then both debit, overshooting the cap by one turn. Same race
  the pot check already has; this slice does not add a reservation
  lock or a campaign table. **Closed in `0.47.0`** — see
  `docs/completions/harness-daily-cap-race-0.47.0.md`.
- The unmetered probe (`OPENTHEORY_HARNESS_UNMETERED_PROBE`) is still
  unmetered. `verify()` will not accept it as the campaign composition.
- Ops dashboard / Fly enablement / lighting the built-in planner
  remain later.

## Tests

- Default 20_000 is documented and overridable; `0` / non-integer
  refuse; UTC day start is midnight inclusive.
- Compiled notes prefix uses `ESCAPE` / escaped `_` (default CI).
- Session-from-env reads the override; health reports `daily_token_cap`.
- Gateway version is `0.46.0`. FastAPI still ignores `app.harness`.
  `fly.toml [env]` has no secrets.
- DB-backed: today's harness spend at the cap refuses a new session
  (`turn_index=0`) before the LLM call, mints nothing, writes no
  debit; yesterday's harness spend does not; `notes=None` and a
  LIKE-lookalike `harness-session-turn extra` do not count; a sibling
  with the real prefix plus the rate-fallback suffix does; unfunded
  still hits the daily cap; pot check and `tokens_used > 0` debit stay.

## Verification

- `ruff check .` clean.
- Default pytest (no `TEST_DATABASE_URL`, no `OPENROUTER_API_KEY`):
  **828 passed, 251 skipped**. +3 vs shipped `0.45.0` (825) —
  daily-cap resolve / UTC day start / literal LIKE prefix.
  +5 skipped (ledger suite).
- Ledger suite skips without `TEST_DATABASE_URL` (CI Postgres runs
  it). Lean / Mathlib stay off. Frontend untouched.

## Unverified

- A live OpenRouter call with a real key in this environment.
- A full `dsh` session against the session-owned HTTP child.
- Fly enablement of the harness child.
