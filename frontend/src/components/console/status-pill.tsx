import { cn } from "@/lib/cn";

import { STATE_META, type StateTone } from "./state";

interface StatusPillProps {
  /** The state tone — drives the glyph + colour. */
  tone: StateTone;
  /** The status text (rendered capitalized, sans). */
  label: string;
  /** Override the tone's default glyph (e.g. `contradicts` → ▲). */
  glyph?: string;
  className?: string;
}

/**
 * The honest status atom: a quiet pill carrying a glyph + label so it reads
 * with colour removed. The label stays at full `--text-soft` weight and the
 * glyph carries the state colour — a failed pill is never dimmer or smaller
 * than a passed one.
 */
export function StatusPill({ tone, label, glyph, className }: StatusPillProps) {
  const meta = STATE_META[tone];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border border-[color:var(--hairline)] bg-white/[0.03] px-2.5 py-[3px] text-[12px] capitalize text-text-soft",
        className,
      )}
    >
      <span aria-hidden className={cn("text-[10px] leading-none", meta.text)}>
        {glyph ?? meta.glyph}
      </span>
      <span>{label}</span>
    </span>
  );
}
