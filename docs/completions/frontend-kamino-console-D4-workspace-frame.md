# Frontend — Kamino Console · Phase D4 (Workspace Frame) — Completion

> Implements **Phase D4** of `docs/executing/frontend-kamino-console-redesign.md`:
> converts the workspace orchestrator chrome and the two cross-cutting bars that sit
> above the three instrument columns — the project **header**, the **budget/funding**
> showcase, and the **branch/line bar**. Presentation-only; **no** backend / schema /
> API / data-flow change, all query/mutation/role-gating preserved byte-for-byte.

**Status:** complete. `typecheck` / `lint` / `build` green; the three converted files
carry **zero** legacy tokens, and the only remaining light-theme files are exactly
the D5 targets. Builds on D1's primitives (+ the new `MetricReadout`) and the D2 shell.

**Version:** still provisional (see the D1 doc) — changelog deferred to merge/D6.

---

## What landed, where, and why

### 0. New primitive — `src/components/console/metric-readout.tsx`

`MetricReadout` (§5.5): a square nested tile (`--panel-2`) carrying a mono
`ReadoutLabel` + a mono tabular value, with optional `title` and `valueClassName`.
Defined once because D4 needs it in **two** places — the header's 6-up count grid
and the budget's 3-up grid — and any future live count lands here. Exported from the
console barrel.

### 1. `project-workspace.tsx` — the header (§5.5 + §1)

- The project **header → a `Bay as="header" bracketed chamfer`** (the identity
  surface: brackets + the single milled corner). `status` → a round `StatusPill`
  (status→tone map); title/question/description in **Sans** by role.
- The 6-up `COUNT_LABELS` `dl` → **`MetricReadout`s**; the loading state is a
  token-ramp shimmer (`bg-text-faint/25`, `rounded-inset`), error → `"—"`.
- **The contradictions block is the honesty surface (§1).** It floats **above** the
  counts, marked by a **state-fail left edge tick** + an `AlertTriangle` glyph + a
  mono `state-fail` readout label, at full readout weight — never softened,
  green-washed, or buried below the counts. Carried by glyph + label + position, so
  it survives grayscale. (The contested-claim statements render in Sans `--text-soft`.)
- The two top-level loading/error returns → **`AwaitingState`** in a `Bay` frame.
- The "Projects" back link → the **`ActionText` register** (text → signal on hover)
  with a leading `←`. (Implemented as a styled `Link`, not the `ActionText`
  *component*, because that component is a `<button>` with a *trailing* `→`; a back
  link needs an `<a>` with a leading arrow. Same visual register, correct semantics.)

### 2. `funding-panel.tsx` — the money/metric showcase

- Wrapped in **`<Bay id="funding">`** — which **satisfies the command rail's
  Funding anchor wired back in D2** (the payoff of making `Bay` forward props in D3).
- `Budget` header → a mono `ReadoutLabel` (the `Wallet` icon demoted to `--text-mute`
  — signal-seldom); the Funded/Available/Spent `dl` → three `MetricReadout`s
  (`Spent` keeps its `--text-mute` value + the compute-spend `title`).
- The ad-hoc `STATUS_CLASS` colour map → a `FundingStatus → StateTone` map behind
  `StatusPill` (`settled→ok ✓`, `pending→run ●`, `failed→fail ■`, `refunded→faint ·`).
- Funding **history → a mono data list**: amount mono/tabular `--text`, source/kind
  mono `--text-mute` tokens, actor display-name **Sans** `--text-mute`, status a
  `StatusPill`, date mono `--text-faint`.
- The native top-up form → a nested `--panel-2` surface with console `Input`
  (amount + currency mono) / `Select` (kind) + a primary `Action`.
- **All funding logic + the `canFund` (internal-role) gate are unchanged.**

### 3. `branch-bar.tsx` — the line bar + the destructive close path (§5.7)

- Wrapped in a `Bay`; the `Line` label → a mono `ReadoutLabel` with a `GitBranch`
  glyph. Main line + each branch → **round selectable `LinePill`s**; selected = a
  **signal ring + signal text** (marked, not a flooded block, §9.2).
- `BRANCH_STATUS_META` → a `BranchStatus → StateTone` map rendered as a compact
  mono `glyph + label` token (`open→run ●`, `dead_end→fail ■`, `closed/merged→mute ▣`).
  **`dead_end` keeps its strike-through** (now `--state-fail`-coloured) — the honest
  "recorded, not deleted" mark, so meaning survives grayscale via glyph + label +
  strike, not colour.
- Fork → a round `ActionGhost`; the Close-branch trigger → a round ghost that hovers
  to `--state-fail`. **The `CloseBranchForm` is the §5.7 destructive test:** its old
  `border-ember` container + flooded `bg-ember` submit become a **state-fail left
  edge tick** on a `--panel-2` surface + an **`ActionDestructive`** (ring + text,
  never a flooded red fill). The "recorded, not deleted" copy stays.
- `ForkBranchForm` / `CloseBranchForm` inputs → console `Input`/`Select`; the "record
  a checkpoint first" notice → a dashed-hairline note; the sign-in gate → `--state-warn`.
- **All three components' hooks, mutations, and the fork/close write flows are
  byte-for-byte unchanged.**

---

## Decisions & deviations (with rationale)

1. **Header uses both `chamfer` and `bracketed`.** The chamfer's `clip-path` clips
   the top-right *registration bracket* corner. The header bay contains no
   overflowing menus (unlike the D2 shell header), so there is no functional risk —
   only the decorative bracket corner is trimmed, which reads as part of the milled
   corner. Kept both per the plan; noted so the slight corner trim is understood as
   intentional.
2. **Contradictions placed directly above the counts, not above the title.** "Float
   failure to the top of its bay" (§1) is honoured relative to the *data* — failure
   sits above the success metrics, prominently marked — while the title still leads
   the header (a header must identify itself first). A deliberate reading-order call.
3. **`MetricReadout` added as a shared primitive** (not in the D1 list) because D4 is
   where metric readouts first recur; defining it once keeps the header and budget
   honest and identical. Low-risk, forward-useful (live counts later).
4. **Currency input width via `!w-16`.** The console `Input` base is `w-full`; the
   narrow currency field needs a hard override, so `!w-16` (Tailwind important) beats
   the base without adding `tailwind-merge`. The only such override in the phase.

## Explicitly NOT touched (scope discipline)

No query key, mutation, route, `useActingIdentity` gate, or read-schema field
changed. The three **instrument columns** (`thread-list-panel`,
`claim-list-panel`, `checkpoint-timeline-panel`), the shared `panel-state` helpers,
and `validation-controls` remain pre-Kamino — they render transitional below the
converted frame and convert in **D5**. Verified: those five files are the *only*
remaining carriers of legacy tokens in the workspace.

## Signal-seldom check

After D4, `--signal` in the workspace frame appears only on: the selected line pill
ring, the primary `Action`s (fund / fork submit), and the back-link hover. Every
former teal accent — the status kicker, the budget Wallet, the "Line" label, the
branch status badges — is now `--text-mute` or a **state tone**. The contradictions
surface and the destructive close use `--state-fail` (status, not brand), keeping
the §9.2 separation intact.

---

## Verification (reproduced)

- **`npm run typecheck`** → clean. **`npm run lint`** → clean.
  **`npm run build`** → success; all routes generated (`/projects/[projectId]` is a
  dynamic route, server-rendered on demand, so it is not prerendered to static HTML).
- **Conversion completeness** — grep confirms the three D4 files carry **none** of
  `bg-white | text-ink | border-line | ember | shadow-panel | shadow-sm | bg-paper |
  rounded-md | rounded-lg`, and that the remaining legacy-token files are exactly the
  five D5 targets. Clean phase boundary.

> Not done here (needs a running backend / manual pass): a live render of the
> workspace with real project data — the honest contradictions surface, the budget
> readouts, a `dead_end` branch's strike, and the destructive close form are best
> confirmed visually + under devtools grayscale. The funding `#funding` anchor target
> now exists; the rail link resolves.

## What D5 can rely on

The workspace **frame** is Kamino; the three instrument columns are the last
conversion. D5 has every primitive it needs — `Bay`/`BayHeader`, `StatusPill` +
`STATE_META` (for claim signal, evidence relation, validation outcome, checkpoint
contribution), `AwaitingState` (to replace the `panel-state` helpers),
`Input`/`Select`/`Textarea`, `Action*`, `MetricReadout` — plus the established
status→tone mapping pattern to extend to the validation vocabulary.
