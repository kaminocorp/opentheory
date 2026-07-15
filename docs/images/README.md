# Images

Shared raster assets for the README and for link previews. The brand *mark* itself
is documented separately in [`frontend/public/brand/README.md`](../../frontend/public/brand/README.md).

## Files

| File | Size | Used by |
|---|---|---|
| `cover.jpg` | 2000×667 | README hero banner; the art band of the social card |
| `social-card.jpg` | 1280×640 | GitHub social preview + `og:image` (copied to `frontend/public/og.jpg`) |
| `social-card.html` | — | the **source** for `social-card.jpg` — edit this, then re-render |
| `x-launch-ledger.png` | 1600×900 | README ledger graphic (illustrative mockup, not a screenshot) |
| `source/` | — | original full-resolution art, kept as provenance |

**Why JPEG here and PNG for `x-launch-ledger`.** `x-launch-ledger.png` is a UI mockup —
flat fills, hard edges, text — which PNG stores losslessly *and* compactly. `cover.jpg`
is a painting: gradients, grain, a starfield. As PNG it is 2.2 MB; at JPEG q88 it is
329 KB and visually identical. GitHub caps the social-preview upload at **1 MB**, so
this is a constraint, not a preference.

## Regenerating the social card

`social-card.html` composes `./cover.jpg` with the brand mark and wordmark using the
OpenTheory Console tokens. It is rendered at 2× and downsampled so the type is
supersampled:

```bash
cd docs/images
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
  --screenshot=/tmp/card@2x.png --window-size=1280,640 --virtual-time-budget=6000 \
  social-card.html
magick /tmp/card@2x.png -resize 1280x640 -strip -quality 90 social-card.jpg
cp social-card.jpg ../../frontend/public/og.jpg      # keep the live app's og:image in sync
```

The mark geometry in `social-card.html` is a copy of `brand/mark-dark.svg`. If the mark
ever changes, update it here too — this file is outside the `brand-mark.tsx` source of
truth and will not follow automatically.

## Where each surface gets its preview image

| Surface | Mechanism | Needs a human? |
|---|---|---|
| **The live app** (`opentheory.vercel.app`) | `og:image` from `frontend/public/og.jpg`, wired in `src/app/layout.tsx` | no — ships with a deploy |
| **The GitHub repo URL** | GitHub's own *Social preview* setting | **yes — see below** |

> [!IMPORTANT]
> **GitHub does not read a social image from the repository.** No file, path, or
> metadata in this repo can set it. It must be uploaded once, by hand, at
> **Settings → General → Social preview → Upload an image**, using
> `docs/images/social-card.jpg`. It persists until replaced, so this is a one-time
> step — but a fresh fork or a new repo starts with the default grey card again.

Set `NEXT_PUBLIC_SITE_URL` to the production origin so the app's `og:image` resolves to
a stable absolute URL rather than a per-deployment Vercel hostname. Open Graph consumers
do not resolve relative URLs.
