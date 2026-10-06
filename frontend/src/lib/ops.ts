import type {
  OpsBudgetState,
  OpsDailyCapRead,
  OpsEnablementRead,
  OpsHarnessRowKind,
  OpsHoldRead,
  OpsHoldStatus,
} from "@/types/ops";

export function formatOpsMoney(amount: string, currency: string): string {
  const value = Number(amount);
  if (Number.isNaN(value)) return `${amount} ${currency}`;
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(value);
  } catch {
    return `${value.toFixed(2)} ${currency}`;
  }
}

export function budgetStateLabel(state: OpsBudgetState): string {
  if (state === "unfunded") return "Unfunded";
  if (state === "exhausted") return "Exhausted";
  return "Available";
}

export function budgetStateTone(state: OpsBudgetState): "mute" | "fail" | "ok" {
  if (state === "unfunded") return "mute";
  if (state === "exhausted") return "fail";
  return "ok";
}

export function dailyCapLine(cap: OpsDailyCapRead): string {
  if (cap.cap === null || cap.exhausted === null || cap.remaining === null) {
    return `Used ${cap.tokens_used_today.toLocaleString()} today · cap unknown`;
  }
  return (
    `${cap.tokens_used_today.toLocaleString()} / ${cap.cap.toLocaleString()}` +
    ` · ${cap.remaining.toLocaleString()} remaining`
  );
}

export function dailyCapTone(cap: OpsDailyCapRead): "fail" | "mute" | "ok" {
  if (cap.exhausted === null) return "mute";
  if (cap.exhausted) return "fail";
  return "ok";
}

export function holdStatusLabel(status: OpsHoldStatus, stale: boolean | null): string {
  if (status === "released") return "Released";
  if (stale === true) return "Open (stale)";
  if (stale === null) return "Open (stale unknown)";
  return "Open";
}

export function holdIdLabel(hold: OpsHoldRead): string {
  if (hold.hold_id) return hold.hold_id;
  return "unknown hold_id";
}

export function turnKindLabel(kind: OpsHarnessRowKind): string {
  if (kind === "hold") return "Hold";
  if (kind === "release") return "Release";
  return "Spend";
}

export function loopLine(enablement: OpsEnablementRead): string {
  return enablement.loop.enabled ? "Built-in loop enabled" : "Built-in loop dark";
}

export function unknownProcessLine(label: string, enabled: "unknown"): string {
  return `${label} ${enabled}`;
}
