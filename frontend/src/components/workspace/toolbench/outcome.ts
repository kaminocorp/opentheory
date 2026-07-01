import type { StateTone } from "@/components/console";
import type { ResultStatus } from "@/types/toolbench";

export type OutcomeMeta = {
  /** A console state tone — carries the grayscale-safe glyph + colour (design_blueprint §5.1). */
  tone: StateTone;
  /** The pill label. */
  label: string;
  /** The honesty gloss shown beside the outcome — never softened (plan Phase 7.4). */
  gloss: string;
};

/**
 * The three instrument outcomes → console state tones, rendered *honestly*:
 *
 * - `result`    → ✓ ok — the instrument ran and produced a result.
 * - `refuted`   → ■ fail — a counterexample: the claim is *definitively false*. This is an
 *   asymmetrically **strong** outcome (a single witness settles it), not an error — the fail tone
 *   marks the claim as false, and the counterexample card frames it as the definitive finding it is.
 * - `undecided` → ▲ warn — the tool ran but could not decide. It renders as "escalate to a proof",
 *   **never** as a pass (the seam to the deferred Z3/Lean verifier).
 */
export const OUTCOME: Record<ResultStatus, OutcomeMeta> = {
  result: {
    tone: "ok",
    label: "Result",
    gloss: "The instrument ran and produced a result.",
  },
  refuted: {
    tone: "fail",
    label: "Refuted",
    gloss: "A counterexample — the claim is definitively false.",
  },
  undecided: {
    tone: "warn",
    label: "Undecided",
    gloss: "Could not decide — escalate to a proof, never a pass.",
  },
};

/** Defensive lookup: a lenient-read blame tuple could carry an unknown status; degrade, don't throw. */
export function outcomeMeta(status: string | undefined): OutcomeMeta {
  if (status && status in OUTCOME) return OUTCOME[status as ResultStatus];
  return { tone: "mute", label: status ?? "—", gloss: "" };
}

/**
 * Flatten the free-form assumption map into human-readable chips so assumptions are *visible* on the
 * record, not a hidden flag (plan Phase 7.4). Two shapes ride in the same map:
 * - a per-symbol SymPy flag set — `{ x: { positive: true } }` → `x: positive`;
 * - a contextual scalar — `{ angle: 90 }` → `angle = 90`.
 */
export function formatAssumptions(assumptions: Record<string, unknown> | undefined): string[] {
  if (!assumptions) return [];
  const chips: string[] = [];
  for (const [key, value] of Object.entries(assumptions)) {
    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      for (const [predicate, on] of Object.entries(value as Record<string, unknown>)) {
        chips.push(on === false ? `${key}: ¬${predicate}` : `${key}: ${predicate}`);
      }
    } else {
      chips.push(`${key} = ${String(value)}`);
    }
  }
  return chips;
}
