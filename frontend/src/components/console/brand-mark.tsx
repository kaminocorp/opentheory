interface BrandMarkProps {
  size?: number;
  className?: string;
}

/**
 * The Kamino mark (§8) — the constant that, with §2's structure, still says
 * "Kamino" when `--signal` is re-themed.
 *
 * INTERIM ASSET (D1 decision): the blueprint wants the emblem PNG
 * (`brand/emblem-white.png`), which does not exist in this repo. Rather than ship
 * a broken image or keep the off-language `FlaskConical`, this is an original
 * thin-line lantern/key glyph drawn inline in the §7 drawing language
 * (`currentColor` stroke, 1.25, no fills). It is isolated in this one component so
 * swapping in the real emblem later is a single-file change. Colour comes from a
 * `text-*` class on the element (it strokes in `currentColor`).
 */
export function BrandMark({ size = 24, className }: BrandMarkProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.25}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={className}
    >
      {/* key bow */}
      <circle cx="12" cy="5" r="2.5" />
      <path d="M12 7.5V9.5" />
      {/* lantern body (a measured diamond aperture) */}
      <path d="M12 9.5L17 15L12 20.5L7 15L12 9.5Z" />
      {/* inner spark */}
      <path d="M12 13V17" />
    </svg>
  );
}
