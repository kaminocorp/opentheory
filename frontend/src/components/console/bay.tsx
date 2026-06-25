import type { ComponentPropsWithoutRef, ElementType, ReactNode } from "react";

import { cn } from "@/lib/cn";

import { ReadoutLabel, type ReadoutTone } from "./readout-label";
import { RegistrationBand, RegistrationBrackets } from "./registration";

interface BayOwnProps {
  children: ReactNode;
  as?: ElementType;
  /** Render the four corner registration brackets (§2.2). Primary bays only. */
  bracketed?: boolean;
  /** The single top-right chamfer (§2.2) — identity headers only. */
  chamfer?: boolean;
  /** Inner padding tier. `monitor` runs dense, `narrative` runs roomy (§4.2). */
  density?: "monitor" | "narrative" | "none";
  className?: string;
}

// Forward arbitrary element props (id, onSubmit, …) so a Bay can be a <form>, or
// carry an anchor id like `#funding`. The own props win where names collide.
type BayProps = BayOwnProps & Omit<ComponentPropsWithoutRef<"div">, keyof BayOwnProps>;

const DENSITY_PAD: Record<NonNullable<BayProps["density"]>, string> = {
  monitor: "p-4", // 2u
  narrative: "p-6", // 3u
  none: "", // header + content well manage their own padding
};

/**
 * The core square recessed instrument bay (§2.2). A surface cut *into* the
 * console, lit by structure (the `.bay` recess in globals.css), never by glow.
 * Square by law — a round bay is a bug.
 */
export function Bay({
  children,
  as: Tag = "section",
  bracketed = false,
  chamfer = false,
  density = "none",
  className,
  ...rest
}: BayProps) {
  return (
    <Tag className={cn("bay", chamfer && "bay-chamfer", DENSITY_PAD[density], className)} {...rest}>
      {bracketed && <RegistrationBrackets />}
      {children}
    </Tag>
  );
}

interface BayHeaderProps {
  /** Set in mono (it is a readout label / machine tag). */
  label: ReactNode;
  /** Optional mono count beside the label. */
  count?: ReactNode;
  /** Right-aligned actions slot. */
  actions?: ReactNode;
  /** Underline the header with the measured registration band. */
  band?: boolean;
  tone?: ReadoutTone;
  className?: string;
}

/**
 * The fixed 6u (48px) bay header (§4.2): a readout label, an optional mono count,
 * an optional actions slot, and an optional registration-band underline. Every bay
 * shares this edge rhythm regardless of size.
 */
export function BayHeader({ label, count, actions, band = false, tone = "mute", className }: BayHeaderProps) {
  return (
    <div className={cn("flex flex-col", className)}>
      <div className="flex h-12 items-center justify-between gap-3 px-4">
        <div className="flex items-baseline gap-2">
          <ReadoutLabel tone={tone}>{label}</ReadoutLabel>
          {count != null && (
            <span className="font-mono text-[11px] tabular-nums text-text-mute">{count}</span>
          )}
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
      {band && <RegistrationBand className="px-4 pb-2" />}
    </div>
  );
}
