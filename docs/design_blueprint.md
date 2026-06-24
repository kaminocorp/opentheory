# Kamino Console Design System

> One design language for every Kamino **product** — Hyperdrive first, and anything operational built next. This is the *engine room*, deliberately distinct from the marble marketing website (the *monument*): same company, opposite posture. The site is a thing you stand before; the console is a thing you work inside.
>
> This file is the portable contract. Copy it into any Kamino product repo and the rules below recreate the look without guesswork. Once a product implements it, that product's `src` tokens become the source of truth and this file is updated to match — but the **structural signature** in §2 is fixed and travels unchanged to every platform.

The feel in one sentence: **a warm-obsidian command bridge — a faint measured field under hairline instrument bays, registration-bracket precision, Plex Mono readouts and Plex Sans prose, where square means built and round means alive, lit by structure not glow, and themed by a single colour used seldom.**

The reference image: *operating a Star Destroyer from the cockpit.* Austere, geometric, powerful, uncluttered — authority without noise. Cutting-edge command centre for developers, engineers and researchers. Never busy, never cyberpunk-neon, never warm-and-soft.

---

## 0. The one law: it must survive grayscale

This system will run across multiple platforms, and **different platforms may carry different primary colours**. Therefore colour cannot be the identity. The identity is **form** — substrate, proportion, shape grammar, line language, type, motion.

> **The grayscale test.** Desaturate the entire UI. If it is no longer recognizably Kamino, the design is wrong. Every rule in this document is written to pass that test. Colour is the *last* section (§9), not the first, and it is the only layer a platform is allowed to re-theme.

What we carry forward from Kamino (the website), translated for a dark instrument:

| Website value (marble) | Console translation (obsidian) |
|---|---|
| "Carved, not glowing" — letterpress emboss | **Recessed instrument bays** — panels set *into* the console, lit by a hairline highlight + shadow lip |
| Paper grain ("printed, not rendered") | **Measured field** — a faint CAD/graph-paper substrate + fine grain |
| Greek-key `Meander` fret | **Registration band** — a measured tick-fret divider/underline |
| Breathing-emblem load state (`EmblemImage.vue`) | **Awaiting-data / empty states** — the mark holds the frame |
| Hairlines, not boxes; one accent, seldom | Unchanged. Hairlines and a single seldom signal |
| "Gravity, not hum" | Motion only ever means *something changed*. Never decoration |
| Warm greys, never cold | The obsidian and the inks keep a **faint warm bias** — never cold blue-black |

---

## 1. Core principles (and the no-go list)

The values are ground-truth, and each maps to a hard rule. This is not decoration over an engineering tool; it is engineering values *expressed* as an interface.

- **Seek Truth Above Comfort → the UI never flatters.** Failure is rendered with the *same weight and prominence* as success — equal size, equal contrast, never buried, never softened, never green-washed. Degraded and failing state surfaces to the top of its bay. No vanity metrics, no decorative gauges, honest empty/error/loading states.
- **Create With Reverence → watchmaker craft.** 0.5px hairlines, tabular monospace figures that never jitter as they tick, pixel-honest alignment to the 8px field, considered density. Every component is a movement, not a widget.
- **Build to Endure → calm and un-trendy.** No gradient-of-the-month, no glassmorphism fashion, no motion that performs. A console that reads correct in five years. Clarity compounds.
- **Agent Life → the product feels awake.** Persistent state, running processes, a sense the system is alive even when unwatched. This is what `round = alive` and liveness-motion exist to express.

**We do:**
- One typeface family (IBM Plex), one structural ramp, one swappable signal.
- Hairlines (0.5px) and registration marks instead of boxes and heavy borders.
- Square structural bays; round only for living things.
- A measured field under everything — nothing floats in a void.
- Mono for every datum; Sans for every sentence.
- Honest density. A command bridge is information-rich, but never cramped and never noisy.
- Motion that demonstrates liveness, then gets out of the way.

**We never do (no-go):**
- ❌ **No pure black, no cold blue-black.** The ground is warm obsidian (`#0D0C0B`), never `#000`, never `#0A0E14`-style cyberpunk blue.
- ❌ **No glow, no neon, no bloom.** Liveness is a hairline ring or an opacity pulse, never a halo. (Crimson glow belongs to the marketing emblem, not the console.)
- ❌ **No second type family.** IBM Plex Sans + IBM Plex Mono only. No display serif in-product (the monument's Marcellus stays on the website).
- ❌ **No colour as the sole carrier of meaning.** Every state is legible by glyph + label + position with colour removed. Colourblind-safe and grayscale-safe by construction.
- ❌ **No rounding structural surfaces.** Panels, tables, bays, inputs are square. Round is reserved — it *means* alive.
- ❌ **No heavy borders or drop shadows as decoration.** Lines are 0.5px. Shadow exists only for the recessed-bay lip and for menus lifting off the field.
- ❌ **No chartjunk.** No 3D, no gradient fills in data, no gauge skeuomorphism, no sparkline-as-ornament. If a pixel isn't carrying data or structure, remove it.
- ❌ **No flooding the signal.** The accent appears on a *fraction* of the screen at any time. If two crimson things compete, one is wrong.
- ❌ **No marketing voice.** No hype, no exclamation, no emoji in UI. Labels are nouns and short verbs.

---

## 2. The structural signature (the identity)

This section is the brand. It does not change between platforms. If §9's colour is re-themed, §2 is what still says "Kamino."

### 2.1 Substrate — the measured field

Nothing sits in a void. The app ground is a warm obsidian carrying two baked layers:

```
--ground:        #0D0C0B;   /* app background — warm obsidian, never #000 */
--field-line:    rgba(236, 234, 230, 0.035);  /* minor grid */
--field-major:   rgba(236, 234, 230, 0.06);   /* major grid + registration ticks */
--field-minor-gap: 8px;     /* minor grid pitch = the base unit */
--field-major-gap: 64px;    /* major grid pitch; ticks/crosshairs land here */
--grain:         url(...);  /* fine neutral noise, ~3% opacity, multiply */
```

- A **graph-paper grid** at 8px minor / 64px major, both at very low alpha — present but never competing with text. At major intersections, a 4px **registration crosshair** (`+`). This is the CAD-viewport / drafting-table read.
- A **fine grain** over the whole ground (~3%, multiply) so the obsidian reads as *material*, not flat fill — the dark heir to the website's paper grain.
- An optional **deep-field vignette**: a barely-there radial darkening at the viewport edges (`rgba(0,0,0,0.18)` at the corners). The "sitting in the cockpit, looking out" depth. Use once, on the app shell, never per-panel.

The grid **must not** sit behind dense log/code text — those bays paint an opaque panel surface (§2.2) over it. The field shows through *gaps* between bays, in headers, and in empty states. The measured field is the table the instruments sit on, not a texture on the instruments.

### 2.2 Shape grammar — square is built, round is alive

The single most identifying rule, and it carries meaning, not style:

- **Structural / built → square (0 radius).** Panels, instrument bays, tables, code blocks, inputs, the field itself. These hold still. They are hairline rectangles, optionally recessed (below).
- **Living / active → fully round (`999px`).** Status dots, running indicators, agent nodes, action affordances (buttons/pills), avatars, the live heartbeat. Roundness *is the signal that something is alive or actionable.*

```
--r-built:  0px;     /* everything structural */
--r-alive:  999px;   /* everything live or actionable */
--r-inset:  2px;     /* the SINGLE exception: tiny machined easing on small inputs/chips-of-data. Use sparingly. */
```

**Instrument bays (the core surface).** A bay is a square panel set *into* the console:

```css
.bay {
  background: var(--panel);              /* #161513 — a touch above the ground */
  border: 0.5px solid var(--hairline);
  border-top-color: var(--hairline-lit); /* light catches the top lip */
  box-shadow:
    inset 0 1px 0 rgba(236,234,230,0.04),     /* top inner highlight */
    inset 0 -1px 0 rgba(0,0,0,0.5),           /* lower shadow lip — the "recessed" read */
    0 1px 0 rgba(236,234,230,0.02);           /* hairline catch below the bay */
  border-radius: var(--r-built);
}
```

This is "carved, not glowing" inverted onto dark: the bay is *cut into* the surface, lit by structure. No outer glow, ever.

**The signature detail: registration brackets.** Primary bays and focus targets wear **corner-brackets** — short L-marks at the four corners, not a full border — plus tick marks where a header rule meets the bay edge. 12px arms, drawn in `--hairline-strong`. This is the command-console / targeting-HUD mark, and it is the thing you would sketch to draw "Kamino console" from memory.

```
┌ ─        ─ ┐      ← brackets, not a closed box
   INSTRUMENT
└ ─        ─ ┘
```

**The occasional chamfer.** One restrained Imperial nod: a *single* clipped corner (top-right, 10px, 45°) is permitted on a bay's **identity header** — never on all four, never on data surfaces. It reads as a milled panel. Use it on the app shell header and primary section headers only.

### 2.3 Line & registration language

```
--hairline:        rgba(236, 234, 230, 0.10);   /* default dividers, bay edges */
--hairline-strong: rgba(236, 234, 230, 0.18);   /* emphasis, brackets, active edges */
--hairline-lit:    rgba(236, 234, 230, 0.22);   /* the lit top lip of a bay */
--tick:            rgba(236, 234, 230, 0.14);    /* registration ticks/crosshairs */
```

- Default rendered weight is **0.5px**. A 1px line is already loud; 2px is reserved for a single active/progress track.
- **Dividers come in two registers:** a plain hairline rule, and the **registration band** — the `Meander` descendant: a thin horizontal fret of evenly-spaced mono ticks (`│ ‧ ‧ ‧ │`), used to underline a bay header or separate major zones. It is the one ornament, and it is *measured*, not decorative.
- **Registration ticks** mark scale: ruled edges on timelines, axis ticks on metrics, and the crosshairs at the field's major grid. Ticks are how the console says "this is measured," which is how it says "ground-truth."

### 2.4 Proportion & edge ratios

Everything aligns to one base unit, so the whole system reflows on a handful of numbers.

```
--u: 8px;                         /* base unit; the minor grid pitch */
--gutter: 24px;   /* 3u — bay-to-bay gap */         --gutter-mobile: 16px;  /* 2u */
--bay-pad: 16px;  /* 2u — inner padding of a bay */ --bay-pad-lg: 24px;     /* 3u */
--rail: 56px;     /* 7u — left command rail width (collapsed 48px / 6u) */
--header: 48px;   /* 6u — app shell header height */
--shell-max: none; /* consoles run full-bleed; bays cap themselves, the shell does not */
```

- **Edge ratios are fixed by element role** (the "shape constants" that read as Kamino):
  - Corner bracket arm: **12px**. Chamfer clip: **10px**. Registration tick: **4px**. Live dot: **8px**. Hairline: **0.5px**.
  - Bay aspect: bays are free-height but their **header is always 6u (48px)** and their content insets by **2u** — so every bay shares the same edge rhythm regardless of size.
- **Density is honest, not cramped.** A command bridge is information-rich; the discipline is that density comes from *small consistent units and hairlines*, never from shrinking whitespace below 1u or stacking borders.
- **Spacing scale** (use these, do not freehand): `4 · 8 · 12 · 16 · 24 · 32 · 48 · 64 · 96`. All multiples of 4, mostly of 8.

---

## 3. Typography

### 3.1 Families

Two, both already in the Kamino stack. No third family, no display serif.

- **IBM Plex Sans** — all prose, labels, UI, headings, button text, descriptions.
- **IBM Plex Mono** — *everything that is data*: metrics, IDs, hashes, timestamps, log lines, code, file paths, durations, counts, table numerics, status codes, engine names in a pipeline.

The split is semantic and absolute: **if it's a measured value or a machine token, it's Mono; if it's a sentence a human wrote, it's Sans.** This division is itself an identity cue — you can tell a Kamino console by *what is set in mono*.

```
font-synthesis: none;
-webkit-font-smoothing: antialiased;
text-rendering: optimizeLegibility;
font-variant-numeric: tabular-nums;   /* global — figures never reflow as they tick */
```

### 3.2 Scale & treatment

Headings are calm and tight; the console earns hierarchy from *weight, mono/sans, and the field*, not from huge type. Consoles are not landing pages — the hero H1 is modest.

| Role | Family | Size | Weight | Tracking | Notes |
|---|---|---|---|---|---|
| Shell / page title | Sans | 20–24px | 500 | `-0.01em` | Modest. This is a tool, not a billboard |
| Section / bay header | Sans | 15–16px | 500 | `0` | Often paired with a count in mono |
| **Readout label** (kicker) | Mono | 11px | 500 | `0.14em` **UPPERCASE** | The command-console label. The one sanctioned all-caps, and *only* in mono — it's a machine label, not prose |
| Body / prose | Sans | 14px | 400 | `0` | Line-height 1.55 |
| Secondary / caption | Sans | 13px | 400 | `0` | `--text-mute` |
| Metric value (hero) | Mono | 28–40px | 500 | `-0.02em` | Tabular. Reels when it changes (§8) |
| Data / table / log | Mono | 12.5–13px | 400 | `0` | Line-height 1.5; tabular |
| Code | Mono | 13px | 400 | `0` | Line-height 1.6 |
| Micro (timestamps, IDs) | Mono | 11.5px | 400 | `0` | `--text-faint` |

**Rules that make it feel "Kamino console":**
- **All-caps lives in exactly one place: the mono readout label.** It is a machine-stamped tag (the descendant of the website's `chrome-label` tracked caps), never used for prose, headings, or buttons. Everywhere else is sentence case.
- **Weight, not size, does hierarchy.** 500 for anything emphatic; 400 for everything else. There is almost nothing in between and nothing heavier.
- **Tabular figures everywhere, no exceptions.** A metric that jitters its own width as it ticks fails the "watchmaker" bar.
- `text-wrap: pretty` on prose; `text-wrap: balance` on headings.

### 3.3 Which text gets which treatment

- **Headings / titles:** `--text` (warm off-white).
- **Readout labels (kickers):** `--text-mute` by default; `--signal` only when the label marks the single live/primary zone — sparingly.
- **Body / prose:** `--text-soft`.
- **Secondary / captions / units / timestamps:** `--text-mute`, then `--text-faint` for the most ambient.
- **Data values:** `--text` for the figure, `--text-mute` for its unit/suffix. State-coloured (§9.3) *only* when the value itself carries state.
- **Inline links:** `--text` with a 0.5px underline; hover → `--signal`. Never blue.

Rule of thumb: **off-white value, muted unit, signal only where something is alive.**

---

## 4. Layout & density

### 4.1 The shell

The canonical Hyperdrive shape is an **app shell**, not a scrolling page:

- A fixed **header** (6u) — Mark + product wordmark left, global state + account right, optional chamfer on the top-right corner.
- A fixed **left command rail** (7u, collapsible to 6u) — icon nav between the product's major zones (signal intake → build → ship → monitor). Active zone marked by a 2px signal tick on the rail edge + a round live dot, never a filled block.
- A **bay grid** filling the rest: instrument bays laid on the measured field, separated by 3u gutters.

The shell runs full-bleed; individual **bays cap their own content** (e.g. a reading column at ~76ch inside an otherwise wide bay). Never letterbox the whole console to a centred column — a command bridge uses its glass.

### 4.2 Bay grids

- **12-column fluid grid** on the field, 3u gutter. Bays span column ranges (`4/4/4`, `6/6`, `8/4`, `12`).
- Bays are the atomic unit. A bay has: a 6u header (readout label + optional count + optional actions), an optional registration-band underline, and a content well inset 2u.
- **Density tiers** by bay role: *monitor* bays (logs, tables, metrics) run dense; *narrative* bays (a run summary, a diff explanation) run roomy. Both use the same units — density is the count of rows, not the size of the gaps.

### 4.3 Breakpoints

| Width | What changes |
|---|---|
| ≤1280px | 12-col → 8-col; wide bays (`8/4`) stack |
| ≤1024px | Left rail collapses to icon-only (6u); 8-col → single column of stacked bays |
| ≤768px | Header actions move to an overflow; `--gutter` → 2u; bay padding → 1.5u; field grid hidden (grain only) on the smallest screens to protect legibility |

---

## 5. Components — data display (the heart)

This is where a console differs from a marketing page: the system is mostly *instruments*. All inherit §2's shape grammar and §3's mono/sans split.

### 5.1 Status pills & live indicators — `round = alive`

- **Live dot:** 8px round. Solid for steady; a 1.6s opacity **pulse** for active/streaming. The pulse is opacity only — *no glow*.
- **Status pill:** fully round, mono UPPERCASE-label inside, 11px. Carries a **glyph + label**, so it reads with colour removed: `● RUNNING`, `▣ QUEUED`, `▲ DEGRADED`, `■ FAILED`, `✓ PASSED`. Colour (§9.3) reinforces; glyph + label carry.
- **Honesty rule (Seek Truth):** a `FAILED`/`DEGRADED` pill is never smaller, dimmer, or lower than its `PASSED` sibling. Equal weight. Failing bays float their failure to the top.

### 5.2 Tables

- Hairline row rules (`--hairline`), no vertical rules, no zebra fills (zebra is chartjunk on a measured field). Square. Header row in mono readout-label style.
- Numerics mono, tabular, **right-aligned**; labels sans, left-aligned. Sort/active column marked by a tick in the header, not a fill.
- Row hover: `--panel-2` wash, no movement. Selected row: a 2px `--signal` edge tick on the left, not a flooded row.

### 5.3 Logs & streams

- Mono, 12.5px, line-height 1.5, on `--panel`. Monotone by default; **severity shown by a left gutter glyph + a 2px edge tick**, colour secondary (`WARN` amber tick, `ERROR` state-fail tick). Timestamps in `--text-faint`, the message in `--text-soft`.
- Streaming logs **autoscroll while pinned to bottom**; scrolling up detaches and shows a round "● live — jump to tail" affordance (round, because the stream is alive).
- This is liveness as evidence: the log *moving* is the proof the factory is running.

### 5.4 Code & diffs

- Square code bay, mono 13px / 1.6. Syntax colouring is **low-saturation and structural** (comments faint, keywords `--text`, strings a desaturated patina, never a rainbow). The diff register: added rows a 2px patina-green edge tick + faint green wash; removed rows a 2px state-fail edge tick + faint wash. Edge ticks, not full-bleed colour blocks.

### 5.5 Metric readouts

- Hero metric: mono 28–40px, tabular, `--text`; unit/suffix mono `--text-mute`; a mono readout-label above. Trend shown by a hairline sparkline (no fill, no gradient) + a `▲/▼` glyph, state-coloured only on the glyph.
- When a value changes live it **reels** (digit roll, ≤0.4s) — never a flash, never a glow.

### 5.6 The pipeline / engine DAG (Hyperdrive's signature instrument)

The closed loop — signal → build → ship → monitor, across the engines (Lupin · Trajan · Rommel · Heimdall) — rendered as a left-to-right **node graph**:

- **Nodes are round** (they're alive): each engine a round node, hairline-ringed, with a centred mono label. Active node: signal-ringed + pulsing live dot. Idle: `--text-faint` ring.
- **Edges are hairlines** with directional registration ticks showing flow; an in-flight unit of work is a small round **packet** travelling the edge (liveness-as-evidence, the one sanctioned travelling motion).
- The DAG sits on the bare measured field (no bay) so the grid reads as the factory floor the engines stand on.

### 5.7 Buttons & actions — round, the alive affordance

| Element | Style |
|---|---|
| Primary (`.action`) | Fully round, `--signal` fill, `--ground` text, mono-or-sans 13px/500, `8px 18px`. The *only* routinely-coloured surface — so there is rarely more than one per zone. Hover: brightness, no move, no glow |
| Secondary (`.action-ghost`) | Round, transparent, `--hairline-strong` ring, `--text`. Hover: ring → `--text` |
| Quiet / tertiary (`.action-text`) | Inline, `--text`, 6px gap to a `→`. Hover → `--signal` |
| Destructive | Round, `--state-fail` ring + text (never a flooded red fill — destructive is *marked*, then confirmed) |
| Disabled / pending | Ghost ring at `--text-faint`, hatched fill for "coming soon / inert" (the website's `btn-disabled` descendant) |

Transitions: opacity / background / border over `0.15s ease`. Buttons never move, scale, or cast shadows.

### 5.8 Inputs

- Square (`--r-built`, or `--r-inset` 2px for the smallest), `--panel` fill, hairline ring; focus ring → `--hairline-strong` plus a 2px `--signal` edge tick on the active side. Mono for value entry that is data (paths, queries, IDs); sans for prose entry.

### 5.9 Awaiting / empty / loading states — the mark holds the frame

Directly carried from the website's `EmblemImage.vue`: any bay awaiting data shows the **Kamino emblem, slow-breathing** (opacity/scale pulse, ~3s), centred on `--panel`, with a one-line mono readout label ("awaiting telemetry", "no runs yet"). On **error** the emblem stops breathing and holds steady (reads "stopped," not "loading") — never a broken-glyph or a bare spinner. Restrained breathe only; no crimson halo in-product (that halo is a marketing flourish; the console stays glow-free).

---

## 6. Motion

Motion is **quiet and meaningful**: it exists to prove liveness or to confirm an action, never to perform. "Gravity, not hum."

- **Liveness (the signature):** the live-dot pulse (1.6s opacity), streaming-log autoscroll, the DAG packet travelling an edge, the metric reel. These are *demonstrations the system is awake* — small, self-contained, ambient. Everything else is still.
- **Entrances:** bays fade-up 8px over `0.4s` on `cubic-bezier(0.2, 0.8, 0.2, 1)`. Stagger grid children by ~40ms. Above-the-fold shell loads with the same curve.
- **UI feedback:** hovers/focus `0.15s ease`; menus fade + 4px slide `0.18s`.
- **No glow, no bloom, no bounce, no parallax, no scale-on-hover for data.** The image-zoom and parallax of a marketing page are explicitly out.
- **Easing vocabulary:** `cubic-bezier(0.2, 0.8, 0.2, 1)` (entrances), plain `ease` `0.15s` (UI), `linear` (live tickers, log scroll, packet travel).
- **Reduced motion is mandatory and non-negotiable.** Under `prefers-reduced-motion: reduce`, all pulses/reels/packets freeze to a steady end-state; liveness degrades to a static "● live" dot. Any new motion must register itself in the reduced-motion block. (This mirrors the website's global neutralization.)

---

## 7. Icons

- **Custom thin-line SVGs**, drawn inline, one drawing language. No icon-font, no library, no filled/duotone/multicolour sets, no emoji.
- `viewBox="0 0 24 24"`, `fill="none"`, `stroke-width: 1.25` (1.5 for ≤16px on dark), `stroke-linecap`/`linejoin="round"`.
- **Colour:** `--text` stroke on panels; `--text-mute` when inactive; `--signal` *only* for the rare brand/live glyph. Icons are line, not fill — the system's hairline language at glyph scale.
- Engine/zone icons in the rail share the stroke weight of the data hairlines, so the rail reads as part of the same instrument.

---

## 8. The Mark & brand presence

- The **Kamino emblem** (the existing lantern/key mark; `brand/emblem-white.png` on dark) appears in: the shell header lockup, the awaiting/empty states (§5.9), and the about/version surface. Wordmark beside it in Sans 15px/500, `-0.01em`.
- The Mark is the *constant* across re-themed platforms — when `--signal` changes colour, the Mark and §2's structure are what still say Kamino.
- **Brand presence is structural, not colour-driven.** On a platform with a different signal colour, the console is still unmistakably Kamino via the measured field, the bays, the brackets, and the mono/sans split. That is the entire point of §0.

---

## 9. Colour (themeable — the only re-skin layer)

Colour is demoted on purpose. The structural ramp is constant; exactly one token re-themes per platform; functional state colours are independent of brand so they never shift when a platform re-skins.

### 9.1 Structural ramp — constant across all platforms

```
--ground:    #0D0C0B;   /* app field — warm obsidian */
--panel:     #161513;   /* instrument bay surface */
--panel-2:   #1C1A18;   /* nested / hovered surface */
--text:      #ECEAE6;   /* primary — warm off-white (echoes the marble) */
--text-soft: #B7B3AC;   /* prose / body */
--text-mute: #807C74;   /* secondary, units, labels — warm grey, never cold */
--text-faint:#5A574F;   /* timestamps, ambient, the lightest */
```

The greys are **warm** (a hint of stone/clay), the same DNA as the website's warm ink ramp. Never substitute cold greys (`#888`, `#9aa`). This warmth is what keeps the command bridge from reading as cold cyberpunk.

### 9.2 Signal — exactly one, swappable, seldom

```
--signal:        #C95A5A;   /* Kamino default: dark-tuned crimson. PER-PLATFORM SWAPPABLE. */
--signal-strong: #D98A8A;   /* hover / emphasis */
```

- **One** accent token for the whole product. To re-skin a platform, change this one value — *nothing else moves*.
- **Used seldom.** It appears only on: the single primary action per zone, the live/active edge tick, the active rail marker, and the one live readout label that matters. If two signal elements compete for attention, one is miscoloured. The accent is a *fraction* of the screen at any moment.
- **No glow.** Signal is a fill or a 2px tick, never a halo.

### 9.3 State — functional, independent of brand

State colours are **constant across platforms** (they do not follow `--signal`), so a re-skin never makes "failed" ambiguous. Each is paired with a glyph + label so it survives grayscale.

```
--state-ok:   #5E8C73;   /* passed / healthy — patina green (ties to website --patina) */
--state-run:  #6F93A8;   /* running / in-progress — cool steel (the only cool tone, earned: "in motion") */
--state-warn: #C8923E;   /* warning / degraded — amber */
--state-fail: #C9514B;   /* failed / error — a red distinct from the brand signal */
```

- **Crimson (`--signal`) is brand; `--state-fail` red is status.** They are deliberately different reds so "this is Kamino" and "this failed" never collapse into the same mark — and so a platform that re-themes its signal to, say, blue still shows failures in the same red.
- State colour is always *secondary* to the glyph + label + position. Remove all four state hues and the console is still fully legible. That is the test (§0).
- On the rare light surface (a printed report, a PDF export): same tokens, inverted ramp; hairlines become ink-on-light at `0.10`–`0.18`. The structure is ground-agnostic by design.

---

## 10. Portability checklist (re-skinning for a new platform)

When standing up the next Kamino product on this system:

1. **Change `--signal`** to the platform's primary. That is the *only* colour you are permitted to change.
2. **Do not touch §2** (substrate, shape grammar, line language, proportion) — that is the shared identity.
3. **Keep the state tokens (§9.3)** as-is. State is universal.
4. **Set in mono what is data, in sans what is prose** (§3.1). No exceptions.
5. **Run the grayscale test** (§0). Desaturate. If it stopped looking like Kamino, you changed something in §2 that you shouldn't have.
6. **Register every animation in the reduced-motion block** (§6).
7. **Honesty audit** (§1): can the UI show its own failure as loudly as its success? If not, fix it before shipping.

> The promise of this system: a developer or an agent can drop this file into a new repo, swap one colour token, and produce a product that is unmistakably Kamino, cutting-edge, and command-centre — without ever having seen the others.
