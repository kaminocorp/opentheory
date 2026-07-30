# 0.15.0 — Frontend design overhaul: the quiet minimalist re-skin

**Goal.** A comprehensive visual overhaul of the entire frontend: retain the stack and the
dark-mode identity, but make the product cleaner, simpler, more minimalist, and easier to
read/navigate/use — "what would OpenTheory look like if OpenAI had designed it?" was the brief's
guide. **Presentation only: every page, section, panel, and write flow is functionally
unchanged.** No backend, schema, API, or migration change; no component props changed except
where noted (two ornamental `Bay` props and one `BayHeader` rename, all internal to the
frontend).

## Why

The `0.6.4` "OpenTheory Console" language was deliberately ornamental: a baked graph-paper
grid + grain + vignette under everything, recessed bays with inset shadow lips, corner
registration brackets, chamfered headers, a tick-fret "registration band", hatched fills, and
all-caps letterspaced mono kickers on nearly every label. It had a strong identity but worked
against scanability: decorative pixels competed with data, the all-caps mono labels were harder
to read than sentence-case sans, `#807C74`-tier muted text ran low on contrast, and square-
everything plus 0.5px borders read as dated rather than precise on non-retina displays.

The overhaul keeps what carried *meaning* (the state vocabulary, the honesty rules, the sparing
crimson signal, mono-for-data) and deletes what was only *style*.

## The new language in one paragraph

Neutral near-black ramp (`#101010 / #181818 / #202020`) with hierarchy from one step of
lightness per nesting level; 1px `rgba(255,255,255,0.08)` borders; 12px card / 8px control /
pill radii; sentence-case IBM Plex Sans for all UI text with IBM Plex Mono demoted to genuine
data (hashes, ids, formulas, tabular numbers, machine tokens); crimson `--signal` kept as the
single sparing accent (primary buttons, active-tab underline, selected-row tick, focus ring);
state colours and glyphs unchanged in role; motion reduced to liveness + small fades.

## What changed, where, how, why

### Foundations

- **`frontend/src/app/globals.css`** (rewritten) — the highest-leverage change.
  - *Removed:* the measured-field grid images (`--field-image`, minor/major gaps, crosshair
    tile), the fractal-noise `--grain` overlay, the `body::before/::after` grain + vignette
    layers, `.field-surface`, `.bay-chamfer`, `.hatch`, and the ≤768px grid-hiding media query
    (nothing to hide anymore). *Why:* every one of these was decorative texture competing with
    content.
  - *Ramp re-tuned:* warm obsidian (`#0D0C0B/#161513/#1C1A18`, warm greys) → neutral near-black
    (`#101010/#181818/#202020`) with **lighter muted tiers** (`--text-mute #8E8E8E`,
    `--text-faint #6E6E6E`) for legibility. Channel-triplet storage (Decision 4) preserved so
    Tailwind opacity modifiers keep working.
  - *Borders:* 0.5px → **1px** at lower alpha (`0.08`/`0.14`). 0.5px lines render inconsistently
    off-retina; 1px at low alpha is the contemporary equivalent.
  - *Radius tokens:* `--r-card: 12px`, `--r-control: 8px` added; `--r-built` kept as a **legacy
    alias = 8px** so every existing `rounded-built` call site rounded automatically;
    `--r-inset` 2px → 6px; `--r-alive` (pill) unchanged.
  - *`.bay`:* recessed instrument bay (inset highlight + shadow lip) → flat card (panel bg, 1px
    hairline, 12px radius).
  - *`.field-input`:* square panel-fill + focus edge-tick → quiet `rgba(255,255,255,0.02)` fill,
    8px radius, **focus brightens the border** (no tick, no glow).
  - *`.menu`:* square → 12px radius, softer single shadow, `--panel-2`.
  - *Motion:* `bay-enter` softened (8px/0.4s → 4px/0.3s); brand-mark cascade/assemble, pulse,
    breathe, menu-pop and the **full reduced-motion freeze block** kept as-is.
- **`frontend/tailwind.config.ts`** — radius scale now `card/control/built(alias)/alive/inset`;
  `borderWidth.hairline` 0.5px → 1px; colour wiring untouched.

### Primitives (`frontend/src/components/console/`)

- **`registration.tsx` deleted** (RegistrationBrackets + RegistrationBand — the corner L-marks
  and tick-fret ornament). Exports removed from `index.ts`; all call sites cleaned.
- **`bay.tsx`** — `Bay` loses the `bracketed`/`chamfer` props (ornament); `BayHeader`'s `band`
  prop (registration-band underline) becomes **`divider`** (plain hairline border-bottom); the
  header label is now a sans 14px/500 title instead of a mono uppercase kicker; counts render
  mono 12px tabular (was 11px).
- **`readout-label.tsx`** — the biggest single legibility change. The one-sanctioned-all-caps
  mono kicker (11px/0.14em/UPPERCASE) becomes a **sans 13px/500 sentence-case label** in
  `--text-soft`. All ~25 call sites already passed sentence-case strings, so no caller changed.
  `tone="signal"` retained.
- **`action.tsx`** — pills retained; ghost gains a `bg-white/5` hover wash; the text variant
  drops its decorative `→` arrow and the signal hover (now muted → text); destructive ring
  softened to `state-fail/70`; the **hatched inert fill replaced** by `bg-white/[0.04]` + faint
  text (shape/skin split and the no-tailwind-merge discipline preserved).
- **`status-pill.tsx`** — mono UPPERCASE 11px → **sans 12px `capitalize`**, `bg-white/[0.03]`.
  `capitalize` matters: several call sites pass raw enum values (`project.status`,
  `member.role`), which previously relied on CSS uppercasing.
- **`state.ts`** — glyph softening: `fail` ■ → **✕**, `mute` ▣ → **○** (`ok ✓ / run ● / warn ▲`
  unchanged). Comments referencing the old glyphs updated (`validation-controls.tsx`).
- **`metric-readout.tsx`** — nested tile → 8px radius `bg-white/[0.02]`; label sans 12px muted;
  value stays mono tabular (18px).
- **`awaiting-state.tsx`** — label mono-caps → sans 13px; error keeps full `--state-fail`
  weight; the brand-mark cascade/steady behaviour untouched.
- **`modal.tsx`** — title ReadoutLabel → sans 14px/500; inherits the new `.bay` card look;
  focus/scroll-lock/portal behaviour untouched.
- **`input.tsx`** — padding 2.5→3 to suit the 8px radius; a11y name-fallback logic untouched.
- **`icon.tsx`** — stroke 1.25/1.5 → **1.5/1.75**; hairline-thin strokes read as spindly
  against the cleaner surfaces.

### Shell (`frontend/src/components/shell/`)

- **`app-shell.tsx`** — header loses the chamfered clip-path panel; now `bg-ground/90` +
  `backdrop-blur` + bottom hairline. The inert search field becomes a rounded-full quiet pill.
  `<main>` no longer sits on a textured field (the body is flat).
- **`command-rail.tsx`** — active zone: 2px signal edge tick + pulsing LiveDot → **filled
  rounded tile** (`bg-white/[0.07]` active, `/[0.04]` hover), the OpenAI-sidebar pattern. The
  inert Agents zone drops the hatch (plain faint icon). All aria/labels/roles unchanged.
- **`auth-menu.tsx` / `invitation-inbox.tsx`** — inline `0.5px` borders → 1px; everything else
  inherits from tokens/primitives.

### Feature sweep (presentation-only; every hook, mutation, and gate untouched)

Mechanical passes across all of `src`: every inline `0.5px solid|dashed` border → 1px; every
local `font-mono … uppercase tracking-[…]` label → sans sentence case (with `capitalize` where
the text is a raw enum); `AwaitingState`/`PanelState` labels sentence-cased ("loading projects"
→ "Loading projects").

Per-file notes:

- **`projects/project-card.tsx`, `app/page.tsx`, `workspace/project-header.tsx`** — `bracketed`
  / `chamfer` usages removed. Header's contested-claims strip and compact counts strip
  de-mono'd (counts themselves stay mono tabular).
- **`workspace/project-tabs.tsx`** — tab labels mono-caps 11px → sans 13px/500; the 2px signal
  active underline stays (it is structural, grayscale-safe, and genuinely OpenAI-ish).
- **`workspace/project-workspace.tsx`** — Instruments context strip de-mono'd; awaiting labels
  cased.
- **`workspace/thread-list-panel.tsx`, `claim-list-panel.tsx`,
  `checkpoint-timeline-panel.tsx`** — `band` → `divider` + `pt-3` content offset; stage/kind/
  status meta-lines and ref-role labels → sans capitalize; stage/contribution chips
  `rounded-inset` mono-caps → rounded-full sans capitalize. Selected-row signal edge tick and
  the checkpoint stream's neutral left rule kept.
- **`workspace/branch-bar.tsx`** — pill status text de-mono'd; dead-end strike-through, glyphs,
  and the marked-not-flooded close flow kept.
- **`workspace/funding-panel.tsx`** — history source/kind label de-mono'd; money stays mono
  tabular. (The `uppercase` on the currency input is functional ISO-code entry and stays.)
- **`workspace/validation-controls.tsx`, `collaborators-panel.tsx`,
  `research-crew-panel.tsx`, `project-edit-form.tsx`, `markdown.tsx`,
  `rich-text-editor.tsx`** — inherit entirely from tokens/primitives; no local changes beyond
  the mechanical border pass (avatar-initials `uppercase` is functional and stays).
- **`workspace/toolbench/toolbench-panel.tsx`** — scope note de-mono'd; result-contract pills no
  longer `.toUpperCase()`; awaiting labels cased. Instrument-picker pills keep mono (instrument
  names are machine tokens).
- **`workspace/toolbench/drive-forms.tsx`** — `Field` labels and `AddRow` de-mono'd to the
  shared label style.
- **`workspace/toolbench/result-view.tsx`** — the honesty cards keep their state-coloured edge
  ticks and glosses but lose the hatch fill and mono-caps captions (now sans 12px/500 in the
  state colour); `KeyValue`/geometry `dt` labels → sans; the outcome StatusPill no longer
  uppercased. Formulas, chips, and the provenance/blame footer stay mono — they are data.
- **`workspace/toolbench/assumptions-editor.tsx`** — "Assumptions" heading → shared label style.
- **`workspace/agent-pass/agent-pass-panel.tsx`, `agent-run-trace.tsx`** — role/earlier-passes
  labels de-mono'd; `AgentRunStatusPill` and the failed-step pill no longer uppercase; the
  dropped/skipped step keeps its dashed border but loses the hatch.
- **`app/styleguide/page.tsx`** — rewritten for the new system: probe, card header/nested
  surface, metric readouts, pills, dots, actions, icons, fields, awaiting states, label tones,
  and the grayscale legend. Bracket/chamfer/band demos removed.

### Docs

- **`docs/blueprints/design-system.md`** — rewritten to describe the new language (the blueprint
  must match the code). The two retained laws — grayscale survival and honesty-over-comfort —
  are now §0.
- **`docs/changelog.md`** — `0.15.0` index line + section.

## What deliberately did *not* change

- **All functionality**: every query, mutation, gate (`canWrite`/`canManage`/seal checks),
  aria pattern (tablist roving tabindex, modal focus trap, rail accessible names, live regions),
  keep-alive tab mounting, and the `?tab=` contract.
- **The honesty surface**: contested claims at full weight above the fold; refuted/undecided
  cards with state-coloured edges that never read as a pass; failed = same size as passed.
- **The state vocabulary** (tones + glyph-carries-meaning) and the signal/state-fail split.
- **IBM Plex Sans/Mono** (self-hosted via next/font) — the mono/sans *split* is retained; only
  mono's surface area shrank to genuine data.
- **The brand mark** and its cascade/assemble animations, the reduced-motion freeze, the
  `:focus-visible` signal ring, tabular numerics, and the channel-triplet token wiring.
- **Legacy aliases kept** (`--r-built`, `rounded-built`, `--hairline-lit`, `--tick`) so nothing
  breaks silently; new code should use `card`/`control`.

## Verification

```bash
cd frontend && npm run typecheck && npm run lint && npm run build   # all clean
```

Runtime spot-check against a local dev server (pointed at the live Fly backend):
`/`, `/styleguide`, and `/projects/[id]` all render 200; the served CSS contains the new tokens
(`--r-card: 12px`, `--hairline: rgba(255,255,255,0.08)`) and **zero** occurrences of
`field-image`/grain/vignette/`bay-chamfer`/`hatch`.

**Unverified:** no pixel-level browser walk was possible in this pass (no connected Claude
browser extension — the same limitation recorded for `0.14.0` §8). Recommended eyeball pass
when a browser is available: `/styleguide` (all primitives + grayscale emulation), the project
deepdive's five tabs, a toolbench run's result card, and the sign-in dropdown.
