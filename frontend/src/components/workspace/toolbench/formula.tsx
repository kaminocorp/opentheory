import katex from "katex";
import "katex/dist/katex.min.css";

import { cn } from "@/lib/cn";

/**
 * The single render seam for a mathematical expression (Phase 7, v1).
 *
 * Instruments emit exact SymPy strings — "sqrt(2)", "pi/2", "x**2", "5" — which are *data*, not
 * prose. When the backend supplies an additive `*_latex` companion (SymPy's authoritative
 * `sympy.latex()`), typeset it with KaTeX; on error or absence, fall back to the monospace SymPy
 * string so provenance is never misrepresented.
 *
 * Every drive and show surface routes expressions through here — render strategy changes stay in
 * this file alone.
 */
export function Formula({
  expr,
  latex,
  className,
}: {
  expr: string;
  latex?: string | null;
  className?: string;
}) {
  const trimmed = latex?.trim();
  if (trimmed) {
    try {
      const html = katex.renderToString(trimmed, { throwOnError: false, output: "html" });
      return (
        <span
          className={cn(
            "inline-block max-w-full overflow-x-auto [&_.katex]:text-[length:inherit] [&_.katex]:text-inherit",
            className,
          )}
          // KaTeX HTML is trusted server-side sympy.latex output; throwOnError:false prevents throws.
          dangerouslySetInnerHTML={{ __html: html }}
        />
      );
    } catch {
      // Bad latex must not white-screen the panel — fall through to monospace.
    }
  }

  return (
    <code className={cn("font-mono text-[13px] tabular-nums text-text", className)}>{expr}</code>
  );
}