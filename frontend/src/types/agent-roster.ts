// Project agent roster (0.57.0). Mirrors app/schemas/agent_roster.py.
// Never carries token plaintext or hash.

import type { AccountSummary } from "./research";

export type ProjectAgentStatus = "active" | "suspended" | "revoked";
export type ProjectAgentRole = "researcher";

export type AgentLiveToken = {
  jti: string;
  expires_at: string;
  last_used_at: string | null;
};

export type AgentRosterRead = {
  actor_id: string;
  display_name: string;
  status: ProjectAgentStatus;
  role: ProjectAgentRole;
  deployed_by: AccountSummary | null;
  responsible: AccountSummary | null;
  token_budget_cap: number | null;
  usd_budget_cap: string | null;
  last_used_at: string | null;
  tokens_used: number;
  amount: string;
  live_tokens: AgentLiveToken[];
  created_at: string;
};

export type AgentDeployRequest = {
  display_name: string;
  reuse_research_crew?: boolean;
};

export type AgentRosterPatch = {
  status: ProjectAgentStatus;
};

export type AgentTokenMintRead = {
  token: string;
  jti: string;
  expires_at: string;
};
