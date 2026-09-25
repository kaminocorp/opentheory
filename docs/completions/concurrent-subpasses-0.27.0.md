# 0.27.0 — Concurrent sub-passes under project budget

**Goal.** Humans set the research question, the agent roster, and a project
budget. Agents should explore multiple open threads at once without
double-spending that pot or conflating funder ≠ contributor ≠ validator.

**Shape.** The shipped `0.22.0` orchestrator (and therefore each `0.25.0`
campaign cycle) runs a small number of `run_agent_pass` calls concurrently.
Budget stays authoritative: a short critical section reserves a slice of
`available` before a pass starts; the debit is still recorded after tokens.
Migration `0019_concurrent_subpasses` (additive). No Mathlib expansion.

## What shipped

- **Bounded concurrency.** `orchestration_concurrency` (default 2, hard-capped
  at 8). `1` is the sequential fallback — same session, one pass at a time.
  The bound is copied onto `OrchestrationRun.concurrency` at commission.
- **Reservation hold.** Before a pass starts, the loop locks the `Project` row
  and writes `AgentRun.reserved_amount` = min(safety-cap cost of
  `agent_pass_max_tokens`, live `available`). `project_budget.available` =
  funded − spent − reserved. A second pass that would oversell is skipped or
  waits for the next wave. The hold is released when the `ComputeDebit` is
  recorded (or the pass finalizes without spending). Debits stay append-only.
- **Waves.** Eligible threads are commissioned in waves of size `concurrency`.
  After a wave, unused reservation returns to the pot and the next wave may
  proceed. `concurrency=1` is one thread per wave.
- **Trace.** Each decision records `wave` and `parallel_with`. Stop reasons
  include `cancelled` (honoured between waves; in-flight passes finish).
  Campaign Stop also flags the current orchestration so a cycle can stop
  between waves rather than finishing the whole scan.
- **Same dark-launch gate.** `AGENT_LOOP_ENABLED`. No second flag.
- **Contributor only.** The loop never writes `Validation` or
  `FundingAllocation`. `after_pass_hook` stays unused. Merge / tag stay
  human/API (`0.21.0`).
- **Frontend.** Overview Run research shows "N at a time", marks parallel
  decisions, and offers Stop.

## What did not change

- Per-pass safety caps and the 0.19.0 debit-after-tokens ledger.
- Campaigns still ran one orchestration per cycle here. Concurrent *cycles*
  shipped later as `0.32.0`.
- A single planning call can still bill more than a tiny remaining pot — the
  same 0.19.0 first-call overshoot. Concurrent *starts* cannot both take the
  last dollar.

## Tests

- DB-free: `resolve_concurrency` clamp; `pass_reserve_amount`; migration
  `0019` revision linkage, single-head, model/migration column agreement;
  dark-launch `404` on the new cancel route.
- DB-gated: two threads overlap in one wave and the trace names the peer;
  `concurrency=1` does not overlap; a pot that covers one envelope
  commissions the first thread and skips the rest; two sessions racing the
  last dollar produce one hold and non-negative `available`; cancel after the
  current wave skips the remainder; existing empty/no-work, failed-sub-pass
  ledger purity, and max-passes tests still hold.

## Verification

- `ruff check .` clean.
- Default pytest (no `TEST_DATABASE_URL`): **480 passed, 191 skipped**.
- With `TEST_DATABASE_URL` at a local throwaway Postgres: focused
  `tests/agent/test_orchestration*.py` + campaigns + budget metering
  **44 passed**, including parallel-wave overlap, sequential fallback,
  two-session reserve race (one winner, `available >= 0`), cancel after
  the current wave, budget-stop, failed-sub-pass ledger purity, and
  dark-launch `404`.
- Frontend `typecheck` / `lint` / `build` clean.

## Unverified

- No live orchestration against OpenRouter.
- No pixel-level browser walk of the Overview control (no signed-in
  browser session against a live backend in this environment).
