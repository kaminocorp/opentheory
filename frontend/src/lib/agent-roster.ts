import type { StateTone } from "@/components/console";
import type { ProjectAgentStatus } from "@/types/agent-roster";

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
export function tokenRevealCacheKey(_token: string): null {
  return null;
}
