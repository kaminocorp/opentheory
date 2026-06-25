import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/cn";

interface IconProps {
  /** A lucide icon component, e.g. `import { GitBranch } from "lucide-react"`. */
  icon: LucideIcon;
  /** Pixel size (drives the stroke-weight rule below). Default 18. */
  size?: number;
  className?: string;
  "aria-label"?: string;
}

/**
 * The single icon wrapper (Decision 2). Keeps `lucide-react` but constrains every
 * glyph to the drawing language (§7): `currentColor` stroke (set the colour with a
 * `text-*` class on the wrapper), no fills, mono-tone, and a hairline-matched
 * stroke weight — 1.25, bumped to 1.5 at ≤16px so small glyphs stay legible on the
 * dark ground. Isolating icons here makes a future swap to in-repo SVGs one file.
 */
export function Icon({ icon: LucideGlyph, size = 18, className, ...rest }: IconProps) {
  const strokeWidth = size <= 16 ? 1.5 : 1.25;
  return (
    <LucideGlyph
      size={size}
      strokeWidth={strokeWidth}
      className={cn("shrink-0", className)}
      aria-hidden={rest["aria-label"] ? undefined : true}
      {...rest}
    />
  );
}
