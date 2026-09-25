# 0.25.0 — Continuous research under budget

**Goal.** Humans set the research question, the agent roster, and a project
budget — then leave. `0.22.0` already runs a multi-thread orchestrator for one
click. This release makes research **continue** until the project pot is empty
or no raisable work remains, without requiring another human click each cycle.

**Shape.** Additive mutable campaign row + thin service that *reuses* the
shipped orchestrator + four routes + a quiet Overview Start / Stop. Migration
`0018_research_campaigns`. No microservice. No second agent stack. Sits on
shipped `0.24.0` CommandRail.

## What shipped

- `ResearchCampaign` — mutable project-level continuous-run trace (not
  append-only, not a ledger primitive). Records per-cycle orchestrations, stop
  reason, cycle counts, and budget remainder. One in-flight campaign per
  project (`409` if a second commission races it, or if a standalone
  orchestration is already running).
- `services/campaigns.py` — repeatedly commissions
  `start_orchestration` → `run_orchestration` until budget / no-work /
  `campaign_max_cycles` (default 8) / cancel / `campaign_error_budget`
  (default 3). An inner `max_passes` stop is *not* a campaign stop — the next
  cycle re-classifies remaining raisable threads.
- Routes behind the **same** `AGENT_LOOP_ENABLED` dark-launch gate as agent
  runs and orchestrations (`POST /projects/{id}/campaigns` → `202`, cancel,
  list + poll). No second flag. Safety caps are `CAMPAIGN_MAX_CYCLES` /
  `CAMPAIGN_ERROR_BUDGET`.
- Contributor infrastructure only: the loop never writes `Validation` or
  `FundingAllocation`, and it never calls merge / tag. A failed cycle is a
  cycle row; the next cycle still runs unless the error budget is exhausted.
- Frontend: quiet **Start** / **Stop** on Overview. Polls cycle N, budget
  remaining, and the last stop reason. Feature-detected via the same 404 as a
  single pass.

## What did not change

- The 0.22.0 orchestrator, `run_agent_pass`, and 0.19.0 `ComputeDebit`
  metering. Campaigns compose them.
- Human review stays opt-in (`0.17.0`).
- `0.21.0` merge / tag stay human/API. No auto-merge hook was wired.
- Lean / Mathlib: `0.23.0` is untouched. No Mathlib expansion.

## Tests

- DB-free: `resolve_max_cycles` clamp; migration `0018` revision linkage,
  single-head, model/migration column agreement, enum labels; dark-launch
  `404` / auth `401` on the new routes (including cancel).
- DB-gated (skip without `TEST_DATABASE_URL`): empty/no-work exits cleanly;
  unfunded work stops on budget; two cycles continue after an inner
  `max_passes`; a pot that covers one debit stops the campaign after that
  cycle; cancel before the first cycle commissions nothing; cancel mid-cycle
  honours the flag before the next cycle; two consecutive exploding cycles
  trip the error budget; the campaign writes neither `Validation` nor a
  `FundingAllocation`; a running campaign `409`s a standalone orchestration;
  API round-trip + in-flight `409`.

## Verification

Recorded in the changelog after the local ruff / pytest / frontend run.

## Unverified

- No live campaign against OpenRouter. The loop is still dark in production
  until the ops flip.
- No pixel-level browser walk of the Overview control (no signed-in browser
  session against a live backend in this environment).
- Process restart does **not** resume an in-flight BackgroundTask. The
  persisted row is swept to `failed` once stale so the UI does not lie. A
  member Starts again.
- Concurrent cycles are not implemented (sequential by design).
