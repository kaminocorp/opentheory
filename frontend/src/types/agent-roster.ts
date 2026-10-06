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
  // 0.58.0 — omitted on a pre-0.58 backend. Derive from tokens_used vs cap.
  token_cap_reached?: boolean;
  usd_cap_reached?: boolean;
  live_tokens: AgentLiveToken[];
  created_at: string;
  // 0.59.0 — omitted on a pre-0.59 backend. Never throw if missing.
  agent_definition_id?: string | null;
  family_id?: string | null;
  definition_display_name?: string | null;
  definition_version?: number | null;
};

export type AgentDeployRequest = {
  display_name: string;
  reuse_research_crew?: boolean;
  token_budget_cap?: number | null;
  usd_budget_cap?: string | null;
  agent_definition_id?: string | null;
};

export type AgentUpgradeRequest = {
  agent_definition_id: string;
};

export type AgentDefinitionRead = {
  id: string;
  account_id: string | null;
  family_id: string;
  version: number;
  display_name: string;
  config_fingerprint: string;
  config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type AgentFamilyRollupRead = {
  family_id: string;
  versions: AgentDefinitionRead[];
  actors: Array<{
    actor_id: string;
    project_id: string | null;
    display_name: string;
    definition_id: string;
    definition_version: number;
  }>;
  checkpoints_authored: number;
  incoming_validations: number;
  tokens_billed: number;
  amount_billed: string;
};

export type AgentRosterPatch = {
  status?: ProjectAgentStatus;
  token_budget_cap?: number | null;
  usd_budget_cap?: string | null;
};

export type AgentTokenMintRead = {
  token: string;
  jti: string;
  expires_at: string;
};
