# 0.32.0 — Concurrent campaign cycles under project budget

**Goal.** Humans set the research question, the agent roster, and a project
budget. A continuous campaign should be able to keep more than one
orchestration in flight at once against that pot — without overselling,
without a second dark-launch flag, and without conflating funder ≠
contributor ≠ validator.

**Shape.** The shipped `0.25.0` campaign (and therefore the `0.22.0` /
`0.27.0` orchestrator it already composes) may run a bounded number of
cycles concurrently. Budget stays authoritative: cycle starts serialize
on the same project-row reservation lock `0.27.0` introduced; debit stays
after tokens at the `0.28.0` live/fallback quote. Migration
`0021_concurrent_campaign_cycles` (additive). No microservice. No second
agent stack. Sits on shipped `0.31.0`.

## What shipped

- **Bounded cycle concurrency.** `campaign_cycle_concurrency` (default 1,
  hard-capped at 4). `1` is today's sequential campaign — same session,
  one orchestration at a time. The bound is copied onto
  `ResearchCampaign.concurrency` at commission.
- **Waves.** Eligible leftover work is commissioned in waves of size
  `min(concurrency, remaining cycle budget, ceil(eligible threads /
  orchestration_max_passes))`. A second cycle starts only when one
  orchestration's pass cap would otherwise leave threads waiting. After
  a wave, unused reservation returns to the pot and the next wave may
  proceed.
- **Reservation hold reused.** Concurrent cycle starts cannot both take
  the last dollar. A peer cycle that finds a thread already running
  skips it (`pass_in_flight`) and tries the next; an empty pot aborts
  that cycle's remaining commissions. Live OpenRouter quotes stay the
  source for hold + debit.
- **One campaign per project.** A second campaign is still `409`.
  Concurrency is *inside* a campaign. A standalone orchestration is
  still `409` while any campaign (or orchestration) is running.
- **Trace.** Each cycle records `wave` and `parallel_with`. Stop reasons
  include `cancelled` (honoured between waves; in-flight orchestrations
  are flagged so they can stop between their own pass-waves).
- **Same dark-launch gate.** `AGENT_LOOP_ENABLED`. No second flag.
  Safety caps remain `CAMPAIGN_MAX_CYCLES` / `CAMPAIGN_CYCLE_CONCURRENCY`
  / `CAMPAIGN_ERROR_BUDGET`.
- **Contributor only.** The loop never writes `Validation` or
  `FundingAllocation`. Merge / tag stay human/API (`0.21.0`).
- **Frontend.** Overview Start / Stop shows "N cycles at a time" when
  the bound is above 1, marks parallel cycle rows, and stays honest
  about Stop.

## What did not change

- Per-pass safety caps, `0.27.0` sub-pass waves, and the `0.19.0` /
  `0.28.0` debit-after-tokens ledger.
- Human review stays opt-in (`0.17.0`).
- Lean / Mathlib: `0.26.0` is untouched.

## Tests

- DB-free: `resolve_cycle_concurrency` clamp; migration `0021` revision
  linkage (`down_revision = 0020_compute_debit_live_rates`), single-head,
  model/migration column agreement.
- DB-gated (skip without `TEST_DATABASE_URL`): `concurrency=1` does not
  overlap and writes empty `parallel_with`; two leftover-work cycles
  overlap in one wave and the trace names the peer; a pot that covers
  one envelope commissions one pass and keeps `available >= 0`; cancel
  mid-wave flags every in-flight orchestration and does not start the
  next wave; existing empty/no-work, budget-stop, cancel-before,
  error-budget, ledger-purity, and in-flight `409` tests still hold.

## Verification

Filled in after the test run for this release.

## Unverified

- No live campaign against OpenRouter. The loop is still dark in
  production until the ops flip.
- No pixel-level browser walk of the Overview control (no signed-in
  browser session against a live backend in this environment).
- Process restart does **not** resume an in-flight BackgroundTask. The
  persisted row is swept to `failed` once stale so the UI does not lie.
- A single planning call can still bill more than a tiny remaining pot —
  the same 0.19.0 first-call overshoot. Concurrent *starts* cannot both
  take the last dollar.

## Honest caveats

- Default `campaign_cycle_concurrency=1` is sequential on purpose.
  Raising it is an ops knob, not a second dark-launch flag.
- Two cycles that start in the same wave classify independently; thread
  partitioning is the existing `pass_in_flight` skip plus the
  project-row lock, not a pre-assigned split.
- `no_open_work` on one peer in a wave is not a campaign stop when
  another peer hit `max_passes` — leftover work still gets a next wave.
  A full scan (commissioned passes, then `no_open_work`) still stops the
  campaign, matching `0.25.0` sequential semantics.
