# `0.12.4` — Thin Agent Loop Phase 6: The frontend (trigger · trace · review)

> **Status — completed (2026-07-06).** Phase 6 of
> [`docs/executing/thin-agent-loop-0.12-implementation-plan.md`](../executing/thin-agent-loop-0.12-implementation-plan.md),
> and the **last** phase of the `0.12.x` line. (Phase 5 — project-budget metering — is an independent
> stretch, deferred; the per-pass safety caps already bound blast radius.) The `0.12.0`–`0.12.3`
> service + API are now drivable from the workspace, in Kamino tone. **Next:** the `0.12.x` line is
> done — repoint at Tier-1 retrieval / Z3 (`docs/plans/roadmap-next-steps.md`).

## What this phase delivered

| Deliverable | State |
|---|---|
| `types/agent-run.ts` — `AgentRunStatus` / `AgentRunStep` / `AgentRunSummary` / `AgentRunRead` / `AgentRunTrigger` | Shipped |
| `lib/api.ts` — `triggerAgentPass` / `listAgentRuns` / `getAgentRun` + `isAgentLoopDisabled` (404 feature-detect) | Shipped |
| `lib/query-keys.ts` — `agentRuns` / `agentRun` | Shipped |
| `components/workspace/agent-pass/agent-pass-panel.tsx` — the trigger + history | Shipped |
| `components/workspace/agent-pass/agent-run-trace.tsx` — the polled trace + `AgentRunStatusPill` | Shipped |
| `project-workspace.tsx` — `AgentPassPanel` rendered after the toolbench | Shipped |
| Docs — `changelog.md` (`0.12.4`), `roadmap-next-steps.md` repointed | Shipped |

Frontend-only — no backend, schema, or migration. All types mirror the `0.12.0`/`0.12.3` read
schemas; no new API shape was invented.

## The surface in one paragraph

A member opens a thread and sees an **Agent pass · Research crew** Bay. A role picker (each role's
assigned model shown inline) plus a **Run agent pass** control commissions the pass (`POST` → `202`);
the returned `running` trace is cached and rendered immediately. The trace polls `GET /agent-runs/{id}`
every 2s **while running** and stops the instant it settles, showing the plan step-by-step — landed
steps with the toolbench's honest outcome pill + a checkpoint link, failed steps with their error,
dropped/skipped steps as faint notes — plus `runs` and `tokens` readouts. When a completed pass
landed on an agent branch, **Review on its line** selects that branch in the branch bar, where the
shipped reject/branch/validate write paths already live.

## Files created / modified

### `types/agent-run.ts` + `lib/api.ts` + `lib/query-keys.ts` — the plumbing

Types mirror the backend `AgentRunSummary` / `AgentRunRead` and the per-step JSON shape documented on
`models/agent_run.py`; the step `status` and `outcome` are kept lenient (`| string`) so a future
status never crashes a trace render. The client adds the three calls and `isAgentLoopDisabled(error)`
— a helper that reads the `request` helper's `Error("404: …")` and answers "the loop is dark for this
deployment," so the UI can **disable** the trigger instead of surfacing a failure.

### `agent-run-trace.tsx` — the polled trace

`useQuery` with `refetchInterval: (q) => q.state.data?.status === "running" ? 2000 : false` — polling
that stops itself. `placeholderData` from the list summary renders status instantly while the full
read loads. A `useRef`-guarded `useEffect` invalidates the checkpoints / overview / branches queries
**only on the `running → terminal` transition**, so landed work appears in the timeline and a freshly
forked agent line appears in the branch bar without a manual refresh. Steps render by kind, reusing
`outcomeMeta` from the toolbench so `refuted` = fail and `undecided` = warn (never a pass) — the same
honesty carried into the agent context.

### `agent-pass-panel.tsx` — the trigger + history

A collapsible Bay (the `ToolbenchPanel` shape). Feature-detects + lists via `listAgentRuns` (enabled
only with a thread selected, `retry: false` so a dark-launch 404 doesn't hammer). The **Run agent
pass** control is `runnable` only when: a member (`canRun`) **and** a thread is selected **and** the
chosen role has a model **and** the loop is live **and** not already pending — each failing condition
maps to a specific gate hint. `activeRunId` resets on a thread change so a stale trace never lingers.

### `project-workspace.tsx` — integration

`AgentPassPanel` renders right after `ToolbenchPanel` (both operate on the selected thread/branch),
receiving `projectId` / `selectedThreadId` / `canRun={canManageProject}` /
`agentModels={project.agent_models}` / `onSelectBranch={setSelectedBranchId}`.

## Three deliberate design decisions (with rationale)

1. **Landed steps reuse the outcome *vocabulary* and link to the checkpoint — they don't re-render
   the full result card.** `ResultView` is tightly coupled to a `ToolRunResult` (it needs
   `checkpoint.tool_invocations`, `artifact_id`, `content_hash`), but an `AgentRun` *step* only
   carries `checkpoint_id` / `evidence_id` / `outcome` / `instrument` / `inputs`. Rather than fetch
   each checkpoint to synthesize a `ToolRunResult`, a landed step shows the honest outcome pill
   (`outcomeMeta(step.outcome)`) + a checkpoint-id chip — and the **full** result card renders one
   glance away in the timeline below (which already lists every checkpoint). This keeps the trace
   legible without a fragile per-step synthesis.

2. **Accept / reject / branch *route to* the shipped write paths — they are not duplicated.** The
   plan's task 3 lists these "in the existing branch bar (reuse shipped write paths)." All three
   already exist: reject = `close_branch(dead_end)` (branch bar), branch further = `create_branch`
   (branch-bar fork), accept = a `Validation` on a claim (`0.4.1`, on the claim panel). So Phase 6's
   only wiring is **making the agent's landed line reachable**: a completed pass offers **Review on
   its line**, which calls `onSelectBranch(branch_id)` — placing the human at the branch bar with the
   agent's line selected, where reject and fork are one click away. Re-implementing a close/fork/
   validate form in the trace would duplicate write logic and drift from the shipped surfaces.

3. **Feature-detect via a 404, disable rather than hide.** The whole surface is dark-launch-gated on
   the backend; `listAgentRuns` 404s while the flag is off. `isAgentLoopDisabled` turns that into a
   quiet "Agent passes are not enabled for this deployment yet" with the trigger disabled — so this
   frontend can ship **ahead** of the backend flag flip without showing a broken button. (When no
   thread is selected yet, the panel shows a neutral "select a thread" prompt; feature detection
   needs a thread to probe, and the flag is on in prod after enablement, so this is a non-issue in
   practice.)

## Verification

```bash
cd frontend && npm run typecheck   # clean
cd frontend && npm run lint        # clean
cd frontend && npm run build       # ✓ compiled; /projects/[projectId] builds (141 kB)
```

All three green this session. The workspace route compiles and prerenders; the panel is additive and
dark-launch-aware, so the existing human toolbench walkthrough is unchanged.

### Manual gate (deferred — needs a live backend with the loop enabled)

The full flagship walkthrough needs a backend with `AGENT_LOOP_ENABLED=true` and the
`OPENROUTER_API_KEY` Fly secret set — prod currently ships the flag **off**, so this could not run
this session. On *measuring across a corner*, confirm end-to-end:

1. Sign in as a member; assign a model to `researcher` (Research crew).
2. Open the thread; **Run agent pass** → `202`, the trace shows `running` then flips to `completed`.
3. A checkpoint lands on the **agent branch** (visible in the timeline), attributed to the agent
   Actor; a second pass reuses the same line.
4. **Review on its line** selects the branch; **Close branch → dead end** (reject) records it.
5. The normal human toolbench walkthrough is unchanged.

## Standing invariants — honoured

- **One write path / append-only:** the frontend mints nothing directly — it commissions a pass
  (which lands through the backend chokepoint) and reuses the shipped branch/validation write paths.
  The `AgentRun` trace it polls is the one deliberately-mutable non-ledger object.
- **Human-first / roles separate:** the trigger is member-gated (the commissioning human is
  accountable); the agent Actor authors the work. The UI adds no funding/validation shortcut that
  would conflate the credit roles.
- **Honesty carried through:** landed-step outcomes reuse the toolbench vocabulary, so `undecided`
  never reads as a pass and `refuted` reads as the definitive finding it is — inside the agent
  context, not just the human one.

## Line housekeeping (follow-up, not done here)

The `0.12.x` line is complete. The plan's task 5 also calls for archiving the plan + proposal
(`docs/executing/thin-agent-loop-0.12*.md` → `docs/archive/`) and moving the five
`docs/completions/thin-agent-loop-phase-*.md` docs to `docs/archive/` alongside them (the pattern the
`0.11.x` line followed). Left for the `review_completions` / archival flow so the completion docs'
`../executing/…` cross-links can be repointed in the same move rather than broken here.
