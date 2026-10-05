# 0.48.0 — Harness daily-cap orphan-hold release

**Goal.** Close the leftover 0.47.0 crash pin: a remaining-room hold
taken by `HarnessSession.authorize()` whose convert never ran occupied
the project's daily room until UTC midnight, even though no tokens
moved. A later authorize must be able to proceed after a chosen
recovery, without letting two live concurrent turns both debit past
`OPENTHEORY_HARNESS_DAILY_TOKEN_CAP`. Do not light
`AGENT_LOOP_ENABLED`. Prefer the existing ledger over a new table.
Default CI stays green without `OPENROUTER_API_KEY` or a live network.

**Shape.** Same project-row `FOR UPDATE` as 0.47.0. Hold notes now
carry a `hold_id`. The next `authorize()` appends a matching
`daily_cap_release` for an unmatched hold older than
`OPENTHEORY_HARNESS_HOLD_TTL_SECONDS` (default 300) and only then
takes a new hold. Amount stays `0`. Release is a new credit row —
never an edit. **No schema, no migration, no campaign table.** Sits
on shipped `0.47.0` (`b92c5b2`, #40). Closes the caveat in
`docs/completions/harness-daily-cap-race-0.47.0.md`.

## Why this shape

- A process-shutdown / session-end release does not fire on a crash,
  which is the leftover. It is not sufficient.
- A sweeper table is a new primitive. The existing `ComputeDebit`
  ledger already carries the hold and can carry the `hold_id`.
- TTL without a `hold_id` would guess which hold to release. Notes
  already accept a suffix (`record_compute_debit` already appends a
  rate-fallback suffix). `hold_id=<uuid>` lets a later authorize
  release only that orphan. A fresh unmatched hold stays so the
  0.47.0 overlapping-authorize close still holds.

## What shipped

- **Identified remaining-room hold.** `authorize()` still locks the
  project row and appends `harness_session_turn; daily_cap_hold;
  hold_id=<uuid>` with `tokens_used = cap − used` and amount `0`.
  Convert / `release_hold` append
  `harness_session_turn; daily_cap_release; hold_id=<uuid>`.
- **Stale-hold recovery on the next authorize.** Under that same
  lock, unmatched holds older than the TTL are released, today's sum
  is re-read, and a new hold is taken only if room remains. A second
  concurrent authorize still sees the fresh hold and is
  `TurnRefused` (`daily token cap exhausted`). 422, `tokens_used` 0,
  minted false, no OpenRouter call.
- **No double release.** Convert and `release_hold` take the project
  row and skip a `hold_id` that already has a release credit.
- **The ledger is still the meter.** Today's sum is still Σ
  `ComputeDebit.tokens_used` whose notes start with the literal
  `harness_session_turn` prefix (`startswith(..., autoescape=True)`).
  Pre-0.48.0 leftover holds without an id pair FIFO against id-less
  releases.
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
  finish over the cap (the check is before the model, as in 0.46.0 /
  0.47.0).
- A model call that lasts longer than the TTL can be treated as an
  orphan by a later authorize. Default 300s is longer than a
  planning completion; the operator can raise
  `OPENTHEORY_HARNESS_HOLD_TTL_SECONDS`. Fail-closed for those
  seconds, not the rest of the UTC day.
- The unmetered probe (`OPENTHEORY_HARNESS_UNMETERED_PROBE`) is still
  unmetered. `verify()` will not accept it as the campaign composition.
- Ops dashboard / Fly enablement / lighting the built-in planner
  remain later.

## Tests

- Orphaned hold (authorize without convert, or a backdated leftover
  row) does not permanently pin the day: a later authorize proceeds
  after TTL recovery. Two overlapping authorizes after that recovery
  still: exactly one hold lands; the second is `TurnRefused`; after
  convert, today's harness sum is one turn.
- A fresh unmatched hold still refuses a second authorize (0.47.0
  race close stays).
- Existing daily-cap tests stay, including
  `test_daily_cap_notes_prefix_is_literal` and the overlapping
  authorize / HTTP race. Hold / release notes with `hold_id` start
  with the literal `harness_session_turn` prefix and are not billed
  spend.
- Gateway version is `0.48.0`. FastAPI still ignores `app.harness`.
  `fly.toml [env]` has no secrets.

## Verification

Filled after the harness pytest / ruff run on this branch.

## Unverified

- A live OpenRouter call with a real key in this environment.
- A full `dsh` session against the session-owned HTTP child.
- Fly enablement of the harness child.
- A model call that actually exceeds the default 300s TTL.
