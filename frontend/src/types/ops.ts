// Perpetual ops dashboard (0.49.0). Mirrors app/schemas/ops.py.
// Every number is on the ledger or a setting this API process can see.
// Anything else is labeled unknown.

import type { ProjectBudget } from "./research";

export type OpsBudgetState = "unfunded" | "available" | "exhausted";
export type OpsProcessIntSource = "default" | "process_env" | "invalid";
export type OpsHarnessRowKind = "spend" | "hold" | "release";
export type OpsHoldStatus = "open" | "released";

export type OpsBudgetRead = {
  snapshot: ProjectBudget;
  state: OpsBudgetState;
  note: string;
};

export type OpsDailyCapRead = {
  utc_day: string;
  cap: number | null;
  cap_source: OpsProcessIntSource;
  tokens_used_today: number;
  remaining: number | null;
  exhausted: boolean | null;
  hold_ttl_seconds: number | null;
  hold_ttl_source: OpsProcessIntSource;
  note: string;
};

export type OpsHoldRead = {
  hold_id: string | null;
  status: OpsHoldStatus;
  tokens: number;
  created_at: string;
  released_at: string | null;
  stale: boolean | null;
  note: string | null;
};

export type OpsTurnRead = {
  id: string;
  created_at: string;
  tokens_used: number;
  amount: string;
  notes: string | null;
  kind: OpsHarnessRowKind;
  hold_id: string | null;
};

export type OpsRefusalsRead = {
  recorded: false;
  note: string;
};

export type OpsLoopRead = {
  enabled: boolean;
  source: "settings.agent_loop_enabled";
};

export type OpsUnknownProcessRead = {
  enabled: "unknown";
  note: string;
};

export type OpsEnablementRead = {
  loop: OpsLoopRead;
  gateway: OpsUnknownProcessRead;
  mcp_child: OpsUnknownProcessRead;
};

export type ProjectOpsRead = {
  project_id: string;
  as_of: string;
  notes_prefix: string;
  budget: OpsBudgetRead;
  daily_cap: OpsDailyCapRead;
  holds: OpsHoldRead[];
  recent_turns: OpsTurnRead[];
  refusals: OpsRefusalsRead;
  enablement: OpsEnablementRead;
};
