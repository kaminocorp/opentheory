# 0.51.0 — Harness serialization guard

**Goal.** `0.50.0` already serializes harness turns per project via
the whole-daily-room hold, so no pot race exists. Add a regression
guard for that, and make the hold TTL strictly exceed the maximum
turn duration so a live turn can never be released as an orphan.
Do not light `AGENT_LOOP_ENABLED`. Do not enable the gateway or MCP
child on Fly. **No schema, no migration.** Sits on shipped `0.50.0`
(`af7ee43`, #44).

**Shape.** Keep 0.50 occupancy (remaining daily tokens, amount `0`).
Refuse composition / session / gateway start when
`OPENTHEORY_HARNESS_HOLD_TTL_SECONDS` is not strictly greater than
the provider request timeout plus a margin.

## Why this shape

- The 0.47/0.48/0.50 hold occupies the whole remaining daily room
  under the project-row `FOR UPDATE`. A second overlapping authorize
  always sees that sum and is `TurnRefused` for the daily cap.
  Reserving pot dollars, or clamping occupancy to pot room, would
  let a second turn in (top-up mid-flight, or a price-unknown
  authorize that ignores a pot mark) and jointly exceed the daily
  cap by their prompt tokens. Under serialization those marks add
  no guarantee.
- The real hole is TTL: a live turn that outlives
  `OPENTHEORY_HARNESS_HOLD_TTL_SECONDS` (default 300) can have its
  hold released by the next authorize as an orphan. A per-phase
  `httpx.AsyncClient(timeout=60)` is not a bound — connect / write
  / read / pool each get 60s and the read timer resets on every
  chunk, so a trickle or SSE can run well past 60s. `complete()`
  wraps post + body read in a total `asyncio.timeout` of the
  resolved turn timeout (env mapping first, then
  `settings.agent_llm_timeout_s` / `AGENT_LLM_TIMEOUT_S`, default
  60) and uses an explicit `httpx.Timeout`. On deadline the hold
  is released, `tokens_used` is 0, and nothing is debited.
  OpenRouter may still bill a request we abandoned — we cannot see
  usage. Truthy `stream` is 422 before authorize. Fail-closed: TTL
  must be `> timeout + 5s` (default `300 > 65`).

## What shipped

- **Regression.** Postgres: tight funded pot + known price, first
  authorize holds remaining daily tokens; a second overlapping
  authorize is refused (`REASON_DAILY_CAP`) with no provider call,
  no debit, no extra hold. Same for a price-unknown second
  authorize. Same after a mid-flight pot top-up.
- **TTL covers turn.** Shared `hold_ttl_covers_turn` /
  `max_turn_duration_seconds` in `app.services.harness_meter`.
  `assert_composition`, `HarnessSession.__post_init__`,
  `create_gateway_app`, and the campaign / gateway process
  entrypoints refuse when misconfigured. `GatewayClient` and
  `resolve_turn_timeout_seconds` read the same value (env mapping
  first, then settings). `complete()` wraps post + body read in a
  total deadline; on cut-off the hold is released and nothing is
  debited (OpenRouter may still bill). Truthy `stream` is 422
  before authorize. FastAPI still does not import `app.harness`.
- **Occupancy unchanged.** Hold notes stay
  `harness_session_turn; daily_cap_hold; hold_id=<uuid>`. Amount
  `0`. No `pot_hold` mark. No Overview "Open turns" figure.

## What did not change

- `create_checkpoint` remains the only Checkpoint writer.
- Append-only guards. Account ≠ Actor. Funder ≠ contributor ≠ validator.
- Unfunded ≠ exhausted. Debit only when `tokens_used > 0`.
- `AGENT_LOOP_ENABLED` default `false`. Fly `[env]` still has no
  secrets. The gateway / MCP child is **not** enabled on Fly.
- No Alembic revision. No campaign table. No sixth tab.

## Tests

- DB-free: TTL 300 covers 60+5; TTL 65 / timeout 400 refuse;
  composition / session / gateway / campaign entrypoints refuse
  when misconfigured; GatewayClient and resolve_turn_timeout_seconds
  share an env mapping; a trickled body is cut off at the total
  deadline; truthy `stream` is 422 before the provider; FastAPI
  still does not import `app.harness`.
- DB-gated: tight-pot overlapping authorize refused for the
  daily-cap reason (known price, unknown price, mid-flight top-up);
  existing 0.50 clamp / floor / overshoot / race / orphan TTL
  expectations restored (hold occupies remaining daily tokens).

## Verification

- `ruff check .` clean.
- Default pytest (no `TEST_DATABASE_URL`, no `OPENROUTER_API_KEY`):
  **854 passed, 273 skipped**. +5 passed vs shipped `0.50.0` (849)
  (TTL covers turn; shared timeout; total deadline on a trickled
  body; truthy `stream` 422). +3 skipped (tight-pot overlapping
  daily-cap; deadline hold-release; stream-before-authorize; CI
  Postgres runs them).
- Harness pytest: **95 passed, 39 skipped** without Postgres.
- Frontend: typecheck / lint / build clean. **64** node:test cases.
- Ledger suite skips without `TEST_DATABASE_URL` (CI Postgres runs
  it). Lean / Mathlib stay off.

## Unverified

- A live OpenRouter call with a real key in this environment.
- A full `dsh` session against the session-owned HTTP child.
- Fly enablement of the harness child.

## Follow-ups (documented, not this slice)

- Debit still uses a separate `quote_model_price` at
  `record_compute_debit` time; authorize and debit can see
  different quotes.
- Cached OpenRouter quotes can go stale inside the process TTL.
- How often a provider overshoots the clamp is not measured here.
