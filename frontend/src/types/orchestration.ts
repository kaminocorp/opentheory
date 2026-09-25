// Project-level orchestration types (0.22.0), mirroring app/schemas/orchestration.py.
// An OrchestrationRun is the human-visible *trace* of one bounded multi-thread
// research loop: which threads were commissioned or skipped, why the loop stopped,
// and how much project budget remained. It is NOT a ledger primitive — the
// AgentRuns it commissions write the ledger through run_agent_pass.

import type { AgentRole } from "./project";

export type OrchestrationRunStatus = "running" | "completed" | "failed";

export type OrchestrationStopReason =
  | "budget_exhausted"
  | "no_open_work"
  | "max_passes"
  | "error";

export type OrchestrationDecisionAction = "commissioned" | "skipped";

export type OrchestrationDecision = {
  thread_id: string;
  thread_title: string | null;
  action: OrchestrationDecisionAction | string;
  reason: string | null;
  agent_run_id: string | null;
  agent_run_status: string | null;
  tokens_used: number | null;
  ran_count: number | null;
  budget_remaining: string | null;
};

export type OrchestrationRunSummary = {
  id: string;
  project_id: string;
  triggered_by_actor_id: string | null;
  role: string;
  status: OrchestrationRunStatus;
  stop_reason: OrchestrationStopReason | string | null;
  passes_commissioned: number;
  passes_completed: number;
  passes_failed: number;
  passes_skipped: number;
  budget_available_start: string | null;
  budget_available_end: string | null;
  max_passes: number;
  error: string | null;
  created_at: string;
  updated_at: string;
};

export type OrchestrationRunRead = OrchestrationRunSummary & {
  decisions: OrchestrationDecision[];
};

export type OrchestrationTrigger = {
  role: AgentRole;
};
