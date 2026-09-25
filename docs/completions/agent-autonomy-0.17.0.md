# 0.17.0 — Phase 1 agent autonomy: human review becomes opt-in

**Goal.** Humans only configure the research question, which agents are deployed, and budget.
Agents research autonomously. A successful pass's attributed checkpoints on the agent branch
stand without a mandatory human accept / reject / fork. Those controls remain available as
opt-in audit.

**Shape.** API read-model contract + service documentation + frontend copy/UX. **No schema,
no migration, no new endpoint.** Ledger writes still go only through `create_checkpoint` /
`run_instrument`. Account ≠ Actor; funder ≠ contributor ≠ validator — a completed pass does
**not** auto-validate (that would conflate contributor and validator).

## What changed

- `AgentRunSummary.requires_review` is a **computed** field, always `false`. It cannot be
  forced true from a row or a request body. `AgentRunStatus` stays `{running, completed,
  failed}` — there is no `awaiting_review`.
- `services/agent_runs.requires_review` is the same contract in the service layer.
  `_finalize(..., completed)` is operator-done: the checkpoints already committed through
  the chokepoint stand.
- The agent-pass trace no longer tells the operator they must review. Completed-on-a-branch
  reads *"This pass stands on its line — no review required."* with an **Inspect its line**
  audit link. Accept / reject / fork still live on the shipped branch bar and claim
  validation — they are not duplicated, and they are not a gate.

## What did not change

- Per-pass safety caps (`agent_pass_max_runs`, recorded `agent_pass_max_tokens`) still bound
  blast radius. Full project-budget metering is **`0.12.5`**, not this line.
- Dark launch is still `AGENT_LOOP_ENABLED` (default `false`) + `OPENROUTER_API_KEY` as a
  Fly **secret**. Production enablement is that ops flip — documented in
  `docs/operations/deploy.md`. Do not invent a second key or a second flag.
- Continuous / scheduled loops and a multi-thread orchestrator are still out of scope.

## Tests

- DB-free: completed / failed traces `requires_review is False`; the field cannot be forced
  true; `AgentRunStatus` has no fourth value; the service helper is always `False`.
- DB-gated (skips without `TEST_DATABASE_URL`): the existing commission→poll→land
  round-trip now also asserts the landed checkpoint is already readable and both the poll
  target and the list row carry `requires_review: false`.

## Unverified

- No live agent pass was run. The loop is still dark in production until the ops flip.
- DB-gated tests skip unless `TEST_DATABASE_URL` points at reachable Postgres.
- No pixel-level browser walk of the new copy.
