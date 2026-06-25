# Frontend — Kamino Console · Phase D1 (Design Foundation) — Completion

> Implements **Phase D1** of `docs/executing/frontend-kamino-console-redesign.md`:
> the substrate (tokens, fonts, the measured field) and the `console/` primitive
> library that every later phase (D2–D5) re-skins against. Presentation-layer only
> — **zero** backend / schema / API / data-flow change, and no existing
> query/mutation/route touched.

**Status:** complete. `typecheck` / `lint` / `build` all green; the Decision-4
opacity-modifier contract is verified in the generated CSS; the styleguide renders
the full primitive set server-side without error.

**Version:** provisional. The plan suggests a dedicated `0.8.0` for the whole
D1–D6 conversion (or folding under the next UI release) — **deferred to merge
time**, so this doc is named by phase, not version. The `docs/changelog.md` entry
is intentionally **not** written yet; per the plan, the changelog is added at the
end (D6), or per-phase once a version is assigned.

---

## What landed, where, and why

### 1. Token layer — `tailwind.config.ts` (replaced `theme.extend`)

The entire old palette (`ink`/`paper`/`line`/`signal`-teal/`ember`) and
`boxShadow.panel` are gone. Colours are now wired through the **channel pattern**:

```ts
const ch = (v: string) => `rgb(var(${v}) / <alpha-value>)`;
colors: { ground: ch("--ground"), panel: ch("--panel"), text: ch("--text"), …,
          signal: ch("--signal"), "state-ok": ch("--state-ok"), … }
```

**Why the channel pattern is non-negotiable (Decision 4).** Tokens are stored in
`:root` as *space-separated RGB channels* (`--panel: 22 21 19`), not finished
`rgb()`/`rgba()` strings. That is the only form that lets Tailwind substitute
`<alpha-value>`, which is what keeps `text-text/70`, `bg-signal/10`, etc. working.
If a token is ever "simplified" to a complete colour string, every `/opacity`
utility across the codebase breaks **silently** (no error — the utility just stops
generating). This is the single biggest risk in the whole conversion, so it is
verified explicitly (see *Verification*).

Also added: `borderRadius` → `built`(0) / `alive`(999) / `inset`(2) so the
shape-grammar law is expressible as `rounded-built` / `rounded-alive`;
`borderWidth.hairline` (0.5px); `fontFamily` → the Plex CSS variables.

### 2. Substrate — `src/app/globals.css` (replaced wholesale)

- **`:root` token block** — the structural ramp + signal + state tokens as
  channels (per above), plus the **alpha-native overlays** (`--hairline`,
  `--hairline-strong`, `--hairline-lit`, `--tick`, `--field-line`,
  `--field-major`) kept as ready-made `rgba()` because they are inherently
  translucent and are consumed in component CSS / arbitrary values, never as
  Tailwind colour utilities. Proportion + radius scalars round it out.
- **`color-scheme: dark`** and a warm-obsidian `body` ground (`rgb(var(--ground))`,
  `#0D0C0B` — never `#000`).
- **The measured field (§2.1)** composed once into `--field-image` /
  `--field-size` / `--field-position` and reused by both `body` and the
  `.field-surface` class (single source of truth — the shell `<main>` in D2 and the
  styleguide reuse it without duplicating the gradients):
  - 8px **minor** grid + 64px **major** grid as layered `linear-gradient`s at very
    low alpha.
  - A 4px **registration crosshair** (`+`) at every major intersection, via a 64px
    SVG data-URI tile. *Implementation note:* the crosshair tile is centred at
    (32,32) and the **major grid is offset by 32px**, so the crosses land exactly
    on the major intersections without the tile-corner clipping problem. 32 is 4u,
    so everything still aligns to the 8px field.
  - **Grain** (`body::before`) — a desaturated `feTurbulence` SVG at ~3.5% opacity,
    so the obsidian reads as *material*, not flat fill.
  - **Deep-field vignette** (`body::after`) — a barely-there radial edge darkening.
  - Both texture layers are `position: fixed; z-index: -1; pointer-events: none`,
    so opaque bays paint over them and the texture only shows in the open field
    (gutters, headers, empty states) — exactly the blueprint's "table the
    instruments sit on, not a texture on the instruments."
- **Global type rendering** — `font-synthesis: none`, antialiasing,
  `optimizeLegibility`, and global `font-variant-numeric: tabular-nums` (figures
  never reflow as they tick). `text-wrap: pretty` on prose, `balance` on headings.
- **`@layer components`** for the verbose primitives that don't belong as inline
  utilities: `.bay` (the recess box-shadow recipe — inset top highlight + lower
  shadow lip), `.bay-chamfer` (the single 10px top-right clip), `.hatch` (inert
  "coming soon" fill), `.field-input` (square panel fill + the 2px `--signal` focus
  edge tick), `.field-surface`, and `.console-link`.
- **Liveness motion + the reduced-motion freeze** — `@keyframes anim-pulse`
  (1.6s opacity) and `anim-breathe` (≈3s opacity/scale) with `.anim-pulse` /
  `.anim-breathe` utilities, then a `@media (prefers-reduced-motion: reduce)` block
  that freezes them and globally neutralises animations/transitions. This is the
  block every later phase appends its own motion to.
- **`@media (max-width: 768px)`** drops the grid lines (grain + ground remain), the
  §4.3 smallest-screen rule.

### 3. Fonts — `src/app/layout.tsx`

IBM Plex Sans (400/500) and IBM Plex Mono (400/500) loaded via
`next/font/google`, exposed as `--font-plex-sans` / `--font-plex-mono`, and applied
on `<html>`. Self-hosted by `next/font` (no third-party request at runtime, no
FOUT, size-adjust fallback to minimise layout shift). **The provider tree
(`QueryProvider` → `AuthProvider` → `DevActorProvider`) is untouched.** This is what
makes the mono/sans semantic split (§3.1) expressible everywhere downstream.

### 4. The primitive library — `src/components/console/*`

One thin component per piece of the shape grammar, so the grammar is defined once
and D2–D5 only compose. All consume the tokens above; none carry domain logic.

| File | Exports | Blueprint |
|---|---|---|
| `state.ts` | `STATE_META`, `StateTone` | §5.1/§9.3 — the shared glyph+colour map every status collapses onto (`ok ✓`, `run ●`, `warn ▲`, `fail ■`, `mute ▣`, `faint ·`, `signal ●`) |
| `bay.tsx` | `Bay`, `BayHeader` | §2.2/§4.2 — the square recessed surface (`bracketed`/`chamfer`/`density` props) + the fixed 6u header |
| `readout-label.tsx` | `ReadoutLabel` | §3.2 — the one sanctioned all-caps (mono 11/500/0.14em) |
| `registration.tsx` | `RegistrationBrackets`, `RegistrationBand` | §2.2/§2.3 — the 12px corner L-marks + the `│ ‧ ‧ ‧ │` tick-fret |
| `status-pill.tsx` | `StatusPill` | §5.1 — round, mono, **glyph + label** (honest, grayscale-safe) |
| `live-dot.tsx` | `LiveDot` | §5.1 — 8px round, optional opacity pulse |
| `action.tsx` | `Action`, `ActionGhost`, `ActionText`, `ActionDestructive` | §5.7 — the round button registers; destructive is a ring, never a flooded fill; disabled/pending = hatched inert |
| `input.tsx` | `Input`, `Select`, `Textarea` | §5.8 — square console fields, `mono` prop for the data/prose split, focus edge tick |
| `icon.tsx` | `Icon` | §7/Decision 2 — the lucide wrapper enforcing stroke 1.25 (1.5 ≤16px), `currentColor`, monotone |
| `brand-mark.tsx` | `BrandMark` | §8 — the interim mark (see Decisions) |
| `awaiting-state.tsx` | `AwaitingState` | §5.9 — "the mark holds the frame" (breathe/loading, steady/empty/error) |
| `index.ts` | barrel | one import path: `@/components/console` |

Supporting: `src/lib/cn.ts` — a dependency-free className joiner (no `clsx` /
`tailwind-merge` added; the primitives never produce conflicting classes).

### 5. Verification aid — `src/app/styleguide/page.tsx`

An internal page rendering every primitive in every state on the measured field,
including a dedicated **opacity-modifier probe** and a **state-glyph legend** for
the grayscale test. See the routing decision below.

---

## Decisions made during D1 (and their rationale)

1. **Brand mark → an interim original thin-line SVG, isolated in `BrandMark`.**
   The blueprint (§5.9/§8) wants the Kamino emblem (`brand/emblem-white.png`),
   which does not exist in this repo, and the app previously used an off-language
   `FlaskConical` lucide glyph. Rather than ship a broken `<img>` or keep the wrong
   mark, `BrandMark` draws an original lantern/key glyph **in the §7 drawing
   language** (`currentColor` stroke, 1.25, no fills). It is the only place the mark
   is defined, so dropping in the real emblem later is a **one-file change** —
   exactly the isolation the plan asked for. *Open item:* obtain/agree the real
   emblem before D6.

2. **Styleguide route → `styleguide/`, gated by `NEXT_PUBLIC_AUTH_DEV`, NOT
   `_styleguide/`.** The plan's literal path `app/_styleguide/page.tsx` would
   **silently never route**: the App Router treats `_`-prefixed folders as
   *private* and excludes them from the route tree, which would make the page
   unreachable and the D1 DoD ("the styleguide page renders") unverifiable. So it
   is a real `styleguide` route that calls `notFound()` unless
   `NEXT_PUBLIC_AUTH_DEV === "true"` — viewable in dev, harmless (404) in prod.
   **View it:** `NEXT_PUBLIC_AUTH_DEV=true npm run dev` → `/styleguide`. D6 may
   delete it.

3. **`Select` defaults to `mono`.** A `<select>` almost always renders an
   enum/machine token (funding `source`, validation outcome, branch status), which
   is Mono by the §3.1 split; `Input`/`Textarea` default to Sans (prose). All three
   accept a `mono` override.

## Deviations from the blueprint letter (faithful in spirit)

- **Crosshair alignment via a 32px major-grid offset** (rather than tile-corner
  quarters) — a cleaner construction that avoids SVG clipping while still landing
  crosses on major intersections, all still on the 8px field. Visual result is
  identical.
- **Grain rendered as a low-opacity light noise layer**, not literal `multiply`
  blend — `multiply` on warm obsidian is essentially invisible; the intent ("reads
  as material, not flat fill") is met with a faint additive speckle at ~3.5%.
- **Registration brackets drawn at 1px** (Tailwind `border`) in `--hairline-strong`
  rather than 0.5px — brackets are an emphasis mark; the defining constant is the
  12px arm length, which is exact.

Each is noted here so a reviewer can spot the intentional-vs-accidental line.

## Explicitly NOT touched (scope discipline)

The existing surfaces (`page.tsx`, `project-workspace.tsx`, the workspace panels,
`project-card.tsx`, auth menu, dev switcher) still reference the **removed** legacy
utilities (`bg-paper`, `text-ink`, `border-line`, `ember`, `shadow-panel`). Those
classes now generate no CSS, so those screens render **transitional** (light
panels on the dark field) until D2–D5 convert them — this is the planned,
acceptable D1 end-state ("the rest of the app still loads … looks transitional").
No query key, mutation, `useActingIdentity`/`useAuth` call, route, or read-schema
field was altered.

---

## Verification (reproduced, not asserted)

- **`npm run typecheck`** → clean.
- **`npm run lint`** → clean.
- **`npm run build`** → success; all 6 routes generated; the Plex fonts fetched
  and self-hosted at build time without error.
- **Decision-4 opacity contract — verified in the emitted CSS** (the one check a
  green build does *not* prove, since Tailwind drops unknown utilities silently).
  Grepping the production CSS:
  - `text-text/70` → `rgb(var(--text)/.7)`
  - `bg-signal/10` → `rgb(var(--signal)/.1)`
  - `bg-state-ok/15` → `rgb(var(--state-ok)/.15)`
  - `rounded-built` → `border-radius:var(--r-built)`; `rounded-alive` →
    `var(--r-alive)`. The channel wiring works end-to-end. (Also observed: the
    legacy components' `bg-signal/5` / `bg-signal/50` now resolve to the **crimson**
    channels — confirming D3–D5 token swaps will be near-mechanical.)
- **Styleguide renders** — prerendering `/styleguide` with the gate open produces
  HTML containing the primitive sections ("Primitive styleguide", "Status pills",
  "State legend"), i.e. every primitive renders server-side without a runtime
  throw.
- **Grayscale safety by construction** — `StatusPill` and the `AwaitingState` error
  carry **glyph + label**, and the state legend makes the glyph set explicit, so
  meaning does not rely on hue. (A full visual desaturation pass is a D6 release
  gate; the primitives are built to pass it.)

## What D2 can now rely on

- `@/components/console` exports the whole shape grammar; `.field-surface` is ready
  for the shell `<main>`; the proportion tokens (`--rail`, `--header`, `--gutter`)
  are defined for the header + command rail; the reduced-motion block is ready to
  receive the menu/entrance motion. The `Icon` wrapper is the single seam for the
  rail's nav glyphs, and `BrandMark` is the single seam for the header lockup.
