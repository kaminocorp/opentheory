# Frontend — Kamino Console · Phase D5 (Instrument Bays) — Completion

> Implements **Phase D5** of `docs/executing/frontend-kamino-console-redesign.md`:
> converts the dense heart of the workspace (§5.1/5.2/5.3) — the three instrument
> columns (**threads**, **claims + evidence**, the **checkpoint timeline**) — plus
> the shared validation vocabulary and the shared panel-state helpers they all
> depend on. Presentation-only; **no** backend / schema / API / data-flow change,
> all queries / mutations / role-gating preserved byte-for-byte.

**Status:** complete. `typecheck` / `lint` / `build` green; the five converted files
carry **zero** legacy tokens — and the grep now finds **no** legacy tokens anywhere
in `src` (outside the dev-only `styleguide`). The workspace body is fully Kamino.
Builds on D1's primitives and the D2 shell / D4 frame.

**Version:** still provisional (see the D1 doc) — changelog deferred to merge/D6.

---

## What landed, where, and why

Converted in dependency order: the shared states and the validation vocabulary
first (every column consumes them), then the three columns.

### 1. `panel-state.tsx` — shared loading / error / empty (§5.9)

The three helpers (`PanelLoading` / `PanelError` / `PanelEmpty`) are now thin
wrappers over **`AwaitingState`** — "the mark holds the frame". Loading breathes;
error/empty hold steady (read "stopped," not "loading"); error renders at full
`--state-fail` weight (§1). The per-panel `lucide` icons are gone — the breathing
brand mark is the single frame-holder. Call sites stay drop-in (a single string).

### 2. `validation-controls.tsx` — the validation vocabulary

- **`OUTCOME_META` retoned from bespoke `signal/ember` classes onto the shared
  `STATE_META` tones:** `passed→ok ✓`, `failed→fail ■`, `inconclusive→mute ▣`,
  `needs_reproduction→warn ▲`, `contradicts→fail ▲` (fail colour, triangle glyph to
  read distinctly from `failed`'s ■ and echo the overview's contradiction marker),
  `retract→faint ·`. Meaning rides on **glyph + label**; colour only reinforces.
- **`OutcomeBadge` → `StatusPill`** (round, mono, glyph+label) — so a `failed` /
  `contradicts` badge is structurally never dimmer or smaller than `passed` (§1).
- **`RecordValidationForm` → console controls:** mono `Select` (outcome enum) + sans
  `Input` (notes) + a round primary `Action`; sign-in gate → `--state-warn`, errors
  → `--state-fail`. The mutation, the checkpoint/overview invalidation, and the
  `invalidateKey` plumbing are unchanged.

### 3. `thread-list-panel.tsx` — the threads bay (§5.1)

`<section>` → `Bay` + `BayHeader` (the `GitBranch` glyph rides inside the readout
label; header gains a mono thread **count**). New/Cancel → a **round** icon toggle.
Each thread → a **square selectable row** whose active state is a **`--signal` left
edge tick + `--panel-2`**, never a flooded fill (§9.2); title Sans, question Sans
`--text-soft`, claim-count mono, `stage · status` a mono readout token. Add form →
console `Input`s + a round `Action`. States via the new `AwaitingState` wrappers.

### 4. `claim-list-panel.tsx` — claims + evidence (the largest convert)

- `Bay` + `BayHeader` (`ListChecks`, mono claim count); the no-thread guard → a
  centered `AwaitingState` ("Select a thread") in a `Bay`.
- Each claim → a **square sub-bay** on `--panel-2`: `statement` Sans; confidence `%`
  → a mono tabular `--r-inset` chip; `kind · status` → a mono readout.
- **Evidence** → a data list: relation kind → a `StatusPill` (`support→ok`,
  `weaken→fail`, `context→mute`); external links → the **`.console-link`** register
  (underline, hover `--signal`, never blue); `source_type` a mono `· token`.
- **Validations** → `OutcomeBadge` pills + the honest signal indicator: `contested`
  is a full-weight `fail ▲` pill and `validated` an `ok ✓` pill — equal weight, glyph
  + label (§1). Both inline forms → console controls.

### 5. `checkpoint-timeline-panel.tsx` — the log/stream (§5.3)

`Bay` + `BayHeader` (`GitCommitHorizontal`, mono on-line count). Each checkpoint →
a **square log entry** on `--panel-2` with a **neutral left rule** (`--hairline-strong`,
not signal — none of these is "the live one"); `summary` Sans, `notes` Sans
`--text-soft`; refs → a mono `role` readout + a **Sans label / mono hash** split
(the §3.1 data-vs-prose rule); `contribution_kind` → a mono `--r-inset` token (mute,
not signal); the meta line → mono micro-tokens (timestamp/stage/parents) with the
author *name* kept Sans. The sealed-line notice → a **warn-marked, dashed-hairline
honest note** (`AlertTriangle` in `--state-warn`), not hidden or dimmed. Add form →
console `Input` + `Textarea` + round `Action`. (No streaming affordances — these are
fetched lists, not a live tail; noted in-file.)

---

## Decisions & deviations (with rationale)

1. **Empty/loading/error copy trimmed to terse one-line readouts.** `AwaitingState`
   is a mark + **one** mono line (§5.9); the previous monument-era guidance
   sentences ("Decompose the question into a first thread…") don't fit and would wrap
   as uppercase mono. Replaced with honest short readouts ("No threads yet", "Select
   a thread", "No checkpoints on the main line", …). A reviewer call — flagged in case
   the onboarding guidance is wanted back (it would need an optional Sans `hint` slot
   on `AwaitingState`, a small principled extension).
2. **Surface ramp (forced by `.field-input`).** Console fields paint `--panel`, so a
   form *container* must sit on `--panel-2` for fields to be visible. The depth
   hierarchy is therefore: column `Bay` (`--panel`) → row sub-bay (`--panel-2`) → form
   tray (`--panel-2`, separated from its row by a hairline + spacing, not a fill). All
   form trays are `--panel-2`; inputs read as recessed wells inside them.
3. **Inline toggles use a plain text/icon button in the `ActionText` register,
   without the forced trailing `→`.** "Attach"/"Validate"/the New toggle all flip to
   "Cancel", where a trailing arrow is wrong — the same reasoning D4 used for the
   back-link. Same visual register (text → `--signal` on hover), correct semantics.
4. **Checkpoint left rule is neutral (`--hairline-strong`), not `--signal`.** It is
   the log's structural rule, and signal is seldom — no past checkpoint is "live."
5. **Header panel counts added** (threads / claims / on-line checkpoints). Derived
   purely from already-fetched data — no new query, no schema touch — and `BayHeader`
   already has the slot, so it is presentation only.
6. **`compact` retained on `RecordValidationForm`** (callers pass it); it now only
   tunes the form gap, since console fields are otherwise fixed-size. Kept to avoid
   churning the two call sites.

## Explicitly NOT touched (scope discipline)

No query key, mutation, route, `useActingIdentity` gate (`canWrite` / `hydrated` /
`signInHint`), read-schema field, the checkpoint **line-scoping filter**, the
**seal-gating** logic, or the validation **invalidation** plumbing changed. The
claim `signal` (`contested` / `validated`) is still the server-derived value, read
verbatim. Pure className / markup / token work.

## Signal-seldom check

In the instrument columns, `--signal` now appears only on: the **active thread row**
edge tick, the **primary `Action`** submit per form, and as the **hover target** of
inline toggles / `.console-link` / the input focus edge tick. Every former teal
accent (panel-label icons, evidence/validation/relation chips, the checkpoint left
bar, ref roles, contribution kinds) is now `--text-mute` or a **state tone**.
`contested` / `failed` / `weaken` use `--state-fail` (status, not brand), keeping the
§9.2 separation intact.

---

## Verification (reproduced)

- **`npm run typecheck`** → clean. **`npm run lint`** → clean (the one transient
  `cn`-unused warning was removed). **`npm run build`** → success; all 6 routes
  generated (`/projects/[projectId]` server-rendered on demand).
- **Conversion completeness** — grep over the five files finds **none** of
  `bg-white | text-ink | border-line | ember | shadow-panel | shadow-sm | bg-paper |
  rounded-md | rounded-lg | text-paper | bg-ink | #1f7a6d | #f7f3ea`; and the same
  grep across **all of `src`** (excluding the dev-only `styleguide`) is now **empty** —
  D5 was the last conversion. The app body is fully on the Kamino token layer.

> Not done here (needs a running backend + a manual pass, and is the D6 gate): a
> live render of the three columns with real project data, the **devtools grayscale
> test** (every status must read with hue removed), the **reduced-motion** audit, and
> the **honesty** walk (contested claims, failed/contradicts validations, sealed
> lines at equal weight). The primitives are built to pass these; D6 proves them.

## What D6 can rely on

The entire user-facing app is now Kamino tokens + primitives. D6 is the finishing
phase: liveness motion (bay entrance + any live dot), the reduced-motion freeze
audit, the honesty + grayscale + signal-seldom gates, responsive/a11y polish, the
dead-token/`styleguide` cleanup, and the `docs/changelog.md` release entry. No
legacy token remains for D6 to chase down — only the audits and motion.
