# Frontend — Kamino Console Design-Language Conversion

> Convert the **entire** OpenTheory frontend from its current light "marble" posture into the
> **Kamino Console** design language (`docs/design_blueprint.md`): a warm-obsidian command bridge
> — recessed instrument bays, registration-bracket precision, IBM Plex Mono readouts / Plex Sans
> prose, square-means-built / round-means-alive, hairlines instead of boxes, lit by structure not
> glow, themed by a single seldom-used signal colour.

## Goal

Make OpenTheory's UI **unmistakably Kamino** while changing **no backend, schema, API contract, or
data flow**. This is a presentation-layer release only: every TanStack Query call, every mutation,
every route, and every read schema stays exactly as-is. What changes is the substrate (tokens,
fonts, the measured field), the structure (a full app shell + left command rail), and the visual
grammar of every component.

The single acceptance bar is the blueprint's own §0 **grayscale test**: desaturate the finished UI
and it must still read as Kamino — because the identity lives in *form* (substrate, proportion,
shape grammar, line language, type), not colour.

## Why this is a large change, not a re-theme

The current frontend is the blueprint's deliberate opposite — the *monument* posture, not the
*engine room*:

| Today (monument) | Target (engine room, per blueprint) |
|---|---|
| Light paper `#f7f3ea`, warm ink `#121417` | Warm obsidian ground `#0D0C0B`, off-white `#ECEAE6` |
| Teal `signal` `#1f7a6d`, `ember` `#c44e2d` | Crimson `--signal` `#C95A5A` (seldom) + independent state tokens |
| Inter (sans) + Menlo (mono) | IBM Plex Sans + IBM Plex Mono |
| Rounded cards (`rounded-lg`/`rounded-md`), soft drop shadows (`shadow-panel`) | Square recessed **bays** with registration brackets; hairlines, no decorative shadow |
| Centered `max-w-7xl` column, header only | Full-bleed app shell: 6u header + 7u left command rail + bay grid on a measured field |
| `bg-white/70` translucent panels floating on paper | Opaque `--panel` bays cut into the field; the field shows through gutters |

So two current choices directly collide with hard **no-go** rules and are resolved explicitly below
(see *Decisions*): the light default ground (§0/§9) and the `lucide-react` icon library (§7).

## Decisions (locked before planning)

1. **Shell architecture → full app shell + left command rail (§4.1).** The most on-spec structure.
   The rail is adapted to OpenTheory's real zones (it is *not* Hyperdrive's signal→build→ship→
   monitor): **Projects** (index), **Workspace** (contextual, active inside a project), **Funding /
   Budget** (contextual inside a project), with a hatched, inert **Agents** zone using the blueprint's
   "coming soon" treatment (§5.7) — honest about what does not exist yet (`0.7.0`).
2. **Icons → keep `lucide-react`, restyled to the line language.** Per explicit direction, the §7
   "no icon library" no-go is **deferred**. Icons are constrained globally to the drawing language:
   `currentColor` stroke, `stroke-width ≈ 1.25` (1.5 at ≤16px), no fills, mono-tone — `--text` /
   `--text-mute` by role, `--signal` only for the rare brand/live glyph. A future slice may swap to
   custom in-repo SVGs; the plan isolates icons behind one wrapper so that swap is cheap.
3. **Stay on Tailwind v3.4** (no v4 migration — out of scope). Tokens are delivered as CSS variables
   referenced by the Tailwind theme.
4. **Tokens stored as raw RGB channel triplets**, wired into Tailwind as
   `rgb(var(--token) / <alpha-value>)`, so the existing `/opacity` utilities (`text-text/70`,
   `bg-signal/10`) keep working. **Non-negotiable Phase 1 rule** — see §"Token delivery".
5. **No dark/light toggle.** The console is dark, full stop (§0/§9). The blueprint's inverted "light
   surface" ramp (§9.3, for a printed report/PDF) is **out of scope** — OpenTheory has no print/export.
6. **Versioning / cadence.** Frontend-only, independent of the `0.7.0` agent work; it can ship in
   parallel. Delivered as **six small, individually deployable phases** (`D1`–`D6`), mirroring how
   `0.4.1`–`0.4.5` and `0.6.1`–`0.6.4` were sliced. Assign a version at merge time (suggested: a
   dedicated `0.8.0`, or fold under the next UI release — the user's call). Update
   `docs/changelog.md` per phase, in the established style.

## Out of scope (explicitly)

- Any backend / schema / migration / API change. Zero.
- New product features, routes, or data. (The non-functional header "search" placeholder stays inert
  — restyled, not wired.)
- The **pipeline / engine DAG** instrument (§5.6). It is Hyperdrive-specific (named engines Lupin·
  Trajan·Rommel·Heimdall); OpenTheory has no engine pipeline. The research-checkpoint DAG is a
  *future* analog, noted in *Deferred instruments*, not built here.
- Custom in-repo SVG icon set (Decision 2).
- Light/print theme (Decision 5).
- Metric **reels** (digit-roll on live change, §5.5/§8) are **optional** in D6 — values here change on
  refetch, not via a live stream, so a reel is low-value; listed as a stretch item.

---

## Global conventions (apply in every phase)

These are the cross-cutting rules every converted component must obey. They are the operational form
of the blueprint and the thing to check in review.

### Shape grammar — square is built, round is alive (§2.2)

- **Square (`rounded-none`, `--r-built`):** every bay, panel, table, code/log surface, **input,
  select, textarea**, the count tiles, the field. These "hold still."
- **Round (`rounded-full`, `--r-alive`):** status dots, live indicators, **all buttons/actions**,
  pills, avatars, the rail's active live-dot. Round *means* alive or actionable.
- `--r-inset` (2px) is the single sanctioned exception — tiny machined easing on the smallest chips
  of data; use sparingly.
- **Audit:** today buttons and panels are both `rounded-md`. After conversion, a square button or a
  round bay is a bug.

### Mono vs Sans — the semantic split (§3.1), as it maps to OpenTheory data

Absolute rule: **a measured value or machine token is Mono; a sentence a human wrote is Sans.**

- **Mono (IBM Plex Mono):** all counts (threads/claims/evidence/checkpoints/validations/branches),
  the `%` confidence, money amounts + currency, dates/timestamps, IDs and short hashes
  (`target_id.slice(0,8)`, `forked_from_checkpoint_id`), enum/status tokens rendered as **readout
  labels** (project/thread/claim/branch/funding status, `claim.kind`, `thread.stage`, validation
  outcomes, ref `role`, `contribution_kind`, funding `source`/`kind`).
- **Sans (IBM Plex Sans):** all titles, `project.question`, `description`, `thread.title`/`question`,
  `claim.statement`, `checkpoint.summary`/`notes`, `evidence.title`, validation `notes`, every UI
  label/button/heading/body string.

### Readout label (§3.2) — the one sanctioned all-caps

The repeated `text-[11px] font-semibold uppercase tracking-[0.1em]` labels already in the code
(`Threads`, `Claims & Evidence`, `Budget`, `Funded`, `History`, …) become the **readout label**:
**Mono**, 11px, weight 500, `tracking-[0.14em]`, UPPERCASE, `--text-mute` (or `--signal` only for the
single live/primary zone). All-caps lives **only** here — never on prose, headings, or buttons.

### Line language (§2.3) — hairlines, not boxes; shadow only for the recess

- Default border weight is **0.5px** in `--hairline`; `--hairline-strong` for emphasis/brackets/
  active edges. Drop every `shadow-panel`/`shadow-sm`; the only shadow is the bay's inner recess lip
  and a menu lifting off the field.
- Replace heavy/colored full borders with **edge ticks** (a 2px `--signal` or `--state-*` bar on one
  side) and **registration brackets** (corner L-marks). Selected/active = edge tick, never a flooded
  fill.

### Honesty (§1, the "Seek Truth" rule)

Failure renders at the **same weight, size, and contrast** as success — never smaller, dimmer, or
green-washed. A `failed`/`contradicts`/`dead_end`/degraded state floats to the **top** of its bay.
State is carried by **glyph + label + position**, with colour only reinforcing — so it survives the
grayscale test. (OpenTheory's `contradictions` summary and `failed`/`contradicts` validation outcomes
are the live test cases.)

### Motion & reduced-motion (§6)

Motion only ever means *something changed* or *something is alive*. No glow/bloom/bounce/parallax/
scale-on-hover for data. Every animation added in any phase must register a freeze in the
`prefers-reduced-motion: reduce` block in `globals.css` (D6 audits this, but each phase adds its own).

---

## Token delivery (the Phase-1 contract every later phase depends on)

`globals.css` `:root` holds the tokens as **space-separated RGB channels** (so Tailwind opacity
modifiers survive — Decision 4). Hairline/field overlays, which are inherently alpha, are kept as
ready-made `rgba()` for use in component CSS and arbitrary values.

```css
:root {
  color-scheme: dark;

  /* Structural ramp — channels, for rgb(var(--x) / <alpha>) */
  --ground:    13 12 11;       /* #0D0C0B warm obsidian */
  --panel:     22 21 19;       /* #161513 bay surface */
  --panel-2:   28 26 24;       /* #1C1A18 nested/hover */
  --text:      236 234 230;    /* #ECEAE6 */
  --text-soft: 183 179 172;    /* #B7B3AC prose */
  --text-mute: 128 124 116;    /* #807C74 units/labels */
  --text-faint:90 87 79;       /* #5A574F ambient */

  /* Signal — the ONE swappable accent (channels) */
  --signal:        201 90 90;  /* #C95A5A */
  --signal-strong: 217 138 138;/* #D98A8A */

  /* State — constant across platforms, independent of signal (channels) */
  --state-ok:   94 140 115;    /* #5E8C73 patina green */
  --state-run:  111 147 168;   /* #6F93A8 cool steel */
  --state-warn: 200 146 62;    /* #C8923E amber */
  --state-fail: 201 81 75;     /* #C9514B — a red distinct from --signal */

  /* Line/field overlays — alpha-native, used in CSS not Tailwind color utils */
  --hairline:        rgba(236,234,230,0.10);
  --hairline-strong: rgba(236,234,230,0.18);
  --hairline-lit:    rgba(236,234,230,0.22);
  --tick:            rgba(236,234,230,0.14);
  --field-line:      rgba(236,234,230,0.035);
  --field-major:     rgba(236,234,230,0.06);

  /* Proportion */
  --u: 8px;  --gutter: 24px; --gutter-mobile: 16px;
  --bay-pad: 16px; --bay-pad-lg: 24px;
  --rail: 56px; --rail-collapsed: 48px; --header: 48px;
  --field-minor: 8px; --field-major-gap: 64px;

  /* Radius */
  --r-built: 0px; --r-alive: 999px; --r-inset: 2px;
}
```

`tailwind.config.ts` maps each ramp/state token through the channel pattern:

```ts
const ch = (v: string) => `rgb(var(${v}) / <alpha-value>)`;
colors: {
  ground: ch("--ground"), panel: ch("--panel"), "panel-2": ch("--panel-2"),
  text: ch("--text"), "text-soft": ch("--text-soft"),
  "text-mute": ch("--text-mute"), "text-faint": ch("--text-faint"),
  signal: ch("--signal"), "signal-strong": ch("--signal-strong"),
  "state-ok": ch("--state-ok"), "state-run": ch("--state-run"),
  "state-warn": ch("--state-warn"), "state-fail": ch("--state-fail"),
},
borderRadius: { built: "var(--r-built)", alive: "var(--r-alive)", inset: "var(--r-inset)" },
fontFamily: { sans: ["var(--font-plex-sans)", ...], mono: ["var(--font-plex-mono)", ...] },
```

This is the mechanism that lets later phases do near-mechanical token swaps
(`text-ink/70` → `text-text/70`, `bg-signal/10` → `bg-signal/10` but now crimson, `text-ember` →
`text-state-fail`) without rewiring opacity.

### Old → new token map (the find/replace key for D3–D5)

| Old (current) | New (Kamino) | Notes |
|---|---|---|
| `bg-paper`, `bg-white/70`, `bg-white/60` | `bg-ground` / `bg-panel` / `bg-panel-2` | white-on-paper → bay surfaces |
| `text-ink`, `text-ink/70`, `text-ink/55` | `text-text`, `text-text-soft`, `text-text-mute` | by role, not by opacity guesswork |
| `text-ink/45` | `text-text-faint` | ambient |
| `border-line` | `border-[var(--hairline)]` or the `.bay`/bracket primitive | hairline, 0.5px |
| `signal` (teal `#1f7a6d`) | `signal` (crimson `#C95A5A`) | now *seldom* — audit overuse |
| `ember` (`#c44e2d`) | `state-fail` | error/failure status (not brand) |
| success/passed greens implied by `signal` | `state-ok` | passed/healthy patina green |
| running/in-progress | `state-run` | the one earned cool tone |
| warn/degraded | `state-warn` | amber |
| `shadow-panel`, `shadow-sm` | *(removed)* | recess lip only, via `.bay` |
| `rounded-lg`, `rounded-md` on structure | `rounded-none` (built) | square |
| `rounded-md` on buttons | `rounded-full` (alive) | round |
| Inter / Menlo | `font-sans` (Plex Sans) / `font-mono` (Plex Mono) | per the mono/sans split |

> **Signal-overuse audit (do this during D3–D5):** today teal `signal` is sprinkled on *every* panel
> label, icon, and accent. Crimson is "seldom" — a fraction of the screen. Most of those become
> `--text-mute` (labels) or a `--state-*` token; `--signal` survives only on the single primary action
> per zone, the active rail/line marker, the one live readout label, and active edge ticks. If two
> crimson things compete in a view, one is wrong.

---

## Component primitives (built in D1, consumed by D2–D5)

A small set of reusable primitives so the grammar is defined once. Proposed home:
`src/components/console/`. Each is thin (Tailwind + the tokens above); the point is one source of
truth for the shape grammar.

- **`Bay`** (`bay.tsx`) — the core square recessed surface (§2.2). Props: `as`, `bracketed?`
  (renders the 4 corner registration brackets), `chamfer?` (single 10px top-right clip, headers
  only), `density?: "monitor" | "narrative"`, `className`. Encapsulates the recess box-shadow
  (`inset` top highlight + lower shadow lip), `0.5px` hairline border, lit top edge, `--r-built`.
- **`BayHeader`** — fixed 6u header row: a `ReadoutLabel`, optional mono count, optional actions
  slot, optional registration-band underline.
- **`ReadoutLabel`** (`readout-label.tsx`) — mono 11px / 500 / `0.14em` / uppercase; `tone`:
  `mute | signal`.
- **`RegistrationBrackets`** — the signature 12px corner L-marks in `--hairline-strong` (absolute,
  `pointer-events-none`).
- **`RegistrationBand`** — the `│ ‧ ‧ ‧ │` measured tick-fret divider (the lone ornament, §2.3).
- **`StatusPill`** (`status-pill.tsx`) — fully round, mono UPPERCASE 11px, **glyph + label**, state
  token. The honest status atom (§5.1). Consumes a shared `STATE_META` map.
- **`LiveDot`** — 8px round; `pulse?` (1.6s opacity pulse, no glow; freezes under reduced-motion).
- **`Action`** / **`ActionGhost`** / **`ActionText`** (`action.tsx`) — the three button registers
  (§5.7), all round: primary `--signal` fill / ghost hairline-strong ring / inline text→`→`.
  `Destructive` = `--state-fail` ring + text, never a flooded fill. `disabled`/`pending` =
  hatched inert fill.
- **`Field`** (`field.tsx`, or pure CSS on the shell) — the measured-field background: 8px/64px
  graph-paper grid + 4px registration crosshairs + ~3% grain + optional edge vignette (§2.1).
- **`Input` / `Select` / `Textarea`** wrappers — square, `--panel` fill, hairline ring, focus →
  `--hairline-strong` + 2px `--signal` edge tick (§5.8); mono for data entry (paths/queries/amounts),
  sans for prose.
- **`Icon`** (`icon.tsx`) — the lucide wrapper enforcing `strokeWidth`, size, and `currentColor`
  monotone (Decision 2), so every icon obeys the line language and a future SVG swap is one file.
- **`AwaitingState`** (`awaiting-state.tsx`) — the §5.9 empty/loading/error state: the brand mark
  slow-breathing (loading) / steady (error), centered on `--panel`, with a one-line mono readout
  label. Replaces the three `panel-state.tsx` helpers.

> **Brand-mark dependency (flag early).** §5.9/§8 want the Kamino emblem (`brand/emblem-white.png`)
> for awaiting states and the shell lockup. OpenTheory currently uses a `FlaskConical` lucide glyph as
> its mark. **Action item for D1:** obtain the emblem asset, or agree an interim mark (e.g. a custom
> thin-line lantern/key SVG, or keep `FlaskConical` restyled). The `AwaitingState`/shell lockup are
> built against whatever mark we settle on; isolate it in one `BrandMark` component.

---

## Phase D1 — Design foundation: tokens, fonts, field, primitives

**Objective.** Stand up the entire substrate and the primitive library so every later phase is a
re-skin against a ready token layer — not ad-hoc styling. Nothing user-facing is "finished," but the
app remains runnable and the new system is verifiable in isolation.

**Files.**
- `frontend/src/app/globals.css` — replace wholesale: `color-scheme: dark`; the `:root` token block
  above; warm-obsidian `body` ground; the baked **measured field** (graph-paper grid via layered
  `background-image` linear-gradients at `--field-minor`/`--field-major-gap` + crosshairs), the
  grain, optional vignette; global `font-variant-numeric: tabular-nums`, `font-synthesis: none`,
  `-webkit-font-smoothing: antialiased`, `text-rendering: optimizeLegibility`; `text-wrap` defaults;
  link styling (underline → hover `--signal`, never blue); and the empty `@media (prefers-reduced-motion: reduce)`
  block that later phases extend.
- `frontend/tailwind.config.ts` — replace `theme.extend` per *Token delivery*: colors via the channel
  pattern, radii (`built`/`alive`/`inset`), `fontFamily` → Plex vars, the spacing scale
  (`4·8·12·16·24·32·48·64·96`), remove `boxShadow.panel`, remove old `ink/paper/line/ember`.
- `frontend/src/app/layout.tsx` — load **IBM Plex Sans** + **IBM Plex Mono** via `next/font/google`
  with CSS variables (`--font-plex-sans`, `--font-plex-mono`); apply both variable classes on `<html>`;
  set `lang`; keep the provider tree untouched.
- `frontend/src/components/console/*` — build the primitives listed above.
- `frontend/src/components/console/brand-mark.tsx` — the single mark component (per the asset decision).
- **(verification aid)** `frontend/src/app/_styleguide/page.tsx` — an internal, unlinked page rendering
  every primitive in every state (bays, brackets, all `StatusPill` states, buttons, inputs, live dot,
  awaiting/loading/error, readout labels, the field). Used to eyeball the system and to run the
  grayscale test cheaply. (Prefixed/again unlinked so it ships harmlessly, or gated behind
  `NEXT_PUBLIC_AUTH_DEV`; remove before final merge if undesired.)

**Tasks.**
1. Swap fonts (`next/font`), confirm Plex loads (no FOUT, `font-synthesis: none`).
2. Land the token block + Tailwind wiring; verify a probe element resolves `bg-panel`, `text-text/70`,
   `border-[var(--hairline)]`, `rounded-built`, `rounded-alive` correctly (the opacity-modifier check).
3. Build the measured field on the body; confirm it shows through and never sits *behind* dense text
   (bays paint opaque `--panel`).
4. Implement each primitive; cover every state in the styleguide page.
5. Settle the brand mark (asset or interim) behind `BrandMark`.

**Definition of Done.** `npm run typecheck`/`lint`/`build` pass. The styleguide page renders the full
primitive set on the warm-obsidian field; desaturating it (browser devtools "grayscale" filter) still
reads as a measured instrument console (no state relies on hue alone). Reduced-motion freezes the live
dot to steady. The rest of the app still loads (it will look transitional until D2–D5).

---

## Phase D2 — The app shell: header + left command rail + bay grid

**Objective.** Replace the centered, header-only layout with the full-bleed **app shell** (§4.1) —
the structural signature. After this phase the chrome is Kamino even though inner content is mid-
conversion.

**Files.**
- `frontend/src/components/shell/app-shell.tsx` **(new)** — the shell: fixed 6u **header** (left:
  `BrandMark` + "OpenTheory" wordmark Sans 15/500 `-0.01em`, optional 10px top-right chamfer; center:
  the inert restyled search field, square, hairline; right: global state slot + account), fixed 7u
  **left rail** (collapsible to 6u), and a `<main>` bay-grid region on the field with 3u gutters,
  full-bleed (no `max-w` letterbox).
- `frontend/src/components/shell/command-rail.tsx` **(new)** — icon nav for the adapted zones
  (Decision 1): **Projects**, **Workspace** (contextual/disabled off-project), **Funding**
  (contextual), and a **hatched, inert Agents** entry (the §5.7 "coming soon" treatment). Active zone:
  a 2px `--signal` edge tick on the rail edge + a round `LiveDot` — never a filled block. Icons via
  the `Icon` wrapper, sharing the data-hairline stroke weight.
- `frontend/src/components/shell/site-header.tsx` — **retire/replace**: its contents move into
  `app-shell.tsx`'s header; keep or delete the file (prefer delete, update imports).
- `frontend/src/app/page.tsx` and `frontend/src/app/projects/[projectId]/page.tsx` — render children
  inside `<AppShell>` instead of `<SiteHeader/> + <section max-w-7xl>`. Remove the centered column;
  the workspace goes full-bleed onto the field.
- `frontend/src/components/shell/auth-menu.tsx` & `dev-actor-switcher.tsx` — re-skin into the header's
  right slot: account button → ghost/round; dropdowns → square `--panel` menus lifting off the field
  with the §6 menu motion (fade + 4px slide, reduced-motion safe); the `ShieldCheck` internal badge →
  `Icon` + `--signal`; "Sign in" → primary `Action`. Keep all auth logic (`useAuth`,
  `useActingIdentity`) byte-for-byte.

**Tasks.**
1. Build `AppShell` + `CommandRail`; wire active-zone detection off the route (`usePathname`).
2. Move header content over; apply the single chamfer to the shell header only.
3. Convert both page shells; delete the `max-w-7xl` centering and `SiteHeader` usage.
4. Re-skin auth menu + dev switcher in-place (logic untouched).
5. Implement the §4.3 breakpoints for the shell: ≤1024 rail collapses to icons; ≤768 header actions
   → overflow, field grid hidden (grain only) on the smallest screens.

**Definition of Done.** Both routes render inside the obsidian shell with a working left rail and the
field showing through gutters. Sign-in/out, the account dropdown, and the dev-actor switcher all
function unchanged. Rail collapses correctly at breakpoints. Typecheck/lint/build pass.

---

## Phase D3 — Project index surface

**Objective.** Convert the landing/index (`/`) — hero, the three feature tiles, and the project grid —
into the bay/bracket grammar with the mono/sans split and honest states.

**Files.**
- `frontend/src/app/page.tsx` — the hero becomes a modest console title (Sans 20–24/500, **not** a
  4xl/5xl billboard — §3.2 "consoles are not landing pages"); the "Research Ledger" kicker → mono
  `ReadoutLabel`; the three `metrics` tiles → a small `Bay` row of metric readouts (mono value, mono
  readout label); the "Fund project" button → primary `Action` (round). Drop `shadow-panel`.
- `frontend/src/components/projects/project-list.tsx` — its three inline loading/error/empty blocks →
  `AwaitingState` (mark holds the frame). Grid of cards stays a responsive bay grid.
- `frontend/src/components/projects/project-card.tsx` — `<article>` → a **bracketed `Bay`**: status →
  a round `StatusPill` (mono, glyph+label); title Sans; `question`/`description` Sans `--text-soft`;
  the open affordance → round ghost icon `Action`; the Threads/Validation/Funding footer → mono
  readout labels with `Icon`s; replace `rounded-lg border bg-white/75 shadow-sm`.

**Tasks.** Token find/replace per the map; restructure card into `Bay`+`RegistrationBrackets`;
convert all three panel states to `AwaitingState`; verify the project `status` enum renders as a
`StatusPill` whose meaning survives grayscale.

**Definition of Done.** `/` renders as console bays on the field; empty/loading/error states use the
breathing-mark treatment; no `shadow-*`/`rounded-lg` on structure; status legible desaturated.
Typecheck/lint/build pass; visual check against the styleguide.

---

## Phase D4 — Workspace frame: project header, budget, line/branch bar

**Objective.** Convert the workspace orchestrator chrome and the two cross-cutting bars that sit above
the three instrument columns.

**Files.**
- `frontend/src/components/workspace/project-workspace.tsx` — the project **header** → a `Bay` with a
  single chamfer + brackets: `status` → `ReadoutLabel`/`StatusPill`; title Sans; `question`/
  `description` Sans; the 6-up `COUNT_LABELS` `dl` → **metric readouts** (§5.5: mono tabular value,
  mono readout label, in square mini-tiles), with the loading shimmer restyled to the token ramp; the
  **contradictions** block → the honesty surface (§1): `state-fail`/`state-warn` glyph + label,
  floated to the top of the header, **equal weight** to the counts, never softened. The two top-level
  loading/error returns → `AwaitingState`. The "Projects" back link → `ActionText` with a `←`.
- `frontend/src/components/workspace/funding-panel.tsx` — **the money/metric showcase**: wrap in a
  `Bay`; `Budget` header → mono `ReadoutLabel`; the Funded/Available/Spent `dl` → three metric
  readouts (mono tabular amounts — currency suffix `--text-mute`; `Spent` stays explicitly `0` with
  its existing tooltip); `STATUS_CLASS` map → `state-*` tokens behind `StatusPill`
  (`settled`→ok, `pending`→mute/run, `failed`→fail, `refunded`→faint); funding history → a mono data
  list (amounts mono/tabular, source/kind mono readout tokens, actor display-name Sans, dates mono
  `--text-faint`); the native top-up form → console `Input`/`Select` + a round primary `Action`; the
  role-separation note stays (Sans `--text-mute`). Keep all funding logic/roles intact.
- `frontend/src/components/workspace/branch-bar.tsx` — wrap in a `Bay`; the `Line` label → mono
  readout; `Main line` + each branch → round selectable pills (active = `--signal` edge tick / fill,
  not a flooded block); `BRANCH_STATUS_META` → `state-*` `StatusPill`s (`open`→run/ok, `dead_end`→
  fail with the existing strike-through preserved as an honest "recorded, not deleted" mark, `closed`/
  `merged`→mute); Fork/Close → round `ActionGhost`/`Destructive`; the `CloseBranchForm` (currently
  `border-ember`, `bg-ember` submit) → `state-fail` **ring + text**, never a flooded red fill (§5.7
  destructive rule); fork/close `Input`/`Select` → console inputs.

**Tasks.** Convert header → metric-readout grid; make contradictions honest + top-floated; rebuild
funding as the metric/data showcase with state-token pills; rebuild the branch bar's pills + the
destructive close form.

**Definition of Done.** Project header, budget, and line bar read as instruments; failure/contested/
dead-end states render at equal weight and survive grayscale; destructive actions are *marked* (ring),
not flooded; all funding/branch logic and role-gating unchanged. Typecheck/lint/build pass.

---

## Phase D5 — The three instrument bays + validation controls + shared states

**Objective.** Convert the dense heart (§5.1/5.2/5.3) — threads, claims+evidence, the checkpoint
timeline — plus the shared validation vocabulary and the shared panel-state helpers.

**Files.**
- `frontend/src/components/workspace/panel-state.tsx` — replace the three helpers
  (`PanelLoading`/`PanelError`/`PanelEmpty`) with thin wrappers over `AwaitingState` (mark holds the
  frame, §5.9), preserving their call signatures so the panels need no logic change. Error stops the
  breathe and holds steady (reads "stopped," not "loading").
- `frontend/src/components/workspace/validation-controls.tsx` — `OUTCOME_META` recolored to **state
  tokens** behind `StatusPill` (`passed`→`state-ok ✓`, `failed`→`state-fail ■`, `contradicts`→
  `state-fail ▲`, `inconclusive`/`needs_reproduction`→`text-mute`/`state-warn`, `retract`→faint),
  glyph+label preserved (already present — just retoned); `OutcomeBadge` → `StatusPill`; the record
  form → console `Select`/`Input` + round primary `Action`; honesty rule — a `failed`/`contradicts`
  badge is never dimmer/smaller than `passed`.
- `frontend/src/components/workspace/thread-list-panel.tsx` — `<section>` → `Bay`+`BayHeader`; the
  `Threads` label → mono readout; New/Cancel toggle → round icon `Action`; the add form → console
  inputs + round `Action`; the thread list → square selectable rows (active = `--signal` left edge
  tick + `--panel-2`, not a flooded `bg-signal/5`); claim-count chip → mono; `stage · status` →
  mono readout tokens; empty/sign-in-hint states via `AwaitingState`/`--state-warn`.
- `frontend/src/components/workspace/claim-list-panel.tsx` — the largest convert: `Bay`+`BayHeader`;
  claim rows → square sub-bays; `statement` Sans; confidence `%` → mono tabular chip; `kind · status`
  → mono readout; the **Evidence** sub-section → a data list with relation-kind `StatusPill`s
  (`support`→ok, `weaken`→fail, `context`→mute) — currently `bg-signal/10`/`bg-ember/10`, retone to
  state tokens; the **Validations** sub-section → `OutcomeBadge`/`StatusPill`s + the contested/
  validated signal indicator (contested = `state-fail` glyph+label, **equal weight**); all three
  inline forms → console inputs + round actions; evidence external links → `--text` + 0.5px underline,
  hover `--signal` (never blue).
- `frontend/src/components/workspace/checkpoint-timeline-panel.tsx` — the §5.3 **log/stream**
  treatment: `Bay`+`BayHeader`; the existing left `bg-signal/50` bar → a proper left **edge tick**;
  `summary` Sans (`--text`), `notes` Sans (`--text-soft`); refs → mono `role` readout + Sans/mono
  label; `contribution_kind` chip → mono readout label (signal only if it's the live/primary one);
  timestamps mono `--text-faint`; `stage`/`thread-scoped`/parents → mono micro tokens; the sealed-line
  notice → `--state-warn`/dashed-hairline honest note; Validate toggle → `ActionText`; record form →
  console inputs. (No autoscroll/streaming needed — these are fetched lists, not live tails — so the
  §5.3 streaming affordances are N/A here; note it.)

**Tasks.** Convert shared states + validation vocabulary first (everything else depends on them), then
the three panels column by column; retone every `bg-signal/*`/`bg-ember/*` chip to the correct state
token; enforce square rows / round affordances throughout.

**Definition of Done.** The full three-column workspace reads as a command bridge of instrument bays;
every status (claim signal, evidence relation, validation outcome, checkpoint contribution,
branch/funding status) is a glyph+label that survives grayscale; failure never recedes; all
create/validate/fork mutations and write-gating (`canWrite`/`signInHint`/`isInternal`) behave exactly
as before. Typecheck/lint/build pass.

---

## Phase D6 — Motion, honesty/grayscale audit, responsive & a11y polish, cleanup

**Objective.** Finish the system: add the sanctioned liveness motion, prove the acceptance bars, tidy
the breakpoints and accessibility, and remove every dead light-theme artifact.

**Tasks.**
1. **Motion (§6).** Live-dot 1.6s opacity pulse (active rail zone, any "live" readout); bay
   entrance fade-up 8px / `0.4s` `cubic-bezier(0.2,0.8,0.2,1)` with ~40ms stagger across grid
   children; UI hovers/focus `0.15s ease`; menus fade+4px slide `0.18s`. **(Stretch)** metric reel on
   budget/count change (≤0.4s digit roll) — optional, low value here (Decision/Out-of-scope).
2. **Reduced motion (§6).** Audit that *every* animation added in D1–D6 registers a freeze in the
   `prefers-reduced-motion: reduce` block; liveness degrades to a static `● live` dot. Non-negotiable.
3. **Honesty audit (§1, §10.7).** Walk every state: can each bay show its own failure as loudly as its
   success? Contradictions, `failed`/`contradicts` validations, `dead_end` branches, failed funding —
   all equal weight, top-floated, glyph+label+position.
4. **Grayscale test (§0, §10.5).** Desaturate the whole app (devtools filter + a manual pass). Every
   state must remain legible with hue removed. This is the release gate.
5. **Signal-seldom audit (§9.2).** Confirm `--signal` appears on only a fraction of each screen — one
   primary action per zone, the active rail/line marker, active edge ticks, the single live readout.
   Demote leftover decorative crimson to `--text-mute`/state tokens.
6. **Responsive (§4.3).** 12→8→single-column bay reflow; ≤1024 rail collapse; ≤768 header overflow +
   field-grid hidden (grain only); bay padding/gutter steps.
7. **Accessibility.** Focus rings as the 2px `--signal` edge tick (visible, not removed); verify
   contrast of `--text-soft`/`--text-mute`/`--text-faint` on `--panel`/`--ground` meets AA for their
   sizes; keyboard nav through rail + menus; `aria` labels preserved; respect `color-scheme: dark`.
8. **Cleanup.** Remove dead tokens (`ink/paper/line/ember`, `boxShadow.panel`), any orphaned
   `shadow-*`/`rounded-lg` on structure, the old `site-header.tsx` if replaced, and (if desired) the
   `_styleguide` page. Grep for stragglers: `rg "shadow-panel|bg-white/|text-ink|border-line|#1f7a6d|#f7f3ea"`.
9. **Changelog.** Add the release entry to `docs/changelog.md` in the house style (per-phase ledger of
   what landed and why), and note the §10 portability promise is satisfied (swap `--signal`, structure
   unchanged).

**Definition of Done.** All acceptance bars pass: grayscale test, honesty audit, reduced-motion,
signal-seldom, responsive, a11y. `npm run typecheck`/`lint`/`build` clean. No light-theme remnants.
The deployed preview is unmistakably Kamino. Changelog updated.

---

## Deferred instruments (noted, not built)

- **Pipeline / engine DAG (§5.6)** — no OpenTheory analog yet. When `0.7.0` agents land, the
  research-checkpoint DAG (checkpoints as round live nodes, parent-links as hairline edges with
  registration ticks, an in-flight agent action as a travelling packet) is the natural place to apply
  it, on the bare measured field. Out of scope here.
- **Metric reels (§5.5/§8)** — values change on refetch, not a live stream; listed as a D6 stretch.
- **Light / print surface (§9.3)** — no export exists; build when one does, using the inverted ramp.

## Risks & watch-items

- **Token opacity regression (Decision 4).** If tokens are mapped to `rgba()` instead of channel
  triplets, every `/opacity` utility in the codebase breaks silently. Verify the probe in D1 before
  proceeding.
- **Signal overuse.** The current teal `signal` is everywhere; crimson is "seldom." The biggest taste
  risk is a screen that is too crimson. Treat the D6 signal audit as a hard gate.
- **Brand-mark asset.** The awaiting-state breathing mark and shell lockup need a real emblem; resolve
  the asset/interim in D1 so it isn't a late blocker.
- **Contrast on obsidian.** `--text-faint` (`#5A574F`) on `--panel` is intentionally ambient; confirm
  it clears AA for the sizes it's used at (timestamps/IDs) or bump those usages to `--text-mute`.
- **Logic drift.** This is presentation-only. Any change to a query key, mutation, `useActingIdentity`
  gate, or read-schema field during a "re-skin" is a defect — keep diffs to className/markup/tokens.

## Verification per phase

Every phase: `cd frontend && npm run typecheck && npm run lint && npm run build`, plus a visual pass
against `_styleguide` and the live dev server (`npm run dev`), plus a devtools grayscale spot-check of
any new surface. No backend or test changes are expected (the frontend has no test suite today); if
one is added later, it is out of this plan's scope.

## Portability checklist satisfied at the end (§10)

1. Re-skin = change `--signal` only ✅ (single token).
2. §2 substrate/shape/line/proportion untouched by theme ✅.
3. State tokens (§9.3) constant ✅.
4. Mono = data, Sans = prose ✅ (enforced per-component).
5. Grayscale test ✅ (D6 gate).
6. Every animation in the reduced-motion block ✅ (D6 audit).
7. Honesty audit ✅ (D6).
