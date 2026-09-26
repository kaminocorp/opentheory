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
 * - `undecided` → ▲ warn — the tool ran but could not decide. It renders as "escalate",
 *   **never** as a pass (`z3.prove` / `z3.satisfy` / `lean.prove` can land a real
   decision; a failed
 *   Lean check or missing toolchain stays here).
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
 * Instrument-honest chrome. Generic `outcomeMeta("result")` is `ok`; several instruments
 * produce a `result` that is *not* a pass (weak support, a proof without `proven`,
 * a finite table hold). Proof / satisfy instruments fall through to **warn** unless
 * the machine-checked flag is true — a missing `proven` must never read as a pass.
 */
export function resolveOutcomeMeta(
  instrumentName: string,
  status: string,
  output: Record<string, unknown> = {},
): OutcomeMeta {
  if (
    instrumentName === "counterexample.search" &&
    status === "result" &&
    output.found === false
  ) {
    return {
      tone: "warn",
      label: "No witness",
      gloss: "Weak support only — absence in this search space is not proof.",
    };
  }
  if (instrumentName === "z3.prove") {
    if (status === "result" && output.proven === true) {
      return {
        tone: "ok",
        label: "Proven",
        gloss: "Machine-checked: the goal holds for all assignments under the hypotheses.",
      };
    }
    if (status === "refuted" && output.refuted === true) {
      return {
        tone: "fail",
        label: "Refuted",
        gloss: "Counter-model — a concrete assignment breaks the goal.",
      };
    }
    return {
      tone: "warn",
      label: "Undecided",
      gloss: "Z3 could not decide — recorded, never a pass.",
    };
  }
  if (instrumentName === "z3.satisfy") {
    if (status === "result" && output.satisfied === true) {
      return {
        tone: "ok",
        label: "Satisfiable",
        gloss: "A concrete assignment satisfies the constraints.",
      };
    }
    if (status === "refuted" && output.unsatisfiable === true) {
      return {
        tone: "fail",
        label: "Unsatisfiable",
        gloss: "No model exists — the constraints cannot be satisfied.",
      };
    }
    return {
      tone: "warn",
      label: "Undecided",
      gloss: "Z3 could not decide — recorded, never a fabricated model.",
    };
  }
  if (instrumentName === "lean.prove") {
    if (status === "result" && output.proven === true) {
      return {
        tone: "ok",
        label: "Proven",
        gloss: "Lean kernel accepted the snippet — machine-checked proof.",
      };
    }
    if (output.outcome === "failed") {
      return {
        tone: "warn",
        label: "Failed",
        gloss: "Lean rejected the snippet — not a proof, not a refutation.",
      };
    }
    return {
      tone: "warn",
      label: "Undecided",
      gloss: "Lean unavailable or timed out — recorded, never a pass.",
    };
  }
  if (instrumentName === "table.derive_column") {
    if (status === "refuted") {
      return {
        tone: "fail",
        label: "Refuted",
        gloss: "A computed row falsifies the relation — exact witness.",
      };
    }
    if (status === "result" && output.is_relation === true) {
      return {
        tone: "warn",
        label: "Holds on this table",
        gloss: "Finite support only — every row holding is not a proof.",
      };
    }
    if (status === "undecided") {
      return {
        tone: "warn",
        label: "Undecided",
        gloss: "A row could not be settled exactly — recorded, never a pass.",
      };
    }
  }
  if (instrumentName === "interval.eval") {
    if (status === "result") {
      return {
        tone: "ok",
        label: "Enclosure",
        gloss: "Proven bound — not a machine-checked proof.",
      };
    }
    if (status === "refuted") {
      return {
        tone: "fail",
        label: "Refuted",
        gloss: "The enclosure misses the claimed value.",
      };
    }
    if (status === "undecided") {
      return {
        tone: "warn",
        label: "Undecided",
        gloss: "Overlap, timeout, or could not enclose — never a fabricated bound.",
      };
    }
  }
  if (instrumentName === "plot.function" || instrumentName === "plot.points") {
    if (status === "undecided") {
      return {
        tone: "warn",
        label: "Undecided",
        gloss: "Not enough real samples — recorded, never a fabricated plot.",
      };
    }
    return {
      tone: "ok",
      label: "Plot",
      gloss: "Visualization only — not evidence.",
    };
  }
  return outcomeMeta(status);
}

/**
 * Agent-trace chrome for one landed step. Uses the recorded display map when the
 * pass persisted one (0.36.2+); pre-0.36.2 rows have no `output` and fall through
 * the same honesty rules as ResultView with an empty map.
 */
export function landedStepMeta(step: {
  instrument: string;
  outcome?: string | null;
  output?: Record<string, unknown> | null;
}): OutcomeMeta {
  return resolveOutcomeMeta(step.instrument, step.outcome ?? "", step.output ?? {});
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
