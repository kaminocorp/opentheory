import { cn } from "@/lib/cn";
import type { ClaimGrounding, GroundingHeadline } from "@/types/research";

/**
 * The evidence grade ladder, on a claim (0.16.0).
 *
 * Shows *how strongly a claim is backed by what actually ran* — the evidence axis, deliberately
 * distinct in shape from the validation `StatusPill` next to it (mono letter in a square tile vs. a
 * glyph in a rounded pill). The two are never combined into one number: a merged score would be
 * exactly the "naked score" the domain model forbids.
 *
 * Honesty rules carried from the backend into the surface:
 *  - **D is calm, never alarming.** It is the *absence* of a tool, not a failure — the baseline the
 *    bench exists to climb out of. It renders muted, at the same weight as everything else.
 *  - **`undecided` never appears here at all.** It contributes no grade server-side, so an
 *    escalation seam can never read as a weak pass.
 *  - **Colour only reinforces.** The letter and the label carry the meaning; the whole chip is
 *    legible with colour removed (design-system §0, grayscale survival).
 *
 * Crimson `--signal` is reserved for `refuted` — *not* `--state-fail`. A refutation is a successful,
 * valuable research outcome, not an error; spending the error red on it would make the bench doing
 * its job look like something breaking.
 */

type ChipStyle = {
  /** The mono character in the tile — the rung itself, or a glyph when there is no letter. */
  mark: string;
  label: string;
  /** What it would take to climb — the affordance that makes the ladder actionable. */
  raise: string;
  text: string;
  tile: string;
};

const HEADLINE_STYLE: Record<GroundingHeadline, ChipStyle> = {
  proven: {
    mark: "A",
    label: "Proven",
    raise: "Machine-checked — the top rung.",
    text: "text-state-ok",
    tile: "bg-state-ok/12",
  },
  refuted: {
    mark: "✕",
    label: "Refuted",
    raise: "A counterexample stands against this claim.",
    text: "text-signal",
    tile: "bg-signal/12",
  },
  B: {
    mark: "B",
    label: "Exact",
    raise: "An exact result; a proof would settle it.",
    text: "text-state-ok",
    tile: "bg-state-ok/10",
  },
  C: {
    mark: "C",
    label: "Sampled",
    raise: "Finite sampling only; an exact result would raise it.",
    text: "text-state-warn",
    tile: "bg-state-warn/10",
  },
  D: {
    mark: "D",
    label: "Asserted",
    raise: "Asserted, not computed; run an instrument to ground it.",
    text: "text-text-mute",
    tile: "bg-white/[0.04]",
  },
  cited: {
    mark: "◇",
    label: "Cited",
    raise: "Pinned to an external source; a computation would grade it.",
    text: "text-text-soft",
    tile: "bg-white/[0.04]",
  },
  ungrounded: {
    mark: "·",
    label: "Ungrounded",
    raise: "No evidence yet; run an instrument or attach evidence.",
    text: "text-text-faint",
    tile: "bg-white/[0.03]",
  },
};

/** The refuting rung, spelled out — an A counter and a B counter are not the same claim about rigor. */
function refutationDetail(counter: ClaimGrounding["counter"]): string {
  return counter === "A"
    ? "A machine-checked counter-model refutes it."
    : "An exact counterexample refutes it.";
}

export function groundingRaiseLine(grounding: ClaimGrounding): string {
  if (grounding.headline === "refuted") return refutationDetail(grounding.counter);
  return HEADLINE_STYLE[grounding.headline].raise;
}

export function GroundingChip({
  grounding,
  className,
}: {
  grounding: ClaimGrounding;
  className?: string;
}) {
  const style = HEADLINE_STYLE[grounding.headline];
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-control px-1.5 py-[3px] text-[12px] text-text-soft",
        style.tile,
        className,
      )}
      style={{ border: "1px solid var(--hairline)" }}
      title={groundingRaiseLine(grounding)}
    >
      <span
        aria-hidden
        className={cn(
          "grid size-[15px] place-items-center rounded-[3px] bg-black/25 font-mono text-[11px] leading-none",
          style.text,
        )}
      >
        {style.mark}
      </span>
      <span>{style.label}</span>
      {/* The pin is additive information, not a rung — shown only when it is not already the
          headline, so a cited claim does not read "Cited · cited". */}
      {grounding.cited && grounding.headline !== "cited" ? (
        <span className="text-text-faint">· cited</span>
      ) : null}
    </span>
  );
}
