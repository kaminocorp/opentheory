# 0.20.0 — Bounded plan → observe → replan

**Goal.** Replace the thin agent loop's single planning call then deterministic execute
with a bounded **plan → observe → replan** loop inside one agent pass. Humans still only
set the research question, agent roster, and budget. Agents explore / prove / disprove
without a human in the loop; a one-shot plan is too brittle once literature pins, Z3,
and counterexamples exist.

**Shape.** Orchestrator loop + planner context + trace narrative + frontend rows.
**No schema, no migration.** `AgentRun.plan` / `AgentRun.steps` are already mutable JSON.

## Why

`0.12.x` planned once and executed the whole list. After `0.16.x` grounding, `0.17.0`
review-as-opt-in, and `0.18.0` literature pins, a pass can settle a claim, pin a source,
or fail an instrument *mid-pass* — and the rest of a frozen plan would keep spending
against a decided claim or retry a dead approach. The pass has to see what just
happened.

## What landed

- `run_agent_pass` executes the current plan version as a **batch**, records
  `Observation` rows (instrument, honest outcome, minted-or-not, grounding delta),
  then calls the planner again with those observations and a refreshed grounding
  snapshot.
- Caps: `agent_pass_max_replans` (default 2), `agent_pass_max_batch_runs` (default 2),
  existing `agent_pass_max_runs` (now counting **attempts**, so a failure is not free).
  `BudgetPolicy.check` is wired to the shipped `0.19.0` project ceiling
  (`ProjectBudgetPolicy` / `record_compute_debit` / refuse-to-start /
  skip-remaining-on-exhaust; no replan after a budget stop).
  `agent_pass_max_tokens` stays recorded.
- Trace: `plan.versions[]` plus narrative `plan` / `replan` steps with
  `observe_summary`. A max-replan stop is a `skipped` row with `reason=max_replans`.
- Honesty: failed/empty steps mint nothing; a failed step does not fail the pass; a
  replan LLM error after landed work completes the pass. The planner is still held
  to the fixed catalog. Failed-step error text is kept off the prompt.
- Review stays opt-in (`0.17.0`). No new gate.

## Tests

- DB-free: observation rendering; error text never reaches the prompt; observations
  reach `plan()`; system prompt states the batch/replan contract.
- DB-gated (skip without `TEST_DATABASE_URL`): replan after observe; max-replan stop
  with remaining run budget; settled grounding on the next plan; failed first step
  does not poison a later landing; replan LLM failure after a landed step completes.

## What did not change

- Ledger writes still go only through `run_instrument` / `create_checkpoint` /
  `create_branch`.
- Dark launch is still `AGENT_LOOP_ENABLED` + `OPENROUTER_API_KEY`.
- Continuous / scheduled loops and a multi-thread orchestrator are still out of scope.
- Project-budget metering shipped in `0.19.0` and is the default `BudgetPolicy`
  on this loop. One `ComputeDebit` per pass (unique on `agent_run_id`) still
  records the first planning call's tokens; later replan tokens update the
  mutable trace and trip `Policy.check` but do not rewrite the append-only debit.

## Verification

- `ruff check .` clean.
- Default pytest: **386 passed, 137 skipped** (DB-gated).
- With `TEST_DATABASE_URL` at a local throwaway Postgres: `tests/agent/` **76 passed**,
  including replan-after-observe, max-replan stop, settled grounding on the next
  plan, failed-step recovery, and replan-LLM-failure-completes.
- Frontend `typecheck` / `lint` / `build` clean.

## Unverified

- No live agent pass against OpenRouter. The loop is still dark in production
  until the ops flip.
- No pixel-level browser walk of the new plan-version rows.
- No live debit against OpenRouter prices — the blended
  `agent_token_rate_usd_per_1k` default (and catalog override) is still the rate.
