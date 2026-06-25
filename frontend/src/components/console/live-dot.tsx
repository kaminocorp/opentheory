import { cn } from "@/lib/cn";

import { STATE_META, type StateTone } from "./state";

interface LiveDotProps {
  tone?: StateTone;
  /** 1.6s opacity pulse (§5.1) — opacity only, never a glow. Freezes under
   *  prefers-reduced-motion (the `.anim-pulse` freeze in globals.css). */
  pulse?: boolean;
  /** Diameter in px (default 8 — the fixed live-dot size, §2.4). */
  size?: number;
  className?: string;
}

/**
 * The live dot (§5.1): an 8px round indicator. Round *is* the signal that
 * something is alive. Solid for steady; opacity-pulsing for active / streaming.
 */
export function LiveDot({ tone = "run", pulse = false, size = 8, className }: LiveDotProps) {
  return (
    <span
      aria-hidden
      className={cn("inline-block shrink-0 rounded-full", STATE_META[tone].bg, pulse && "anim-pulse", className)}
      style={{ width: size, height: size }}
    />
  );
}
