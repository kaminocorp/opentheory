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

const VARIANT: Record<ActionVariant, string> = {
  // The only routinely-coloured surface — so there is rarely more than one per zone.
  primary: "bg-signal px-[18px] py-2 text-ground hover:bg-signal-strong",
  ghost: "border px-[18px] py-2 text-text hover:border-text",
  text: "px-1 py-1 text-text hover:text-signal",
  // Destructive is *marked*, then confirmed — a ring + text, never a flooded red fill.
  destructive: "border border-state-fail px-[18px] py-2 text-state-fail hover:bg-state-fail/10",
};

export function Action({ variant = "primary", pending = false, className, children, ...props }: ActionProps) {
  const inert = pending || props.disabled;
  return (
    <button
      type={props.type ?? "button"}
      {...props}
      disabled={inert}
      className={cn(
        BASE,
        VARIANT[variant],
        // ghost/destructive draw their ring in hairline-strong via inline border-color
        variant === "ghost" && "border-[color:var(--hairline-strong)]",
        inert && "hatch border-[color:var(--hairline)] bg-transparent text-text-faint hover:bg-transparent",
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
