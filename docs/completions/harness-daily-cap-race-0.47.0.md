# 0.47.0 — Harness daily-cap reservation

**Goal.** Close the leftover 0.46.0 race: `HarnessSession.authorize()`
read today's `ComputeDebit` sum with no row lock, then
`chat_completions` called OpenRouter and `record_spend` inserted in a
later session. Two in-flight turns could both pass `authorize()` and
both debit past `OPENTHEORY_HARNESS_DAILY_TOKEN_CAP`. Refuse the
second concurrent turn (or fail the reservation closed) so that
cannot happen. Do not light `AGENT_LOOP_ENABLED`. Prefer the existing
ledger over a new table. Default CI stays green without
`OPENROUTER_API_KEY` or a live network.

**Shape.** Project-row `FOR UPDATE` plus a remaining-room hold
expressed as a `ComputeDebit` row whose notes start with
`harness_session_turn`. Amount is `0` (not a pot debit). Release is a
new credit row after the model call — never an edit. **No schema, no
migration, no campaign table.** Sits on shipped `0.46.0` (`8ee8ac0`,
#39). Closes the caveat in
`docs/completions/harness-daily-cap-0.46.0.md`.

## What shipped

- **Reservation before the model.** `authorize()` locks the project
  row, re-reads today's harness token sum (holds included), and
  appends `harness_session_turn; daily_cap_hold` with
  `tokens_used = cap − used`. A second concurrent authorize sees
  `used >= cap` and is `TurnRefused` (`daily token cap exhausted`).
  422, `tokens_used` 0, minted false, no OpenRouter call.
- **Convert after the model.** `record_spend` appends
  `harness_session_turn; daily_cap_release` (`tokens_used = −hold`)
  and, when tokens moved, the billed spend through
  `record_compute_debit`. One transaction. A 0-token completion
  releases the hold and writes no spend row.
- **The ledger is still the meter.** Today's sum is still Σ
  `ComputeDebit.tokens_used` whose notes start with the literal
  `harness_session_turn` prefix (UTC midnight inclusive;
  `startswith(..., autoescape=True)`). Hold and release rows match
  that prefix so the second authorize cannot ignore them. A process
  restart does not reset the sum.
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
- Process-local turn index still resets to 0 on restart.
- Default 20_000 / UTC day and `OPENTHEORY_HARNESS_DAILY_TOKEN_CAP`
  override stay.

## Honest caveats

- A green default pytest is not a live OpenRouter / `dsh` session.
- A single turn that burns more than the remaining room can still
  finish over the cap (the check is before the model, as in 0.46.0).
  What this slice closes is *two* overlapping authorizes both
  debiting.
- A crash after `authorize()` and before convert leaves the hold on
  the ledger for the rest of the UTC day (fail-closed). There is no
  sweeper.
- The unmetered probe (`OPENTHEORY_HARNESS_UNMETERED_PROBE`) is still
  unmetered. `verify()` will not accept it as the campaign composition.
- Ops dashboard / Fly enablement / lighting the built-in planner
  remain later.

## Tests

- Overlapping `authorize()`: exactly one hold lands; the second is
  `TurnRefused`; after convert, today's harness sum is one turn.
  Overlapping HTTP completions on the session-owned path: second is
  422 / minted false / `tokens_used` 0; OpenRouter is called once.
- Existing daily-cap tests stay, including
  `test_daily_cap_notes_prefix_is_literal`. Hold / release notes
  start with the literal `harness_session_turn` prefix and are not
  billed spend.
- Gateway version is `0.47.0`. FastAPI still ignores `app.harness`.
  `fly.toml [env]` has no secrets.

## Verification

- `ruff check .` clean.
- Default pytest (no `TEST_DATABASE_URL`, no `OPENROUTER_API_KEY`):
  **828 passed, 252 skipped**. Same passed count as shipped `0.46.0`
  (828). +1 skipped (overlapping-authorize race).
- Ledger suite skips without `TEST_DATABASE_URL` (CI Postgres runs
  it). Lean / Mathlib stay off. Frontend untouched.

## Unverified

- A live OpenRouter call with a real key in this environment.
- A full `dsh` session against the session-owned HTTP child.
- Fly enablement of the harness child.
