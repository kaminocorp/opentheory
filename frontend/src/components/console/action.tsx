import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/cn";

export type ActionVariant = "primary" | "ghost" | "text" | "destructive";
export type ActionSize = "sm" | "md";

interface ActionProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ActionVariant;
  /** Compact (`sm`) vs default (`md`) sizing — pick the size here, never via a
   * `className` padding/text override (`cn` has no tailwind-merge, so an override
   * would double-emit `px-*`/`text-*` and resolve by CSS source order). */
  size?: ActionSize;
  /** In-flight state: renders the inert hatched fill (like `disabled`). */
  pending?: boolean;
  children: ReactNode;
}

// Round, always (§5.7) — round is the alive / actionable affordance. Buttons
// never move, scale, or cast shadows; only opacity/colour transitions. Text size is
// a per-size token (kept out of BASE so `sm` overrides cleanly, never doubly-emits).
const BASE =
  "inline-flex items-center justify-center gap-1.5 rounded-full font-sans font-medium transition-colors disabled:cursor-not-allowed";

const TEXT_SIZE: Record<ActionSize, string> = { md: "text-[13px]", sm: "text-[12px]" };

// Split per variant into SHAPE (padding + border *presence* — always applied, so an
// inert button never changes size) and SKIN (colour / border-colour / hover — applied
// only when interactive). `cn` is plain clsx (no tailwind-merge), so the inert override
// and a variant SKIN must be *mutually exclusive*, never layered: layering them leaves
// conflicting utilities (e.g. `bg-signal` vs `bg-transparent`) to resolve by CSS source
// order, which can render a disabled button looking enabled. Likewise, `sm`/`md` SHAPE
// are mutually exclusive (one is chosen), so padding is never double-emitted either.
const VARIANT_SHAPE: Record<ActionSize, Record<ActionVariant, string>> = {
  md: {
    primary: "px-[18px] py-2",
    ghost: "border px-[18px] py-2",
    text: "px-1 py-1",
    // Destructive is *marked*, then confirmed — a ring, never a flooded red fill.
    destructive: "border px-[18px] py-2",
  },
  sm: {
    primary: "px-3 py-1",
    ghost: "border px-3 py-1",
    text: "px-1 py-0.5",
    destructive: "border px-3 py-1",
  },
};

const VARIANT_SKIN: Record<ActionVariant, string> = {
  // The only routinely-coloured surface — so there is rarely more than one per zone.
  primary: "bg-signal text-ground hover:bg-signal-strong",
  ghost: "border-[color:var(--hairline-strong)] text-text hover:border-text",
  text: "text-text hover:text-signal",
  destructive: "border-state-fail text-state-fail hover:bg-state-fail/10",
};

// The inert (disabled / pending) skin — *replaces* the variant SKIN, never layers over it.
const INERT_SKIN =
  "hatch border-[color:var(--hairline)] bg-transparent text-text-faint hover:bg-transparent";

export function Action({
  variant = "primary",
  size = "md",
  pending = false,
  className,
  children,
  ...props
}: ActionProps) {
  const inert = pending || props.disabled;
  return (
    <button
      type={props.type ?? "button"}
      {...props}
      disabled={inert}
      className={cn(
        BASE,
        TEXT_SIZE[size],
        VARIANT_SHAPE[size][variant],
        inert ? INERT_SKIN : VARIANT_SKIN[variant],
        className,
      )}
    >
      {children}
      {variant === "text" && <span aria-hidden>→</span>}
    </button>
  );
}

export const ActionGhost = (props: Omit<ActionProps, "variant">) => <Action variant="ghost" {...props} />;
export const ActionText = (props: Omit<ActionProps, "variant">) => <Action variant="text" {...props} />;
export const ActionDestructive = (props: Omit<ActionProps, "variant">) => (
  <Action variant="destructive" {...props} />
);
