import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

interface MetricReadoutProps {
  /** The metric label (sans, muted). */
  label: ReactNode;
  /** The measured value — mono, tabular. May be a number, a "—", or a shimmer node. */
  value: ReactNode;
  /** Tooltip (e.g. the Spent / compute-spend explainer). */
  title?: string;
  /** Colour class for the value (default `text-text`). State-coloured only when
   *  the value itself carries state. */
  valueClassName?: string;
  className?: string;
}

/**
 * A metric readout: a quiet nested tile carrying a small muted label and a
 * tabular value. The atomic unit of the header count grid and the budget grid.
 */
export function MetricReadout({ label, value, title, valueClassName, className }: MetricReadoutProps) {
  return (
    <div
      className={cn(
        "rounded-control border border-[color:var(--hairline)] bg-white/[0.02] px-3 py-2",
        className,
      )}
      title={title}
    >
      <p className="text-[12px] font-medium text-text-mute">{label}</p>
      <p
        className={cn(
          "mt-1 font-mono text-[18px] font-medium leading-tight tabular-nums",
          valueClassName ?? "text-text",
        )}
      >
        {value}
      </p>
    </div>
  );
}
