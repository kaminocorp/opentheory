// Agent-run types (0.12.x), mirroring the backend read schemas (app/schemas/agent_run.py) and the
// per-step JSON shape documented on the model (app/models/agent_run.py). An `AgentRun` is the
// human-visible *trace* of one bounded agent pass: who commissioned it, which role/model ran, the
// validated plan, and the per-step outcome (what landed on the ledger, what failed, what was
// dropped as unrunnable). It is NOT a ledger primitive — it is a live, mutable narrative that flips
// `running` → `completed` | `failed`; the checkpoints/evidence it lands ARE the append-only ledger.

import type { AgentRole } from "./project";
import type { ResultStatus } from "./research";

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
