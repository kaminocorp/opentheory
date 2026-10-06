import type {
  OpsActorSpendRead,
  OpsBudgetState,
  OpsDailyCapRead,
  OpsEnablementRead,
  OpsHarnessRowKind,
  OpsHoldRead,
  OpsHoldStatus,
  OpsLastTurnRead,
  ProjectOpsRead,
} from "@/types/ops";

export function formatOpsMoney(amount: string, currency: string): string {
  const value = Number(amount);
  if (Number.isNaN(value)) return `${amount} ${currency}`;
  // Ledger amounts are Numeric(12, 6). Default currency rounding (2 dp) would
  // turn $0.000400 into $0.00 — an invented zero. Keep up to 6 fraction digits.
  const options: Intl.NumberFormatOptions = {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
  };
  try {
    return new Intl.NumberFormat(undefined, options).format(value);
  } catch {
    return `${value.toFixed(6).replace(/0+$/, "").replace(/\.$/, ".00")} ${currency}`;
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

export function lastTurnLine(turn: OpsLastTurnRead): string {
  const used = `${turn.tokens_used.toLocaleString()} used`;
  const who = turnActorSuffix(turn);
  if (turn.clamp === null) {
    return `${used}${who} · clamp unknown`;
  }
  const overshoot =
    turn.overshoot && turn.overshoot > 0 ? ` · overshoot ${turn.overshoot.toLocaleString()}` : "";
  const price = turn.price_known === false ? " · price unknown" : "";
  return `${used}${who} · clamp ${turn.clamp.toLocaleString()}${overshoot}${price}`;
}

/** Missing `actor_*` (pre-0.57 backend) is unattributed — never a throw. */
export function turnActorLabel(turn: {
  actor_id?: string | null;
  actor_display_name?: string | null;
}): string {
  if (turn.actor_display_name) return turn.actor_display_name;
  if (turn.actor_id) return "unknown actor";
  return "unattributed";
}

function turnActorSuffix(turn: {
  actor_id?: string | null;
  actor_display_name?: string | null;
}): string {
  return ` · ${turnActorLabel(turn)}`;
}

export function spendByAgentLine(tokensUsed: number, displayName: string | null | undefined): string {
  const who = displayName ?? "unknown actor";
  return `${who} · ${tokensUsed.toLocaleString()} tok`;
}

/**
 * `spend_by_agent` is 0.57.0. A pre-identity `GET /ops` omits it.
 * Readers must not call `.length` on undefined — that threw on prod Overview.
 */
export function opsSpendByAgent(
  data: Pick<ProjectOpsRead, "spend_by_agent"> | Record<string, unknown> | null | undefined,
): OpsActorSpendRead[] {
  const rows = data && typeof data === "object" ? data.spend_by_agent : undefined;
  return Array.isArray(rows) ? (rows as OpsActorSpendRead[]) : [];
}

export function lastTurnTone(turn: OpsLastTurnRead): "fail" | "mute" | "ok" {
  if (turn.overshoot && turn.overshoot > 0) return "fail";
  if (turn.clamp === null) return "mute";
  return "ok";
}
