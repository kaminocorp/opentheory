import type { ComponentPropsWithoutRef, ElementType, ReactNode } from "react";

import { cn } from "@/lib/cn";

interface BayOwnProps {
  children: ReactNode;
  as?: ElementType;
  /** Inner padding tier. `monitor` runs dense, `narrative` runs roomy. */
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
 * The core card surface (the `.bay` class in globals.css): one step above the
 * ground, a low-alpha border, a soft radius. Flat and quiet — surfaces separate
 * by lightness and border, never by ornament.
 */
export function Bay({
  children,
  as: Tag = "section",
  density = "none",
  className,
  ...rest
}: BayProps) {
  return (
    <Tag className={cn("bay", DENSITY_PAD[density], className)} {...rest}>
      {children}
    </Tag>
  );
}

interface BayHeaderProps {
  /** The card title — sans, sentence case. */
  label: ReactNode;
  /** Optional count beside the title (tabular, muted). */
  count?: ReactNode;
  /** Right-aligned actions slot. */
  actions?: ReactNode;
  /** Separate the header from the content with a hairline divider. */
  divider?: boolean;
  className?: string;
}

/**
 * The fixed 48px card header: a sans title, an optional muted count, and an
 * optional actions slot. Every card shares this edge rhythm regardless of size.
 */
export function BayHeader({ label, count, actions, divider = false, className }: BayHeaderProps) {
  return (
    <div className={cn("flex flex-col", divider && "border-b border-[color:var(--hairline)]", className)}>
      <div className="flex h-12 items-center justify-between gap-3 px-4">
        <div className="flex items-baseline gap-2">
          <span className="text-[14px] font-medium text-text">{label}</span>
          {count != null && (
            <span className="font-mono text-[12px] tabular-nums text-text-mute">{count}</span>
          )}
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
    </div>
  );
}
