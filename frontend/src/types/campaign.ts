// Continuous research campaign types (0.25.0), mirroring app/schemas/campaign.py.
// A ResearchCampaign is the human-visible *trace* of a long-running loop that
// repeatedly commissions 0.22.0 orchestrations against the shared ComputeDebit
// ceiling. It is NOT a ledger primitive — each cycle's OrchestrationRun writes
// the ledger through run_agent_pass. Merge / tag stay human.

import type { AgentRole } from "./project";

export type ResearchCampaignStatus = "running" | "completed" | "failed";

export type CampaignStopReason =
  | "budget_exhausted"
  | "no_open_work"
  | "max_cycles"
  | "cancelled"
  | "error_budget"
  | "error";

export type CampaignCycle = {
  cycle: number;
  orchestration_id: string | null;
  orchestration_status: string | null;
  stop_reason: string | null;
  passes_commissioned: number | null;
  passes_completed: number | null;
  passes_failed: number | null;
  budget_remaining: string | null;
  error: string | null;
};

export type ResearchCampaignSummary = {
  id: string;
  project_id: string;
  triggered_by_actor_id: string | null;
  role: string;
  status: ResearchCampaignStatus;
  stop_reason: CampaignStopReason | string | null;
  current_cycle: number;
  cycles_completed: number;
  consecutive_errors: number;
  cancel_requested: boolean;
  budget_available_start: string | null;
  budget_available_end: string | null;
  max_cycles: number;
  error_budget: number;
  error: string | null;
  created_at: string;
  updated_at: string;
};

export type ResearchCampaignRead = ResearchCampaignSummary & {
  cycles: CampaignCycle[];
};

export type CampaignTrigger = {
  role: AgentRole;
  max_cycles?: number;
};
