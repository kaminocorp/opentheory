import type { ClaimBlameStep } from "@/types/research";

/** Quiet one-line attribution for a blame step. Sentence case; no AI chrome. */
export function blameAuthorLine(step: ClaimBlameStep): string {
  const name = step.author?.display_name ?? "unknown actor";
  const kind = step.author?.type ?? "human";
  const action = step.contribution_kind ?? "checkpoint";
  return `${name} · ${kind} · ${action}`;
}

/** Signal / grounding move copy, or null when this commit did not move either axis. */
export function blameMovementLine(step: ClaimBlameStep): string | null {
  const bits: string[] = [];
  if (step.signal_moved) {
    bits.push(`signal ${step.from_signal ?? "—"} → ${step.signal_after}`);
  }
  if (step.grounding_moved) {
    bits.push(`grounding ${step.from_grounding ?? "—"} → ${step.grounding_after}`);
  }
  return bits.length > 0 ? bits.join(" · ") : null;
}

export function blameInstrumentLine(step: ClaimBlameStep): string | null {
  if (step.instruments.length === 0) return null;
  return step.instruments.map((row) => `${row.instrument} ${row.status}`).join(" · ");
}
