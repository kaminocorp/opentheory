import { cn } from "@/lib/cn";

import { BrandMark } from "./brand-mark";

export type AwaitingVariant = "loading" | "empty" | "error";

interface AwaitingStateProps {
  /** One-line mono readout, e.g. "awaiting telemetry", "no threads yet". */
  label: string;
  variant?: AwaitingVariant;
  className?: string;
}

/**
 * The awaiting / empty / error state (§5.9) — "the mark holds the frame".
 *
 * Loading: the mark slow-breathes (≈3s opacity/scale). Empty/error: it holds
 * steady (reads "stopped", not "loading") — never a bare spinner, never a broken
 * glyph, no crimson halo. On error the label takes the `--state-fail` colour at
 * full weight so failure is as loud as success (§1).
 */
export function AwaitingState({ label, variant = "loading", className }: AwaitingStateProps) {
  const breathing = variant === "loading";
  // Announce state transitions to assistive tech: an error is assertive (`alert`), a load is
  // polite (`status`); a steady empty state needs no live region. `role` implies the matching
  // `aria-live`, so failures are heard as well as seen (the §1 honesty surface, for SR users).
  const role = variant === "error" ? "alert" : variant === "loading" ? "status" : undefined;
  return (
    <div
      role={role}
      className={cn("flex flex-col items-center justify-center gap-3 px-4 py-10 text-center", className)}
    >
      <BrandMark
        size={28}
        className={cn(breathing ? "anim-breathe text-text-soft" : "text-text-mute")}
      />
      <span
        className={cn(
          "font-mono text-[11px] font-medium uppercase tracking-[0.14em]",
          variant === "error" ? "text-state-fail" : "text-text-mute",
        )}
      >
        {label}
      </span>
    </div>
  );
}
