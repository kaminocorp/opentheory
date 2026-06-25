import type { ElementType, ReactNode } from "react";

import { cn } from "@/lib/cn";

export type ReadoutTone = "mute" | "signal";

interface ReadoutLabelProps {
  children: ReactNode;
  /** `signal` only for the single live / primary zone label — used sparingly. */
  tone?: ReadoutTone;
  as?: ElementType;
  className?: string;
}

/**
 * The readout label (§3.2): the one sanctioned all-caps in the whole system.
 * Mono, 11px / 500, 0.14em tracking, UPPERCASE — a machine-stamped tag, never
 * used for prose, headings, or buttons.
 */
export function ReadoutLabel({ children, tone = "mute", as: Tag = "span", className }: ReadoutLabelProps) {
  return (
    <Tag
      className={cn(
        "font-mono text-[11px] font-medium uppercase tracking-[0.14em]",
        tone === "signal" ? "text-signal" : "text-text-mute",
        className,
      )}
    >
      {children}
    </Tag>
  );
}
