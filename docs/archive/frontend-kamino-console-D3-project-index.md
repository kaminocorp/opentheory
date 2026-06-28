# Frontend — Kamino Console · Phase D3 (Project Index Surface) — Completion

> Implements **Phase D3** of `docs/executing/frontend-kamino-console-redesign.md`:
> converts the landing/index (`/`) — hero, the three feature tiles, the create-
> project orchestrator, and the project grid — into the bay/bracket grammar with the
> mono/sans split and honest states. Presentation-only; **no** backend / schema /
> API / data-flow change, all query/mutation logic preserved byte-for-byte.

**Status:** complete. `typecheck` / `lint` / `build` green; the converted index
SSRs (hero kicker, metric readouts, bays, and the honest loading state all present
in the prerendered HTML). Builds on D1's `@/components/console` primitives + the D2
shell.

**Version:** still provisional (see the D1 doc) — changelog deferred to merge/D6.

---

## What landed, where, and why

### 1. `src/app/page.tsx` — the hero (§3.2)

- The **4xl/5xl billboard `h1` → a modest console title** (Sans 22–24 / 500 /
  `-0.01em`). "Consoles are not landing pages" — hierarchy comes from weight + the
  field, not size.
- The **"Research Ledger" kicker → a mono `ReadoutLabel`** (default `mute` tone, not
  signal — the index has no "live" zone, and signal stays seldom).
- The **three metric tiles → a `bracketed Bay` of metric readouts**: each row is a
  mono `ReadoutLabel` (the category) + a mono value, divided by hairlines. Dropped
  `rounded-lg` / `border-line` / `bg-white/70` / `shadow-panel`. (The values
  —"Parallel"/"Provenance"/"Token-bound"— are short machine-tag descriptors, set in
  mono per §5.5; they are static copy, not live counts.)

> **Note:** the plan mentions converting a "Fund project" button → primary `Action`.
> There is no Fund button on the current index (the only index action is "New
> project", in the orchestrator below) — so nothing to convert there. Flagged so the
> omission reads as intentional, not missed.

### 2. `src/components/projects/project-card.tsx` — `<article>` → bracketed `Bay`

- `<article …rounded-lg border bg-white/75 shadow-sm>` → **`<Bay as="article"
  bracketed>`** (the recessed surface + the four corner registration brackets).
- **`status` → a round `StatusPill`** via a `status → StateTone` map
  (`draft→mute ▣`, `active→run ●`, `paused→warn ▲`, `completed→ok ✓`,
  `archived→faint ·`). Glyph + label carry the meaning, so it survives grayscale.
- Title **Sans** `--text`; `question` **Sans** `--text-soft`; `description` **Sans**
  `--text-mute` (line-clamped). The open affordance → a **round** ghost icon link
  (round = actionable). The Threads / Validation / Funding footer → mono
  `ReadoutLabel`s with `Icon`-wrapped glyphs.

### 3. `src/components/projects/project-list.tsx` — states → `AwaitingState`

The three bespoke loading / error / empty blocks collapse to **`AwaitingState`**
(the mark holds the frame, §5.9), each framed in a `Bay` (`min-h-72`):
`loading` (breathing) / `project index unavailable` (error — the mark **stops** and
holds steady, equal weight, §1) / `no projects yet` (empty). The `useQuery` logic
and the responsive card grid are unchanged.

### 4. `src/components/projects/projects-section.tsx` — re-skinned (logic untouched)

*(Not in the plan's literal D3 file list — included deliberately; see Decisions.)*
The "New project / Cancel" toggle → a round `ActionGhost`; the create form → a
narrative `Bay as="form"` with console `Input` / `Textarea`, a mono `ReadoutLabel`
for the slug field, and a primary `Action` submit (with `pending`); the sign-in
gate → `--state-warn`, the create error → `--state-fail`. **Every hook, the
`slugify` logic, the `createMutation`, `canSubmit`, and the `canWrite`/`signInHint`
write-gating are byte-for-byte unchanged.**

### 5. `src/components/console/bay.tsx` — `Bay` now forwards element props

`Bay` accepts and spreads arbitrary element props
(`BayOwnProps & Omit<ComponentPropsWithoutRef<"div">, …>`), so it can be used as a
`<form>` (the create form above) and — importantly — **carry an `id` for the
`#funding` anchor the D2 rail already links to** (D4 will set it). A small primitive
upgrade that pays off across later phases.

---

## Decisions & deviations (with rationale)

1. **Included `projects-section.tsx` beyond the literal file list.** It is the
   index's interactive orchestrator (the create form + write-gating) and renders in
   the middle of the now-converted index; leaving it in light-theme markup would put
   a white form on the obsidian field — gutting the conversion. Converted with logic
   byte-for-byte. Documented so the scope expansion is explicit, not silent.
2. **Metric values set in mono.** They are short machine-tag descriptors on a
   console readout (§5.5), so mono over sans — even though they are words, not
   numbers. (If these ever become live counts, they are already in the right place.)
3. **Card open affordance is a plain `<a>`, kept as-is.** The original used a full-
   navigation anchor (not Next `Link`); changing it would be a behaviour change, out
   of a presentation-only phase. Restyled to a round ghost, navigation untouched.
4. **Error/empty copy compressed to one-line mono readouts.** `AwaitingState` is a
   single-line state (mark + readout label), so the old multi-line titles +
   descriptions become terse honest readouts ("project index unavailable"). This is
   the §5.9 treatment, not a loss of information.

## Explicitly NOT touched (scope discipline)

No query key, mutation, route, `useActingIdentity` gate, or read-schema field
changed. The **workspace** (project detail) surfaces remain pre-Kamino — they render
transitional inside the D2 shell and convert in **D4** (header/budget/branch bar) and
**D5** (the three instrument bays). This is the planned D3 end-state.

## Signal-seldom check (passes by construction)

After conversion, `--signal` on the index appears only on the "Create project"
primary `Action` (and only while the form is open) plus the active rail marker
(D2). Every former teal accent — the kicker, every card status, every footer icon —
is now `--text-mute` or a **state tone**, so the §9.2 discipline holds without a
separate pass.

---

## Verification (reproduced)

- **`npm run typecheck`** → clean. **`npm run lint`** → clean.
  **`npm run build`** → success; all 6 routes generated.
- **Converted index SSRs** — the prerendered `/` HTML contains the hero kicker
  (`Research Ledger`), the metric readouts (`Active Threads`, `Token-bound`), three
  `.bay` surfaces (header chamfer layer + metric bay + the project-list frame), and
  the honest `loading projects` state. (The project **cards** + their `StatusPill`s
  render client-side after the `useQuery` resolves, so they are correctly absent
  from the static HTML — the `StatusPill` primitive itself was proven in the D1
  styleguide.)

> Not done here (manual / later): a live visual + grayscale spot-check of the card
> grid with real project data, and of the create form open state — quick via
> `NEXT_PUBLIC_AUTH_DEV=true npm run dev`.

## What D4 can rely on

The index is fully Kamino. `Bay` now forwards `id`/handlers, so D4 can mount the
funding panel as `<Bay id="funding">` (satisfying the rail anchor) and the workspace
forms as `Bay as="form"`. Next: the workspace frame — the project header (metric-
readout grid + the honest contradictions surface), the budget/funding showcase, and
the branch/line bar.
