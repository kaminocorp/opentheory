# 0.51.0 — Harness pot-room reservation

**Goal.** Close the leftover 0.50.0 pot race: the daily-cap hold
(0.47/0.48) reserves remaining *daily* tokens under the project-row
`FOR UPDATE`, but the pot was not reserved, so two concurrent
harness turns on a tightly funded project could each be clamped to
the full pot room and together spend past available. Do not light
`AGENT_LOOP_ENABLED`. Do not enable the gateway or MCP child on Fly.
**No schema, no migration.** Sits on shipped `0.50.0` (`af7ee43`,
#44).

**Shape.** When pot room is applied (funded + known price), the
existing amount-0 hold also carries `pot_hold=<usd>` — the clamp's
dollar value at the clamp rate. A concurrent authorize subtracts
unpaired open pot holds inside the lock. Occupancy is the clamp so
that second authorize can reach pot math when pot is the bottleneck.

## Why this shape

- **(a) `pot_hold=<usd>` on the existing hold**, not a second
  append-only scheme. The 0.48 `hold_id` pairing, TTL orphan
  release, `classify_harness_row`, ops hold parse, and frontend
  already walk these notes. A new mark is ignored by old parsers.
  Putting dollars on `amount` would look like a pot debit (amount
  stays `0`). A second row would double the pairing surface. A
  table is a schema change.
- Occupancy becomes the clamp. 0.50 held the full daily remainder
  so two overlapping authorizes could not both pass — that also
  hid the pot race by serializing every turn. With pot reserved,
  holding the granted room is honest: daily-tight turns still
  occupy remaining daily tokens (0.47/0.48 intact); pot-tight
  turns leave daily room and the second authorize sees
  `available − open pot holds`.
- Funding / Overview `available` must not silently change meaning.
  Open-turn reservations are a separate ops figure.

## What shipped

- **Reservation.** `hold_notes(hold_id, pot_hold=)` writes
  `pot_hold=<usd>` only when pot room was applied. Shared math in
  `app.services.harness_meter` (`parse_pot_hold`, `pot_hold_usd`,
  `open_pot_holds`, `pot_available_after_holds`). FastAPI still
  does not import `app.harness`.
- **Authorize.** After stale-hold release, pot room is
  `pot_tokens_from_available(available − open pot holds, clamp
  rate)`. Floor refuse writes nothing. Hold `tokens_used` is the
  clamp.
- **Free.** Convert / release / TTL-expired orphan unpairs the
  hold and frees its pot reservation. Legacy rows without the mark
  reserve `0` and still pair.
- **Ops.** `reserved_by_open_turns` on the Overview bay. Per-hold
  `pot_hold` when present. `snapshot.available` unchanged.

## What did not change

- `create_checkpoint` remains the only Checkpoint writer.
- Append-only guards. Account ≠ Actor. Funder ≠ contributor ≠ validator.
- Unfunded ≠ exhausted. Debit only when `tokens_used > 0`.
  Hold/release amount `0` with the literal notes prefix and
  `hold_id`.
- `AGENT_LOOP_ENABLED` default `false`. Fly `[env]` still has no
  secrets. The gateway / MCP child is **not** enabled on Fly.
- No Alembic revision. No campaign table. No sixth tab.

## Tests

- DB-free: `pot_hold` parse / format; open unmatched holds sum;
  legacy without the mark reserves nothing and still pairs;
  `available − reserved` floors at 0; existing clamp / spend-note
  / pair_holds tests.
- DB-gated: two overlapping authorizes on a tight funded pot
  cannot together be clamped past available (second refuses below
  floor); remaining unreserved pot room; below-floor remainder
  writes no hold; release / convert frees the reservation;
  TTL-expired orphan frees it; legacy hold without the mark still
  pair / release and does not reserve; unfunded and price-unknown
  unchanged; existing 0.47 race, 0.48 TTL, and 0.50 clamp tests.
- Frontend: last-turn honesty unchanged; hold fixture accepts
  `pot_hold: null`.

## Verification

- `ruff check .` clean.
- Default pytest (no `TEST_DATABASE_URL`, no `OPENROUTER_API_KEY`):
  **850 passed, 275 skipped**. +1 passed vs shipped `0.50.0` (849)
  (pot-hold parse / pair / leftover-zero). +5 skipped (overlapping
  pot race, remainder / floor, release/convert, TTL, legacy).
- Harness pytest: **91 passed, 40 skipped** without Postgres.
- Frontend: typecheck / lint / build clean. **64** node:test cases.
- Ledger suite skips without `TEST_DATABASE_URL` (CI Postgres runs
  it). Lean / Mathlib stay off.

## Unverified

- A live OpenRouter call with a real key in this environment.
- A full `dsh` session against the session-owned HTTP child.
- Fly enablement of the harness child.
- Pixel-level browser walk of the new Open turns figure.

## Follow-ups (documented, not this slice)

- Debit still uses a separate `quote_model_price` at
  `record_compute_debit` time; authorize and debit can see
  different quotes.
- Cached OpenRouter quotes can go stale inside the process TTL.
- Spend-notes prefix stays the literal `harness_session_turn`
  string; a structured notes type is later.
- Prompt cost is still not reserved.
