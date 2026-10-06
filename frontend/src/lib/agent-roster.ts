import type { StateTone } from "@/components/console";
import type { ProjectAgentStatus } from "@/types/agent-roster";

/** Quiet Crew copy when live Fly has no `GET /projects/{id}/agents` yet. */
export const ROSTER_UNAVAILABLE_LINE =
  "The agent roster isn't available on this backend yet.";

/** Same 404 shapes as `request()` / `isNotFoundError` — kept local so node tests resolve. */
export function isRosterUnavailable(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  return error.message.startsWith("404:") || error.message === "Request failed with 404";
}

/** Status pill tone. Revoked is fail-weight — honesty over comfort. */
export function agentStatusTone(status: ProjectAgentStatus): StateTone {
  if (status === "active") return "run";
  if (status === "suspended") return "warn";
  return "fail";
}

export function agentStatusLabel(status: ProjectAgentStatus): string {
  if (status === "active") return "active";
  if (status === "suspended") return "suspended";
  return "revoked";
}

/** Billed tokens for the theft-detection readout. Holds are not spend. */
export function agentSpendLine(tokensUsed: number): string {
  if (tokensUsed <= 0) return "no billed spend";
  return `${tokensUsed.toLocaleString()} tok billed`;
}

export function formatAgentWhen(iso: string | null): string {
  if (!iso) return "never";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toISOString().replace("T", " ").replace(/\.\d+Z$/, " UTC");
}

/**
 * Token plaintext stays in component state for the reveal only.
 * Never a query key, never a cache value, never a log argument.
 */
export function tokenRevealCacheKey(token: string): null {
  void token;
  return null;
}

function parseLedgerNumber(value: string | number | null | undefined): number | null {
  if (value == null || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

/**
 * Cap-reached is 0.58.0. A 0.57 roster has the cap columns but not the
 * flag — derive from billed tokens vs `token_budget_cap`. Missing both
 * is not reached. Never throw on an older shape.
 */
export function agentTokenCapReached(agent: {
  token_budget_cap?: number | null;
  tokens_used?: number;
  token_cap_reached?: boolean;
}): boolean {
  if (typeof agent.token_cap_reached === "boolean") return agent.token_cap_reached;
  const cap = agent.token_budget_cap;
  if (cap == null) return false;
  return (agent.tokens_used ?? 0) >= cap;
}

export function agentUsdCapReached(agent: {
  usd_budget_cap?: string | null;
  amount?: string;
  usd_cap_reached?: boolean;
}): boolean {
  if (typeof agent.usd_cap_reached === "boolean") return agent.usd_cap_reached;
  const cap = parseLedgerNumber(agent.usd_budget_cap);
  if (cap == null) return false;
  const billed = parseLedgerNumber(agent.amount) ?? 0;
  return billed >= cap;
}

export function agentCapLine(agent: {
  token_budget_cap?: number | null;
  usd_budget_cap?: string | null;
}): string {
  const token =
    agent.token_budget_cap != null
      ? `token cap ${agent.token_budget_cap.toLocaleString()}`
      : "no token cap";
  const usd =
    agent.usd_budget_cap != null && agent.usd_budget_cap !== ""
      ? `usd cap ${agent.usd_budget_cap}`
      : "no usd cap";
  return `${token} · ${usd}`;
}
