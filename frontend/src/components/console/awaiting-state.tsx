import { cn } from "@/lib/cn";

import { BrandMark } from "./brand-mark";

export type AwaitingVariant = "loading" | "empty" | "error";

interface AwaitingStateProps {
  /** One-line status, e.g. "Loading projects", "No threads yet". */
  label: string;
  variant?: AwaitingVariant;
  className?: string;
}

/**
 * The awaiting / empty / error state — "the mark holds the frame".
 *
 * Loading: the mark's four nodes light in a diagonal cascade. Empty/error: it
 * holds steady (reads "stopped", not "loading") — never a bare spinner, never a
 * broken glyph. On error the label takes the `--state-fail` colour at full
 * weight so failure is as loud as success.
 */
export function AwaitingState({ label, variant = "loading", className }: AwaitingStateProps) {
  const loading = variant === "loading";
  // Announce state transitions to assistive tech: an error is assertive (`alert`), a load is
  // polite (`status`); a steady empty state needs no live region. `role` implies the matching
  // `aria-live`, so failures are heard as well as seen (the honesty surface, for SR users).
  const role = variant === "error" ? "alert" : variant === "loading" ? "status" : undefined;
  return (
    <div
      role={role}
      className={cn("flex flex-col items-center justify-center gap-3 px-4 py-10 text-center", className)}
    >
      <BrandMark
        size={28}
        animated={loading}
        className={cn(loading ? "text-text-soft" : "text-text-mute")}
      />
      <span
        className={cn(
          "text-[13px]",
          variant === "error" ? "font-medium text-state-fail" : "text-text-mute",
        )}
      >
        {label}
      </span>
    </div>
  );
}
