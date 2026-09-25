# 0.22.0 — Thin multi-thread orchestrator

**Goal.** Humans set the research question, the agent roster, and a project
budget — then leave. One pass on one thread is no longer enough. A project-level
loop allocates that budget across bounded `run_agent_pass` calls on multiple
open threads / branches, using the 0.20.0 plan → observe → replan loop inside
each pass and the 0.19.0 `ComputeDebit` ceiling as the shared pot.

**Shape.** Additive mutable trace + thin service + three routes + a quiet
Overview control. Migration `0017_orchestration_runs`. No microservice. Sits
on shipped `0.21.0` research-git merge / tag.

## What shipped

- `OrchestrationRun` — mutable project-level trace (not append-only, not a
  ledger primitive). Records per-thread decisions, stop reason, pass counts,
  and budget remainder. One in-flight row per project (`409` if a second
  commission races it).
- `services/orchestration.py` — classifies every thread (open + raisable
  claims; skip closed / empty / settled / in-flight), then commissions
  sequential `start_agent_pass` → `run_agent_pass` calls until the pot is
  empty, no raisable work remains, or `orchestration_max_passes` (default 4)
  is hit.
- Routes behind the **same** `AGENT_LOOP_ENABLED` dark-launch gate as agent
  runs (`POST /projects/{id}/orchestrations` → `202`, list + poll). No second
  flag.
- Contributor infrastructure only: the loop never writes `Validation` or
  `FundingAllocation`. A failed sub-pass is a decision row; the next eligible
  thread is still considered; earlier checkpoints stand.
- Frontend: quiet **Run research** bay on Overview, next to the budget.

## What did not change

- Per-pass safety caps and the 0.19.0 project ceiling still bind each
  sub-pass. The orchestrator does not invent a per-thread budget.
- Human review stays opt-in (`0.17.0`).
- `0.21.0` merge / tag are shipped human/API operations. `after_pass_hook`
  is reserved and unused — this loop does not auto-merge or auto-tag.

## Tests

- DB-free: raisable-headline helper; migration `0017` revision linkage,
  single-head, model/migration column agreement, enum labels; dark-launch
  `404` / auth `401` on the new routes.
- DB-gated (skip without `TEST_DATABASE_URL`): empty/no-work exits cleanly;
  threads without claims or closed threads are skipped; two threads each get
  a pass; a pot that covers one debit commissions the first thread and skips
  the rest (`budget_exhausted`); a failed sub-pass does not mint a
  `Validation` or a `FundingAllocation` and does not block the next thread;
  `max_passes` skips the remainder; API round-trip + in-flight `409`.

## Unverified

- No live orchestration against OpenRouter. The loop is still dark in
  production until the ops flip.
- No pixel-level browser walk of the Overview control.
- Concurrent *sub-passes* are not implemented (sequential by design). Two
  overlapping orchestrations are rejected at commission.
