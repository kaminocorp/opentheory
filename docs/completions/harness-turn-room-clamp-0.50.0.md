# 0.50.0 — Harness turn-room clamp

**Goal.** Close the leftover from `0.46`–`0.48`: a single external-harness
turn can overshoot the remaining room. Today `authorize()` locks the
project row, releases orphan holds, checks today's
`harness_session_turn` sum against `OPENTHEORY_HARNESS_DAILY_TOKEN_CAP`,
and takes a remaining-room hold — but the OpenRouter call can then
consume more tokens than the daily remainder and/or more than the pot
can pay. Do not light `AGENT_LOOP_ENABLED`. Do not enable the gateway
or MCP child on Fly. **No schema, no migration.** Sits on shipped
`0.49.1` (`f2362b1`, #43).

**Shape.** Compute the room at authorize. Carry it on the hold. Clamp
the gateway `max_tokens`. Refuse below a floor instead of sending a
request that cannot complete honestly. Record provider overshoot as
truth. Price unknown → daily room only.

## Why this shape

- The 0.47/0.48 hold occupies remaining *daily* tokens so two
  overlapping authorizes cannot both pass. Changing that hold to the
  smaller pot room would reopen the daily-cap race when pot is the
  bottleneck. The ledger hold stays the daily remainder (amount `0`).
  The clamp is a second number on the same authorization.
- `max_tokens` is the provider's completion bound, not a total-token
  guarantee. Prompt tokens can still push usage over the clamp. The
  ledger records the real usage and flags the overshoot rather than
  hiding it.
- A blended `agent_token_rate_usd_per_1k` is an invented price. Pot
  tokens are computed only from a live OpenRouter quote or a catalog
  `usd_per_1k`, at the completion rate (or `max(prompt, completion)`).
  The live mean overstates room because `max_tokens` is a completion
  bound billed ~4× prompt on DeepSeek. Prompt cost is not reserved.
  Unfunded is not a pot (`pot_room=none`).

## What shipped

- **Clamp.** `min(daily room, pot room)` when pot room was applied
  (funded + known live/catalog price, converted at the completion
  rate or `max(prompt, completion)`). Daily room when unfunded or
  price unknown. Shared math in `app.services.harness_meter`
  (`turn_clamp`, `clamp_rate_per_1k`, `pot_tokens_from_available`,
  `price_is_known`, `clamp_max_tokens`, spend-note parse including
  `pot_room=N|none`). FastAPI still does not import `app.harness`.
- **Floor.** `OPENTHEORY_HARNESS_TURN_TOKEN_FLOOR` (default **16**).
  Below it: `TurnRefused` → 422, `tokens_used` 0, minted false, no
  provider call, no debit, no hold.
- **Gateway.** Model is resolved once for `authorize` and `complete`.
  A caller-smaller `max_tokens` is kept. Invalid `max_tokens` (0,
  negative, non-int) is 422, not "no request".
- **Overshoot.** Spend notes `harness_session_turn; clamp=N` plus
  `pot_room=N|none`, plus `overshoot=M` when the provider reports
  more, plus `price_unknown` when the price was not known. Gateway /
  `SupervisedTurn` surface the same numbers. Overview last-turn
  readout is read-only, no sixth tab; it does not say "min of daily
  room and pot room" when `pot_room=none`.
- **Race / TTL unchanged.** `FOR UPDATE` + remaining-daily hold +
  `hold_id` stale release stay. Concurrent authorize and orphan TTL
  tests still pass.

## What did not change

- `create_checkpoint` remains the only Checkpoint writer.
- Append-only guards. Account ≠ Actor. Funder ≠ contributor ≠ validator.
- Unfunded ≠ exhausted. Debit only when `tokens_used > 0`. Hold/release
  amount `0` with the literal notes prefix.
- `AGENT_LOOP_ENABLED` default `false`. Fly `[env]` still has no
  secrets. The gateway / MCP child is **not** enabled on Fly.
- No Alembic revision. No campaign table. No sixth tab.

## Tests

- DB-free: clamp = min(daily, pot); clamp = daily when pot unknown;
  blended fallback is not a known price; pot clamp rate prefers
  completion / max(prompt, completion); floor peek invalid is
  unknown; spend-note parse including `pot_room=none`; invalid
  `max_tokens` 422; omitted model uses the resolved default;
  gateway version `0.50.0`; FastAPI still does not import
  `app.harness`.
- DB-gated: known-price authorize clamp; unknown-price daily-only
  clamp; unfunded + known price → daily room, not refused,
  notes/readout do not claim pot room; completion-rate pot clamp
  (mean would overstate); HTTP keeps a caller-smaller `max_tokens`;
  HTTP `max_tokens` equals pot room when price known; below-floor
  refuse with no provider call and no debit; provider over-report
  recorded and flagged on the ledger row (not a helper-only assert);
  `supervise_turn` sends the clamped `max_tokens` and returns
  `SupervisedTurn.clamp` / `overshoot`; overlapping authorize race;
  orphan TTL release.
- Frontend: last-turn line does not invent a clamp; overshoot is
  labeled.

## Verification

- `ruff check .` clean.
- Default pytest (no `TEST_DATABASE_URL`, no `OPENROUTER_API_KEY`):
  **849 passed, 270 skipped**. +10 passed vs shipped `0.49.1` (839)
  (room math / completion-rate / floor / spend-note parse / invalid
  `max_tokens`). +13 skipped (clamp ledger + review cases).
- With `TEST_DATABASE_URL`: **1115 passed, 4 skipped**.
- Harness pytest: **91 passed, 36 skipped** without Postgres;
  **127 passed** with Postgres (includes overlapping-authorize race
  and orphan TTL).
- Frontend: typecheck / lint / build clean. **64** node:test cases
  (+1 last-turn honesty).
- Ledger suite skips without `TEST_DATABASE_URL` (CI Postgres runs
  it). Lean / Mathlib stay off.

## Unverified

- A live OpenRouter call with a real key in this environment.
- A full `dsh` session against the session-owned HTTP child.
- Fly enablement of the harness child.
- Pixel-level browser walk of the new last-turn line (helpers covered;
  the 0.49.1 Overview walk did not include this field).

## Follow-ups (documented, not this slice)

- Debit still uses a separate `quote_model_price` at `record_compute_debit`
  time; authorize and debit can see different quotes.
- Cached OpenRouter quotes can go stale inside the process TTL.
- Spend-notes prefix stays the literal `harness_session_turn` string;
  a structured notes type is later.
- How often a provider overshoots the clamp is not measured here.

## Correction (0.51.0)

The first 0.51 brief treated a leftover "two concurrent turns can
still both spend a tight pot" as open. That was wrong: this slice
already occupies the whole remaining daily room under the
project-row lock, so a second overlapping authorize is always
refused. There is no pot race. `0.51.0` records that as a
regression guard and closes the real hole (hold TTL must strictly
exceed max turn duration).
