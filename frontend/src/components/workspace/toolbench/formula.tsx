import { cn } from "@/lib/cn";

/**
 * The single render seam for a mathematical expression (Phase 7, v1).
 *
 * Instruments emit exact SymPy strings — "sqrt(2)", "pi/2", "x**2", "5" — which are *data*, not
 * prose. v1 renders them as a monospace value chip: on-brand with the console's data/token family
 * (design_blueprint §3.1, where every measured value is mono), and — crucially for a provenance
 * ledger — incapable of mis-rendering (a *wrong* formula recorded against a result is worse than a
 * plainly-typeset one).
 *
 * Every drive and show surface routes its expressions through here. That makes render strategy the
 * one thing this component owns: a v2 that prefers a server-supplied `latex` field (SymPy's
 * authoritative `sympy.latex()`, an additive backend change) and typesets it with KaTeX is a change
 * to THIS FILE ALONE — no call site moves.
 */
export function Formula({ expr, className }: { expr: string; className?: string }) {
  return (
    <code className={cn("font-mono text-[13px] tabular-nums text-text", className)}>{expr}</code>
  );
}
