# OpenTheory — Design System

> The design language for the OpenTheory workspace, as of the `0.15.0` overhaul. This file
> describes what is built; the tokens in `frontend/src/app/globals.css` are the source of truth
> and this file is updated to match. (The previous "OpenTheory Console" language — measured-field
> grid, registration brackets, chamfers, all-caps mono kickers — was retired in `0.15.0`; see
> `docs/completions/design-overhaul-0.15.0.md` for the rationale and the full delta.)

The feel in one sentence: **a quiet, minimalist dark surface system — flat neutral panels
separated by one step of lightness and a low-alpha border, soft radii, sentence-case sans
typography with mono reserved for data, and a single crimson accent used sparingly.**

Calm, legible, uncluttered. The reference point is contemporary product design of the
OpenAI/Linear school: the interface recedes, the research content carries the page.

---

## 0. The two laws

1. **It must survive grayscale.** No state may be carried by colour alone. Every status pairs a
   glyph + label with its colour; the active tab/row is marked by weight or a structural edge as
   well as the accent. Desaturate the UI and nothing becomes ambiguous.
2. **Honesty over comfort.** Failure renders with the same weight and prominence as success —
   equal size, equal contrast, never buried, never softened. `refuted` and `undecided` must be
   as legible as a pass; an undecided result never *reads* as a pass. Honest empty/error/loading
   states, no vanity metrics.

These two survived the re-skin untouched, because they are product law, not styling.

---

## 1. Tokens (globals.css)

Structural ramp and state colours are stored as space-separated RGB *channel triplets*
(`--panel: 24 24 24`) consumed via `rgb(var(--x) / <alpha-value>)` in `tailwind.config.ts` —
this is what keeps Tailwind opacity modifiers (`text-text/70`, `bg-signal/10`) working. Do not
"simplify" a token to a finished `rgb()` string.

### 1.1 Structural ramp — neutral near-black

```
--ground:    #101010   /* app background */
--panel:     #181818   /* card surface */
--panel-2:   #202020   /* nested / hover surface */
--text:      #ECECEC   /* primary */
--text-soft: #B4B4B4   /* prose */
--text-mute: #8E8E8E   /* secondary, labels */
--text-faint:#6E6E6E   /* timestamps, ambient */
```

Hierarchy comes from **one step of lightness per nesting level** (ground → panel → panel-2),
never from texture, shadow stacks, or ornament. Avoid nesting more than two surfaces.

### 1.2 Borders

```
--hairline:        rgba(255,255,255,0.08)   /* default borders, dividers */
--hairline-strong: rgba(255,255,255,0.14)   /* interactive outlines, emphasis */
```

Borders are 1px, low-alpha white. `--hairline-lit` and `--tick` remain as legacy aliases of
`-strong`/`0.12` and should not be used in new code.

### 1.3 Radius

```
--r-card:    12px   /* card surfaces (.bay), menus */
--r-control: 8px    /* inputs, tiles, list rows, code blocks */
--r-alive:   999px  /* pills, buttons, dots, avatars */
--r-inset:   6px    /* the smallest chips */
--r-built:   8px    /* legacy alias of --r-control (rounded-built call sites) */
```

Everything is softly rounded. Buttons and status pills are full pills.

### 1.4 Signal — exactly one, swappable, sparing

```
--signal:        #C95A5A   /* crimson. SWAPPABLE — the one brand colour. */
--signal-strong: #D98A8A   /* hover / emphasis */
```

Appears only on: the primary action per zone, the active-tab underline, the selected-row edge
tick, the focus ring, and the rare live marker. If two signal elements compete, one is wrong.

### 1.5 State — functional, independent of brand

```
--state-ok:   #5E8C73   /* passed / healthy */
--state-run:  #6F93A8   /* running / in-progress */
--state-warn: #C8923E   /* warning / degraded / undecided */
--state-fail: #C4403A   /* failed / refuted — deliberately distinct from --signal */
```

Glyph vocabulary (`components/console/state.ts`): `✓ ok · ● run · ▲ warn · ✕ fail · ○ mute`.
State colour is always secondary to glyph + label + position.

---

## 2. Typography

Two families, unchanged: **IBM Plex Sans** for everything a human reads, **IBM Plex Mono** for
data only — hashes, ids, formulas, code, machine tokens (instrument names, models), and tabular
numerics. The mono surface area was deliberately shrunk in `0.15.0`: labels, captions, statuses,
and navigation are sans now.

- **No all-caps, no letterspacing.** Sentence case everywhere; enum values render through CSS
  `capitalize`. Hierarchy comes from **weight (500 vs 400) and the text ramp**, not treatment.
- Body 14px / 1.6. Card titles 14px/500 `--text`. Section/field labels 13px/500 `--text-soft`
  (`ReadoutLabel`). Small meta 12px `--text-mute`, ambient 11px `--text-faint`.
- `font-variant-numeric: tabular-nums` globally — figures never reflow as they tick.
- `text-wrap: pretty` on prose, `balance` on headings.

---

## 3. Surfaces & components (`components/console/`)

- **`Bay`** (`.bay`) — the card: `--panel`, 1px `--hairline` border, 12px radius, flat. No inset
  shadows, no corner brackets, no chamfer. `BayHeader` = 48px header (sans title + muted count +
  actions), optional `divider` hairline.
- **`Action`** — pill buttons. Primary: `--signal` fill (the only routinely coloured surface).
  Ghost: hairline-strong ring, hover `bg-white/5`. Text: muted → text. Destructive: state-fail
  ring, never a flooded fill. Disabled/pending: faint text on `bg-white/4` (the hatch texture is
  retired). Buttons never move, scale, or cast shadows.
- **`Input`/`Textarea`/`Select`** (`.field-input`) — quiet `rgba(255,255,255,0.02)` fill, 1px
  border, 8px radius; **focus brightens the border** (no glow, no edge tick). `mono` prop per the
  data/prose split. Accessible-name fallback from placeholder is unchanged.
- **`StatusPill`** — pill, sans 12px capitalized label + state glyph, `bg-white/3`. A failed pill
  is never dimmer or smaller than a passed one.
- **`MetricReadout`** — nested tile (8px radius, `bg-white/2`), sans muted label, mono tabular
  value.
- **`AwaitingState`** — the mark still holds the frame: loading runs the diagonal cascade;
  empty/error hold steady; error label at full `--state-fail` weight. Labels are sans sentence
  case.
- **`Modal`** — `.bay` surface lifting over a scrim; sans title; behaviour (focus trap, Escape,
  scroll lock) unchanged.
- **`.menu`** — popover surface: `--panel-2`, strong hairline, 12px radius, soft single shadow.
- **`Icon`** — lucide wrapper, stroke 1.5 (1.75 at ≤16px), `currentColor`, no fills.

### Shell

Header: 48px, `bg-ground/90` + backdrop-blur + bottom hairline; brand lockup (with the click
"jingle" easter egg) left, search pill centre, bell + account right. Nav rail: icon column with
**filled rounded tiles** for hover/active (`bg-white/4` / `bg-white/7`) — no edge ticks, no
pulsing dots. Tabs (`ProjectTabs`): sans labels with a 2px `--signal` bottom edge on the active
tab (structural, so it survives grayscale).

### Selection & log rows

List rows are 8px-radius `--panel-2` tiles; the selected row keeps its 2px `--signal` left edge
tick. Checkpoint entries keep a neutral left rule. Dropped/skipped agent steps use a dashed
hairline border (the hatch fill is retired).

---

## 4. Motion

Quiet and meaningful only: the live-dot opacity pulse, the brand-mark loading cascade and
one-shot assemble, menu fade+4px, and a 0.3s fade+4px stagger for entering grids. No glow, no
bounce, no parallax. **Reduced motion is mandatory** — every animation freezes to a steady
end-state under `prefers-reduced-motion: reduce`; register any new animation in that block.

---

## 5. Accessibility

- Keyboard focus: a visible 2px `--signal` outline on `:focus-visible`, never removed.
- The tablist keeps the full WAI-ARIA pattern (roving tabindex, arrow keys).
- Status is glyph + label + position first, colour second (law #1).
- Muted text tiers were *lightened* in `0.15.0` (`#8E8E8E`/`#6E6E6E`) for contrast.

---

## 6. Checklist (extending the system)

1. To re-skin, change `--signal` only.
2. New surfaces: pick a ramp step + hairline + the right radius token. No new textures, shadows,
   or borders heavier than 1px.
3. Sans for words, mono for data. No all-caps, no letterspacing.
4. Map new statuses onto the existing state tones + glyphs; never invent colours.
5. Run the grayscale test and the honesty audit (§0) before shipping.
6. Register every new animation in the reduced-motion block.
