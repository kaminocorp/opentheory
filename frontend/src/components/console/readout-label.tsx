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
 * A quiet section / field label: sans, 13px medium, sentence case. Used for
 * form labels, metric labels, and secondary section headings. No all-caps, no
 * letterspacing — hierarchy comes from weight and colour, not treatment.
 */
export function ReadoutLabel({ children, tone = "mute", as: Tag = "span", className }: ReadoutLabelProps) {
  return (
    <Tag
      className={cn(
        "text-[13px] font-medium",
        tone === "signal" ? "text-signal" : "text-text-soft",
        className,
      )}
    >
      {children}
    </Tag>
  );
}
