// Agent-run types (0.12.x), mirroring the backend read schemas (app/schemas/agent_run.py) and the
// per-step JSON shape documented on the model (app/models/agent_run.py). An `AgentRun` is the
// human-visible *trace* of one bounded agent pass: who commissioned it, which role/model ran, the
// validated plan, and the per-step outcome (what landed on the ledger, what failed, what was
// dropped as unrunnable). It is NOT a ledger primitive — it is a live, mutable narrative that flips
// `running` → `completed` | `failed`; the checkpoints/evidence it lands ARE the append-only ledger.

import type { AgentRole } from "./project";
import type { GroundingHeadline, ResultStatus } from "./research";

// The pass lifecycle. `running` is the only non-terminal state (the client polls until it settles).
export type AgentRunStatus = "running" | "completed" | "failed";

// A step's disposition. `landed` minted a checkpoint; `failed` reached the instrument but errored
// (mints nothing — the failure split); `dropped_invalid` never ran (the planner rejected it before
// execution); `skipped` was cut by a budget stop. Kept lenient (`| string`) — a future status must
// never crash a trace render.
export type AgentRunStepStatus = "landed" | "failed" | "dropped_invalid" | "skipped";

// One entry in the `steps` narrative. `outcome` is the instrument's honest ResultStatus on a landed
// step (else null); `reason` carries a drop/skip cause (e.g. `unknown_instrument`, `max_runs`,
// `budget_exhausted`); `error` carries a failed step's message.
export type AgentRunStep = {
  index: number;
  instrument: string;
  inputs: Record<string, unknown>;
  claim_id: string | null;
  relation_kind: string | null;
  rationale: string;
  status: AgentRunStepStatus | string;
  checkpoint_id: string | null;
  evidence_id: string | null;
  outcome: ResultStatus | string | null;
  error: string | null;
  reason: string | null;
};

// What a pass did to one claim's evidence axis (0.16.1). Three-way rather than up/down, because
// `B → refuted` is NOT a regression — a refutation is a successful research outcome — but calling it
// "raised" would be equally wrong. `settled` names the decisive case so both stay honest.
//   settled   — reached proven or refuted from neither; decided, in either direction
//   raised    — the supporting rung strictly strengthened
//   unchanged — neither (a new citation lands here: real, but off-ladder)
export type ClaimMovement = "settled" | "raised" | "unchanged";

// One claim's before/after rung across a pass. Recorded only when the headline actually changed.
export type ClaimYield = {
  claim_id: string;
  before: GroundingHeadline;
  after: GroundingHeadline;
  movement: ClaimMovement;
};

// What a pass *bought*, beside what it spent (0.16.1). `ran_count`/`tokens_used` measure activity;
// this measures result. `measured` is every open claim the pass could have moved, `moved` is how
// many it did. A pass with `ran_count > 0` and `moved === 0` minted checkpoints and climbed nothing
// — the reading this release exists to make impossible to miss.
export type PassYield = {
  measured: number;
  moved: number;
  changed: ClaimYield[];
};

// The list-view row (no heavy JSON). Mirrors the backend AgentRunSummary.
export type AgentRunSummary = {
  id: string;
  project_id: string;
  thread_id: string;
  // The agent line this pass landed on; null = the main-line fallback (thread had no fork point).
  branch_id: string | null;
  agent_actor_id: string | null;
  triggered_by_actor_id: string | null;
  role: string;
  model: string | null;
  status: AgentRunStatus;
  // The model's raw proposal size; `ran_count` is what actually reached an instrument.
  planned_count: number;
  ran_count: number;
  tokens_used: number;
  // The yield measure. Small and bounded, so it rides on the summary too — a history row showing
  // spend without result is exactly the reading 0.16.1 is trying to prevent.
  //
  // `null` means **never measured** — a pass that failed before it could measure, or one recorded
  // before 0.16.1. That is a different statement from a measure of zero, and the surfaces must not
  // collapse the two: "—" for unmeasured, "0/4" for looked-and-found-nothing.
  grounding_yield: PassYield | null;
  error: string | null;
  created_at: string;
  updated_at: string;
};

// The poll target: the summary plus the validated plan and the per-step outcomes.
export type AgentRunRead = AgentRunSummary & {
  plan: Record<string, unknown>;
  steps: AgentRunStep[];
};

// Body for POST /projects/{id}/threads/{thread_id}/agent-runs: which Research-crew role commissions
// the pass. Must be one of the four roles (the backend 422s an unknown role).
export type AgentRunTrigger = {
  role: AgentRole;
};
