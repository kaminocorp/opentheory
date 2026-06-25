import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

import { ReadoutLabel } from "./readout-label";

interface MetricReadoutProps {
  /** The mono readout label (category). */
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
 * A metric readout (§5.5): a square nested tile carrying a mono readout label and
 * a mono tabular value. The atomic unit of the header count grid and the budget
 * grid. Nested inside a bay, so it sits on `--panel-2`.
 */
export function MetricReadout({ label, value, title, valueClassName, className }: MetricReadoutProps) {
  return (
    <div
      className={cn("rounded-built bg-panel-2 px-3 py-2", className)}
      style={{ border: "0.5px solid var(--hairline)" }}
      title={title}
    >
      <ReadoutLabel as="p">{label}</ReadoutLabel>
      <p
        className={cn(
          "mt-1 font-mono text-[19px] font-medium leading-tight tabular-nums",
          valueClassName ?? "text-text",
        )}
      >
        {value}
      </p>
    </div>
  );
}
