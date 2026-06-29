# OpenTheory brand mark

Four solid shapes stepping up a diagonal — **circle → link → square → circle** —
a research graph compounding from lower-left to upper-right.

The mark is **drawn natively** (geometry, not a raster trace), so the React
component, the SVGs here, and the generated favicons all share one source of
truth: viewBox `170 150 920 920` (a tight, centred crop of the original 1254²
canvas). Palette is the Kamino tokens, not raw black/white:
**`#0D0C0B`** (warm obsidian, on light) and **`#ECEAE6`** (off-white, on dark).

## Where the mark lives

| Use | Asset |
|-----|-------|
| In-app logo + loading animation | `components/console/brand-mark.tsx` (`<BrandMark animated? />`, fills `currentColor`) |
| Browser favicon (theme-adaptive) | `src/app/icon.svg` |
| Safari/iOS home screen | `src/app/apple-icon.png` (180², white on obsidian) |
| Legacy favicon | `src/app/favicon.ico` (16/32/48, white on obsidian) |

## Files in this folder

- `mark.svg` — adaptive (ink on light, off-white on dark) — use when the surface theme is unknown.
- `mark-dark.svg` — fixed off-white, for dark backgrounds.
- `mark-light.svg` — fixed obsidian, for light backgrounds.
- `mark-512-*.png`, `mark-1024-*.png` — transparent rasters (`-dark` = white shapes, `-light` = obsidian shapes) for slides, social, README embeds.
- `source/` — the original provided PNGs (solid backgrounds), kept as provenance.

To regenerate the rasters/favicons, re-run the generator in the commit that added
them (PIL, supersampled 4× → LANCZOS). Editing the geometry means updating the
four shapes in `brand-mark.tsx` and the three SVGs in lockstep.
