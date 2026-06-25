import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/cn";

export type ActionVariant = "primary" | "ghost" | "text" | "destructive";

interface ActionProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ActionVariant;
  /** In-flight state: renders the inert hatched fill (like `disabled`). */
  pending?: boolean;
  children: ReactNode;
}

// Round, always (§5.7) — round is the alive / actionable affordance. Buttons
// never move, scale, or cast shadows; only opacity/colour transitions.
const BASE =
  "inline-flex items-center justify-center gap-1.5 rounded-full font-sans text-[13px] font-medium transition-colors disabled:cursor-not-allowed";

// Split per variant into SHAPE (padding + border *presence* — always applied, so an
// inert button never changes size) and SKIN (colour / border-colour / hover — applied
// only when interactive). `cn` is plain clsx (no tailwind-merge), so the inert override
// and a variant SKIN must be *mutually exclusive*, never layered: layering them leaves
// conflicting utilities (e.g. `bg-signal` vs `bg-transparent`) to resolve by CSS source
// order, which can render a disabled button looking enabled.
const VARIANT_SHAPE: Record<ActionVariant, string> = {
  primary: "px-[18px] py-2",
  ghost: "border px-[18px] py-2",
  text: "px-1 py-1",
  // Destructive is *marked*, then confirmed — a ring, never a flooded red fill.
  destructive: "border px-[18px] py-2",
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

export function Action({ variant = "primary", pending = false, className, children, ...props }: ActionProps) {
  const inert = pending || props.disabled;
  return (
    <button
      type={props.type ?? "button"}
      {...props}
      disabled={inert}
      className={cn(
        BASE,
        VARIANT_SHAPE[variant],
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
