interface BrandMarkProps {
  size?: number;
  className?: string;
  /**
   * When set, the four nodes light in a diagonal cascade (a signal travelling up
   * the staircase) — the §5.9 loading liveness. Off by default so the header and
   * static lockups render a steady mark. Frozen under `prefers-reduced-motion`.
   */
  animated?: boolean;
}

/**
 * The OpenTheory mark — four solid shapes stepping up a diagonal
 * (circle → link → square → circle), a research graph compounding from
 * lower-left to upper-right.
 *
 * Drawn natively (no raster asset) so it stays crisp at every size and each node
 * is individually addressable for motion. Fills in `currentColor`, so colour
 * comes from a `text-*` class on the element — off-white on the console ground,
 * ink on a light surface. The geometry is the single source of truth shared with
 * `public/brand/mark*.svg` and the generated favicons (viewBox `170 150 920 920`,
 * a tight centred crop of the original 1254² canvas).
 */
export function BrandMark({ size = 24, className, animated = false }: BrandMarkProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="170 150 920 920"
      fill="currentColor"
      aria-hidden
      className={className}
    >
      {/* DOM order is the diagonal order (BL → TR), so the cascade reads as a
          wave climbing the staircase via nth-child delays (globals.css §6). */}
      <g className={animated ? "mark-cascade" : undefined}>
        <circle cx="313" cy="873" r="84" />
        <rect x="405" y="640" width="252" height="132" rx="66" />
        <rect x="661" y="455" width="162" height="162" />
        <circle cx="942" cy="351" r="84" />
      </g>
    </svg>
  );
}
