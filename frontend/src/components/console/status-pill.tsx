import { cn } from "@/lib/cn";

import { STATE_META, type StateTone } from "./state";

interface StatusPillProps {
  /** The state tone — drives the glyph + colour. */
  tone: StateTone;
  /** The readout text (rendered UPPERCASE, mono). */
  label: string;
  /** Override the tone's default glyph (e.g. `contradicts` → ▲). */
  glyph?: string;
  className?: string;
}

/**
 * The honest status atom (§5.1): fully round (it reports something *alive*),
 * mono UPPERCASE 11px, carrying a glyph + label so it reads with colour removed.
 * The label stays at full `--text-soft` weight and the glyph carries the state
 * colour — a FAILED pill is never dimmer or smaller than a PASSED one (§1).
 */
export function StatusPill({ tone, label, glyph, className }: StatusPillProps) {
  const meta = STATE_META[tone];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-[3px] font-mono text-[11px] uppercase tracking-[0.08em] text-text-soft",
        className,
      )}
      style={{ borderColor: "var(--hairline)" }}
    >
      <span aria-hidden className={cn("text-[10px] leading-none", meta.text)}>
        {glyph ?? meta.glyph}
      </span>
      <span>{label}</span>
    </span>
  );
}
