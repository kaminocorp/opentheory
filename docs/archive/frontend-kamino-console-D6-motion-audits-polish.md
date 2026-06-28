# Frontend — Kamino Console · Phase D6 (Motion, Audits, Polish) — Completion

> Implements **Phase D6** of `docs/executing/frontend-kamino-console-redesign.md`:
> the finishing phase — sanctioned liveness motion, the reduced-motion freeze audit,
> the three release gates (honesty, grayscale, signal-seldom), responsive + a11y
> polish, dead-artifact cleanup, and the release changelog entry. Presentation-only;
> **no** backend / schema / API / data-flow change.

**Status:** complete. `typecheck` / `lint` / `build` green; all 6 routes generated.
The three acceptance gates pass **by construction** (grep-evidenced below); a final
live devtools desaturation pass is the one step that needs a browser and is noted.

**Version:** the whole D1–D6 conversion ships as **`0.6.4`** (folded into the current
`0.6.x` line — the user's call per Decision 6). The release entry is in
`docs/changelog.md`; this doc is the phase-scoped detail.

---

## What landed, where, and why

### 1. Liveness motion (§6) — `globals.css`

- **`@keyframes bay-enter`** + the **`.enter-stagger`** container utility: a bay's
  direct children "power on" with a fade + 8px lift (`0.4s cubic-bezier(0.2,0.8,0.2,1)`)
  in a ~40ms `nth-child` cascade. Chosen as a **component-agnostic container class**
  (no per-item `index` prop threaded through cards/panels) — adding the class to a grid
  is the whole change. Applied to the two real bay grids: the **project index card
  grid** (`project-list.tsx`) and the **workspace instrument 3-column grid**
  (`project-workspace.tsx`).
- The other liveness motions already existed from D1/D2 (the rail's `LiveDot` pulse on
  the active zone, the `AwaitingState` breathe, the menu `menu-pop`); D6 only added the
  entrance and audited the set.

### 2. Reduced-motion freeze (§6, non-negotiable) — `globals.css`

`.enter-stagger > *` was added to the explicit `prefers-reduced-motion: reduce`
freeze list (`animation: none !important`). Because each child's **base** state is
`opacity: 1` (only the keyframe `from` is transparent), removing the animation leaves
bays fully visible rather than stuck mid-fade. The global `*` reset (duration → 0.001ms)
remains the catch-all that also neutralises Tailwind's `animate-pulse` count shimmer.

### 3. Keyboard focus ring (§4 a11y) — `globals.css`

A global `:focus-visible` rule renders the system's **2px `--signal` outline**
(offset 2px) on `a / button / summary / [role=button] / [tabindex]` — so every
custom round button (the New/Cancel toggles, the open-affordance, line pills) gets a
visible, on-language focus ring instead of the browser default. Scoped to
`:focus-visible` (keyboard), so a mouse press doesn't ring; console fields keep their
own inset `--signal` focus tick (the `.field-input` rule), untouched.

### 4. Responsive step (§4.3) — `app-shell.tsx`

The `<main>` gutter now steps with the field: `px-4 py-5` on mobile → `sm:px-6 sm:py-6`
(the `--gutter-mobile` 16px → `--gutter` 24px move). The rest of §4.3 was already in
place from D2/D4 (rail icon-width + `lg:w-14`, header search `hidden md:flex`, the
field-grid hidden ≤768 in `globals.css`, and the bay grids' `sm/lg/xl` reflows).

### 5. Cleanup (§10.8)

- `site-header.tsx` was already removed in D2; confirmed **deleted with zero dangling
  imports**.
- Dead tokens (`ink`/`paper`/`line`/`ember`, `boxShadow.panel`): confirmed **already
  gone** from `tailwind.config.ts` and `globals.css` (D1 was thorough) — a repo-wide
  grep finds none.
- The `styleguide` route is **kept**, dev-gated (`notFound()` unless
  `NEXT_PUBLIC_AUTH_DEV`), as an ongoing grayscale-test aid — harmless (404) in prod.

---

## Release-gate audits (grep-evidenced, by construction)

- **Signal-seldom (§9.2).** At rest, `--signal` appears only on: the active rail
  edge tick + pulse dot, the active thread-row tick, the selected branch pill, the one
  `ShieldCheck` "Kamino internal" identity glyph, and the primary `Action` per form.
  Every other `signal` reference is `hover:text-signal` (hover-only) or the
  `ReadoutLabel` `signal` *tone option*. Crimson is a fraction of each screen.
- **Motion / reduced-motion (§6).** Enumerated every trigger (`anim-pulse`,
  `anim-breathe`, `menu-pop`, `enter-stagger`, Tailwind `animate-pulse`); each is
  frozen — the four custom ones explicitly, the Tailwind one by the global `*` reset.
- **Honesty / grayscale (§1).** Every `state-*` colour is paired with a glyph
  (`StatusPill`, `AlertTriangle`) or sits on literal message text — never colour
  alone. Failure surfaces (contradictions, `failed`/`contradicts`, `dead_end`, the
  sealed line, the error `AwaitingState`) render at full weight and float to the top
  of their bay. Meaning survives hue removal.

---

## Decisions & deviations (with rationale)

1. **`styleguide` kept (not deleted).** The plan allowed deleting it; it is retained
   because it is the cheapest way to re-run the grayscale test on the primitive set,
   and it is dev-gated so it never ships. Easy to drop later if undesired.
2. **Entrance applied to grids only, not every bay.** Staggering the index cards and
   the three instrument columns is the on-spec "cascade across grid children"; the
   stacked frame bays (header/funding/branch) deliberately do **not** animate, to
   avoid a slow top-to-bottom waterfall on an already data-dense view.
3. **Metric reels (§5.5/§8) skipped** (the plan's explicit D6 stretch / out-of-scope):
   values change on refetch, not via a live stream, so a digit-roll is low-value here.
   Noted as a future item when a live stream exists.

## Explicitly NOT done (scope / environment)

- A **live devtools desaturation pass** and an in-browser reduced-motion check —
  the primitives are built to pass and the gates hold by construction, but the final
  visual confirmation needs a running app (consistent with how D1–D5 flagged the
  visual pass). No code blocks it.
- No query key, mutation, route, gate, or read-schema field changed anywhere in D6 —
  purely `globals.css` + four className/markup touches.

---

## Verification (reproduced)

- **`npm run typecheck`** → clean. **`npm run lint`** → clean. **`npm run build`** →
  success; all 6 routes generated (`/projects/[projectId]` server-rendered on demand,
  `/` and `/styleguide` static).
- **No legacy tokens** anywhere in `src` (outside the dev-only `styleguide`); the
  Tailwind config + `globals.css` carry no dead palette.

## Portability checklist satisfied (§10)

1. Re-skin = change `--signal` only ✅ (single token; everything else is structure / state).
2. §2 substrate / shape / line / proportion untouched by theme ✅.
3. State tokens constant, independent of signal ✅.
4. Mono = data, Sans = prose ✅ (enforced per-component across D3–D5).
5. Grayscale test ✅ by construction (glyph + label + position carry every state).
6. Every animation registered in the reduced-motion block ✅ (D6 audit).
7. Honesty audit ✅ (failure at equal weight, top-floated, never hue-only).

The deployed preview is, end to end, the Kamino Console.
