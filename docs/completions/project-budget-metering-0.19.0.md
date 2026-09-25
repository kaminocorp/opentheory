# 0.19.0 — Project-budget metering for agent passes

**Goal.** Budget is real accounting. Humans configure the research question, the agent
roster, and a project compute ceiling; agent passes debit that ceiling from recorded
`AgentRun.tokens_used`. An exhausted project refuses to start / stops mid-pass with a
trace. Historically sketched as deferred `0.12.5`; shipped as **`0.19.0`**.

**Shape.** Additive ledger + service enforcement + funding/overview read-model honesty.
Migration `0015_compute_debits`. No new HTTP endpoint. Per-pass safety caps unchanged.
Prod enablement remains the ops flip `AGENT_LOOP_ENABLED` + `OPENROUTER_API_KEY` — out
of scope here.

## What shipped

- `ComputeDebit` — append-only project spend. **Not** a `FundingAllocation`: the agent
  is a contributor, never a funder. One row per pass (partial unique on `agent_run_id`).
  Amount is `tokens × rate / 1000` at Numeric(12, 6); the rate is snapshotted.
- `project_budget.spent` = Σ those rows; `available = funded − spent`. Decision #6 closed.
- `run_agent_pass` refuses when `available <= 0` (`failed`, `error="project budget
  exhausted"`, mints nothing). After planning, a debit is recorded even if the planner
  then fails (the provider billed it). Remaining instrument runs skip with
  `reason=budget_exhausted`; no branch is forked if nothing can land.
- `BudgetPolicy` seam keeps its signature. Default is the project ceiling
  (`ProjectBudgetPolicy`); an injected policy still replaces it (future orchestrator
  slices). **No per-thread limit.**
- Funding panel and Overview tab show funded / spent / available as live numbers.

## What did not change

- Per-pass `agent_pass_max_runs` / recorded `agent_pass_max_tokens` still bound blast
  radius independently of the project pot.
- Funder ≠ contributor ≠ validator. A pass never writes `FundingAllocation`, never
  records `fund`, never auto-validates.
- The checkpoint chokepoint. Debits are accounting rows, not research checkpoints.
- Dark launch. Phil still lights `AGENT_LOOP_ENABLED`.

## Tests

- DB-free: `tokens_to_cost` / rate fallback / `ProjectBudgetPolicy`; migration `0015`
  revision linkage, single-head, model/migration column agreement, enum labels.
- DB-gated (skips without `TEST_DATABASE_URL`): available drops after a pass by the
  metered amount and the funding + overview read models match; exhausted budget refuses
  to start (planner never called, no debit, no tool_run, no extra checkpoint); mid-pass
  skip when planning tokens consume the remainder (skipped steps, no branch, spend
  recorded); agent never funds or validates; `ComputeDebit` append-only; debit
  idempotent on the same `agent_run_id`.
- Existing orchestrator / API happy paths grant settled native budget so the new
  ceiling does not fail them (unfunded `available` is `0`).

## Unverified

- No live agent pass was run. The loop is still dark in production until the ops flip.
- No pixel-level browser walk of the funding / overview numbers (typecheck / lint /
  build are the frontend gate).
- Concurrent passes on the same project can each see `available > 0` before planning
  and overshoot on the planning call (the spend already happened at the provider). Each
  debit is recorded honestly; the instrument loop then stops. Same class of race as the
  known concurrent-first-pass branch fork.
- Full DB-gated suite: **520 passed, 7 failed**. The 7 failures are pre-existing
  toolbench write-path tests this line did not touch (`Stub("calc.eval")` vs the
  sandbox; geometry `*_latex` assertion). Focused metering / orchestrator / funding
  run: **43 passed**. Default suite (no `TEST_DATABASE_URL`): **389 passed, 138 skipped**.
