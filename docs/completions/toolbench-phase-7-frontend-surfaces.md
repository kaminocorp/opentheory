# Toolbench Phase 7 — Frontend workspace surfaces (completion notes)

> **Status:** implemented · **Release slice:** `0.9.5` (the toolbench's frontend component library) of
> `docs/executing/toolbench-provenance-and-first-instruments.md` · **Scope:** frontend only — the
> typed API plumbing, the drive/show surfaces for all four instruments, and the honesty rules. No
> backend, schema, or migration.
>
> **What it delivers:** a person standing in a project workspace can pick a deterministic maths
> instrument, drive it (with a visible **assumptions** input), run it as a project member, and see the
> result land in the ledger — the measurement, its assumptions, and the
> `instrument@version · engine@version` blame line, all rendered honestly. The flagship *measuring
> across a corner* thread is one click (`A=[0,0], B=[3,0], C=[3,4]` → `dist(A,C)=5`,
> `angle(A,B,C)=90°`).

---

## 1. What changed, where, and why

### 1.1 Plumbing — the typed client + types (`lib/api.ts`, `types/`, `lib/query-keys.ts`)

- **`types/toolbench.ts` (new)** — `InstrumentDescriptor`, `ResultContractOutcome`, `ToolRunRequest`,
  `ToolRunResult`, mirroring the Phase-6 read schemas. The core provenance types (`ResultStatus`, the
  `ToolInvocation` blame tuple) live in **`types/research.ts`** beside `Checkpoint` (which carries
  them) and are re-exported from `toolbench.ts`, so a consumer imports the whole surface from one
  place and there is no import cycle.
- **`Checkpoint.tool_invocations` (`types/research.ts`)** — added, typed as `ToolInvocation[]` with
  every field optional. That optionality is deliberate: the backend surfaces `tool_invocations` as
  **lenient raw JSON** (a pre-/future-shape historical entry must never break a read), so the UI
  renders it defensively rather than assuming the strict write shape.
- **`lib/api.ts`** — `getInstrumentCatalog()` (`GET /instruments`, public) and
  `runInstrument(projectId, name, body)` (`POST /projects/{id}/instruments/{name}/run`, membership
  gated). `lib/query-keys.ts` — `instrumentCatalog` (static, cached indefinitely like the agent-model
  catalog).

### 1.2 The render seam — `Formula` (`toolbench/formula.tsx`)

Every expression a drive or show surface displays routes through one component, `<Formula expr />`.
v1 renders a **monospace value chip** — on-brand with the console's data/token family
(`design_blueprint §3.1`) and, for a provenance ledger, *incapable of mis-rendering* (a wrong formula
recorded against a result is worse than a plainly-typeset one). This is the single seam that owns
render strategy: a v2 that prefers a server-supplied `latex` field (SymPy's authoritative
`sympy.latex()`, an additive backend change) and typesets with KaTeX is a change to this file alone —
no call site moves. **Decision recorded in the build discussion:** mono-now → backend-`latex`-later
avoids building a throwaway frontend SymPy→LaTeX converter.

### 1.3 Drive surfaces — `toolbench/drive-forms.tsx`

One bespoke form per instrument, each pre-filled with its demo so the flagship cases are one click:

| Instrument | Drive surface | Demo prefill |
|---|---|---|
| `calc.eval` | one expression/relation field | `3**2 + 4**2 == 5**2` |
| `expr.compare` | left + right fields | `(a + b)**2 - 2*a*b` ≟ `a**2 + b**2` |
| `geometry.coordinate_measure` | points editor + distance/angle rows | the corner: `A,B,C` → `dist(A,C)`, `angle(A,B,C)` |
| `oeis.search` | comma-separated terms | `1, 1, 2, 3, 5, 8` |

A form owns its display state and reports the built `inputs` object (or `null` when incomplete)
upward; the runner enables **Run** only when it is non-null. Coordinates coerce whole numbers to
ints and leave everything else a string (`1/2`, `sqrt(2)`) — **never a float**, matching the
instrument's exactness contract. A **JSON fallback form** keeps the panel working for any future
instrument the registry gains before it has a hand-built surface.

### 1.4 The assumptions input — `toolbench/assumptions-editor.tsx`

Assumptions are recorded *with* the result, so they are an **explicit, editable surface, never a
hidden flag** (plan Phase 7.4). The editor expresses both shapes the backend accepts:

- a per-symbol **SymPy predicate** — `x is positive` → `{ x: { positive: true } }` (the dropdown
  offers only ids `_sympy_support.SYMPY_ASSUMPTION_KEYS` accepts, so the menu can't offer what a run
  rejects);
- a **contextual scalar** — `angle = 90` → `{ angle: 90 }`, which rides on the record but is not a
  symbol flag.

The geometry instrument seeds `angle = 90` as its demo assumption — the flagship deliverable's
"result card shows its angle=90° assumption".

### 1.5 Show surfaces — `toolbench/result-view.tsx`

Dispatches on instrument name to the right card, then surfaces the assumptions and the blame line:

- **value / measurement cards** — `calc.eval` value, `geometry` distances + angles (degrees with the
  exact radians beside);
- **counterexample card** — the `refuted` outcome rendered as the **strong, definitive finding it
  is** (a `--state-fail` edge tick, captioned "Counterexample · definitive"), used by `calc.eval`
  (a false relation) and `expr.compare` (a non-zero difference witness);
- **citation card** — `oeis.search`: the A-number pin, cited name/formula, the source link,
  `retrieved_at`, and the `raw_response_hash` fingerprint (cite, don't redistribute);
- **provenance footer** — `instrument@version · engine@version`, plus the artifact / evidence /
  checkpoint ids and the content hash. The reconstruct-exactly-how-it-was-made contract, made
  visible.

### 1.6 The panel + runner — `toolbench/toolbench-panel.tsx`

- **`ToolbenchPanel`** — a collapsible `Bay` (discoverable without dominating the workspace). Fetches
  the public catalog, renders a segmented **instrument picker** over the code registry, the selected
  instrument's description + `name@version · engine@version`, and its **self-describing outcome
  legend** (the three `result_contract` entries as tone-coded pills with their meanings as tooltips —
  so "undecided ≠ pass" is stated up front, paying off the Phase-6 decision to make the contract
  self-describing).
- **`InstrumentRunner`** — one instrument's two columns: **drive** (form + assumptions + an optional
  claim target) and **show** (the `ResultView`, or an awaiting state). Keyed by instrument name, so
  switching instruments resets all state to that instrument's demo. On success it invalidates
  `checkpoints` + `overview` (+ `evidence` when a claim was targeted), so the produced checkpoint
  appears in the timeline below.

### 1.7 Mount (`project-workspace.tsx`)

`<ToolbenchPanel>` sits between the branch bar and the three-column grid, `canRun={canManageProject}`
(membership) and `selectedThreadId` for scope. Reads are public; the run is gated.

## 2. Honesty rules in the UI (plan Phase 7.4)

The three outcomes map to console state tones through one table (`toolbench/outcome.ts`), never
softened:

- `result` → ✓ **ok** — a produced result.
- `refuted` → ■ **fail** — a counterexample; the claim is *definitively false*. Rendered as an
  asymmetrically **strong** outcome (the counterexample card), not an error.
- `undecided` → ▲ **warn** — the tool ran but could not decide; rendered as "escalate to a proof,
  **never a pass**" (the seam to the deferred Z3/Lean verifier).

## 3. Judgment calls

- **Mono over KaTeX for v1 (behind a seam).** See §1.2 — chosen after weighing the SymPy→LaTeX shim's
  fragility (a mis-rendered formula in a provenance ledger is a real defect) against a mono chip that
  can't be wrong and is already the console's house style for data. The `Formula` seam makes the v2
  upgrade a one-file change.
- **Membership gate, matching the backend.** `canRun = canManageProject` (a `project_members` row),
  mirroring the Phase-6 `ensure_is_member` gate. Running an instrument is *research* (a
  `Contribution`), not governance — the gate is membership, and the backend still authorizes every
  run regardless of the client gate.
- **Claim targeting is optional and secondary.** A run always records on the ledger; a claim target
  (offered only when a thread is selected and has claims) *also* mints Evidence linked to that claim.
  `relation_kind` is left for the backend to derive from the outcome (`refuted → weaken`, etc.),
  matching the Phase-3 service.
- **Reused the existing checkpoint list carries the tuple.** No new "artifact/evidence detail" fetch —
  the blame tuple on `ToolRunResult.checkpoint.tool_invocations` already carries everything the show
  surface renders; artifact/evidence are shown by id. (Mirrors the Phase-6 §3.1 decision.)

## 4. Verification

| Check | Result |
|---|---|
| `npm run typecheck` | **clean** |
| `npm run lint` | **clean** |
| `npm run build` | **green** — production type-check + 9/9 static pages; `/projects/[projectId]` 61.8 kB, no new shared deps |

### Not run here (honest gap)

Per the no-local-DB / verify-against-live policy, the **signed-in round-trip** is a post-deploy check:
open a project as a member, run `calc.eval` (`3²+4²==5²` → RESULT; `5 == 7` → the REFUTED
counterexample card), run the geometry corner (`dist(A,C)=5`, `angle=90°` with its `angle = 90`
assumption chip and the `geometry.coordinate_measure@0.1.0 · sympy@x.y.z` blame line), confirm the
checkpoint appears in the timeline, and confirm a non-member sees the catalog but a disabled Run with
the membership hint. This exercises the same DB-backed write path whose backend round-trips are still
pending a throwaway Postgres / the live deploy (Phases 3–6).

## 5. Scope boundary

No backend, schema, or migration. No KaTeX / typeset math (the `Formula` seam is the v2 hook, §1.2).
No standalone artifact/evidence detail pages. No plot/table cards (Vega-Lite is deferred with
`plot.*`). No agent execution — the surface is human-invokable; an agent later drives the *same* API.

## 6. Next step

Phase 7 closes the implementation line of
`docs/executing/toolbench-provenance-and-first-instruments.md` (Phases 1–7 done). Remaining is the
**release step**, matching Phases 1–6: batch the `0.9.1`–`0.9.5` entries into `docs/changelog.md`,
run the DB-backed round-trips (throwaway Postgres or CI), and `fly deploy` + Vercel redeploy — once
greenlit. A natural v2 follow-up: the additive backend `latex` field + KaTeX behind `Formula`, and
`plot.*` / table cards.
