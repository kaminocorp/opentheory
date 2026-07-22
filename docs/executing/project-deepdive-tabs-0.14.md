# Project deepdive — sectioned tab workspace (implementation)

> **Status — executing (2026-07-22).** Frontend layout / information-architecture only.
> **No backend, schema, API, or migration.** Implements the proposal
> `docs/plans/project-deepdive-tab-redesign.md`; read it first for the *why*. This doc is
> the *how* — decisions locked, phases, tasks, and the file map to follow methodically.
>
> **Target release line:** `0.14.x` (frontend-only slices). **Confirm the number** against the
> in-flight `0.13.x` Z3 instrument line (`docs/executing/z3-instrument-0.13.md`) so the two don't
> collide — bump this line if `0.13.x` is still open when this ships.

---

## 0. One-line goal

Turn `/projects/[projectId]` from a **flat vertical stack of nine peer bays** into a
**persistent header + five tabs**, with **Research as the default surface** and every other
concern reachable in one click — preserving thread/branch selection and a live agent poll
across tab switches. Move panels, don't rewrite them.

---

## 1. Decisions locked (resolving the proposal's §14 open questions)

The proposal left five decisions open and offered chrome options. They are now **fixed** so
implementation is unambiguous:

| # | Decision | Choice | Rationale |
|---|---|---|---|
| D1 | Chrome (proposal §4) | **Option 3 Hybrid, phased**: horizontal tab strip in P0 (Phase A); CommandRail sync in P1 (Phase B). No in-page sidecar. | Smallest structural change first; rail becomes the *only* second nav surface, never a third. |
| D2 | Agent pass placement (§3.3) | **Option A — Instruments tab**, below the toolbench. | Same "run something that lands on the ledger" family; keeps Research clean. |
| D3 | Header metrics (§14.3) | **Compact** `n threads · n claims · n checkpoints` mono line in the persistent header; **full six-metric grid moves to Overview**. | Identity + honesty stay above the fold; the full grid is reference, not focus. |
| D4 | Background essay (§14.4) | **Overview-only.** Not a collapsible on Research. | Research stays operational; context-heavy prose doesn't push the ledger down. |
| D5 | Unmount vs hide (§14.5) | **Keep Research + Instruments mounted** (CSS-hidden when inactive); **lazy-render Crew / Funding / Overview.** | The hot path shares thread/branch selection *and* the agent poll must survive a tab switch (see §5.2). Cold config tabs can mount on demand. |
| D6 | Tab URL state | **`?tab=` search param** from P0, behind a `useProjectTab` hook; default `research`; `router.replace` (no history spam); normalize legacy `#funding`. | Deep-linkable Funding/Crew and rail sync both need one source of truth; retrofitting later would re-touch every setter. |
| D7 | Contested strip + metric line placement | **Outside the tablist**, in the persistent header. | a11y §10: honesty surface must not be reachable "only inside Research." |

**Tab set (5, frozen for v1):** `research` · `instruments` · `crew` · `funding` · `overview`.
Do not add a sixth until a real surface forces it (e.g. an agent-runs history browser).

---

## 2. Target architecture

### 2.1 Component tree (after)

```
app/projects/[projectId]/page.tsx        (server component)
  <AppShell>
    <Suspense fallback={…}>              ← NEW: required for useSearchParams (see §5.1)
      <ProjectWorkspace projectId />     ← becomes a THIN orchestrator
        ├─ shared queries: project · members · overview · branches   (unchanged, stay here)
        ├─ shared state:   selectedThreadId · selectedBranchId · editing   (unchanged)
        ├─ tab state:      useProjectTab()  →  { tab, setTab }              (NEW)
        │
        ├─ <ProjectHeader …/>            ← NEW file: persistent chrome (§3.1)
        ├─ <ProjectTabs active setTab counts …/>   ← NEW file: the tablist (§4)
        └─ <ProjectTabBody active …>     ← NEW (may live inline in workspace)
             research     → BranchBar + 3-col grid            (keep-alive)
             instruments  → context readout + Toolbench + AgentPass  (keep-alive)
             crew         → ResearchCrew + Collaborators      (lazy)
             funding      → FundingPanel                      (lazy)
             overview     → Background + description + Edit entry + full metric grid + contested detail (lazy)
```

### 2.2 State ownership (unchanged owner, new consumers)

All shared state **stays in `project-workspace.tsx`** — it already owns it. Nothing is lifted
or moved to context. The orchestrator passes state + derived flags down as props exactly as it
does today; only the *grouping* of the children changes.

- `selectedThreadId`, `selectedBranchId`, `editing` → `useState` (unchanged).
- `canManageProject`, `selectedBranch`, `lineSealed`, `contradictions`, `counts` → derived
  from the four shared queries (unchanged).
- `tab` → from URL via `useProjectTab()` (NEW).

### 2.3 The "move, not rewrite" contract

Every existing panel already fetches its own data given `projectId` + selection props
(verified: `ThreadListPanel`, `ClaimListPanel`, `CheckpointTimelinePanel`, `ToolbenchPanel`,
`AgentPassPanel`, `FundingPanel`, `ResearchCrewPanel`, `Collaborators` all self-fetch). **No
panel's props or internals change** except where a phase explicitly says so (Instruments gets a
context readout; Overview gets the metric grid + edit entry). If you find yourself rewriting a
panel, stop — that's out of scope for this line.

---

## 3. Information architecture (concrete)

### 3.1 Persistent header (always visible, above the tablist)

New file `project-header.tsx`. Renders, top → bottom:

1. Back link → Projects (existing markup, `ArrowLeft`, ActionText register).
2. Row: `StatusPill` (tone from `projectStatusTone`) + **Edit** toggle (`canManage` only).
3. Title (`h1`) + question (`p`). Description: **one line, truncated** ("more" defers to Overview).
4. **Contested-claims strip** — verbatim from today's header (state-fail edge tick + glyph +
   list). Honesty stays above the fold (D7).
5. **Compact metric line**: `n threads · n claims · n checkpoints` in mono/tabular-nums
   (`ReadoutLabel` cadence). Loading + `—` error states preserved from the current `MetricReadout`
   fallbacks. The **full six-metric `dl` grid moves to Overview** (D3).

Header owns **no state**; `editing` toggle is passed in from the orchestrator (so the Edit form,
which lives in Overview, opens regardless of active tab — see §3.2 overview row).

### 3.2 Tab → contents

| Tab | Contents | Mount | Gating |
|---|---|---|---|
| **research** (default) | `BranchBar` (the single branch selector) + the 3-col grid (`ThreadList · ClaimList · CheckpointTimeline`), `enter-stagger` retained | keep-alive | public read; writes gated in-panel as today |
| **instruments** | Sticky **context readout** (`Thread: … · Branch: main / …`) + `ToolbenchPanel` + `AgentPassPanel` (D2) | keep-alive | catalog public; run CTAs `canRun`-gated as today; agent block dark-launch-aware (unchanged) |
| **crew** | `ResearchCrewPanel` + `Collaborators` (existing two-column) | lazy | read-only for visitors; manage gated |
| **funding** | `FundingPanel` | lazy | read; write gated |
| **overview** | Background Markdown (default open) + full description + **Edit-form entry** for stewards + **full six-metric grid** + contested-claims detail | lazy | read; Edit gated |

**BranchBar stays on Research** as the sole branch *selector*; Instruments shows the selected
branch **read-only** in its context readout. Toolbench runs still land on `selectedBranchId`
(select branch on Research → switch to Instruments → run lands on that line). `AgentPassPanel`
takes no branch prop (backend picks the agent branch) — unchanged.

**Edit form location:** the toggle lives in the header (any tab), but the `ProjectEditForm`
renders inside **Overview**. When `editing` is true and the active tab is not `overview`, the
Edit toggle should `setTab('overview')` before/at opening, so the form is always visible when
toggled on. (Simplest: the header Edit handler does `setEditing(true); setTab('overview')`.)

---

## 4. Tab chrome + visual spec (console-aligned)

New file `project-tabs.tsx` — **local to `workspace/` for v1** (graduate into
`components/console` later only if a second consumer appears). Align to
`docs/blueprints/design-system.md`, reusing patterns already in `command-rail.tsx`:

- **Labels:** mono uppercase, `ReadoutLabel` tracking; inactive `--text-mute`, active `--text`.
- **Active marker:** a **2px signal edge tick** (`absolute … w-0.5 bg-signal`, bottom edge of the
  strip) — mirror the rail's `bg-signal` tick. **No filled pill background.**
- **Strip:** hairline bottom rule (`border-bottom: 0.5px solid var(--hairline)`).
- **Badges (stretch, Phase C):** contested count on Research; member/invite count on Crew;
  a running-pass `LiveDot tone="signal" pulse` on Instruments.
- **Grayscale:** active tab must read from weight + edge tick alone (acceptance #6), never colour.
- **Mobile:** horizontal scroll (`overflow-x-auto`), optional `scroll-snap`; no hamburger — five
  labels fit.

### 4.1 Accessibility (WAI-ARIA tabs pattern)

- `role="tablist"` on the strip; `role="tab"` on each control with `aria-selected` and
  `aria-controls={panelId}`; each panel `role="tabpanel"` `aria-labelledby={tabId}` `tabIndex={0}`.
- **Roving tabindex**: active tab `tabIndex=0`, others `-1`; **←/→** move + activate; **Home/End**
  jump. Tabs are **buttons** (not links) so the ARIA tab pattern stays clean; the URL update is a
  side effect of the `setTab` handler (§5.1). The CommandRail (Phase B) uses `<Link>` for the same
  `?tab=` — both converge on the search param, one source of truth.
- Focus moves into the panel heading on activation (document the choice in the component).

---

## 5. Cross-cutting concerns (get these right once)

### 5.1 URL tab state + the Suspense boundary

New hook `use-project-tab.ts` (in `lib/` or `workspace/`):

```ts
export type ProjectTabId = "research" | "instruments" | "crew" | "funding" | "overview";
// reads ?tab= via useSearchParams; validates against the union; defaults "research".
// setTab(id): router.replace(`${pathname}?tab=${id}`, { scroll: false })  — replace, not push.
```

- **HARD REQUIREMENT:** `useSearchParams()` in Next 15 must render under `<Suspense>` or
  `next build` fails. Wrap `<ProjectWorkspace>` in `<Suspense>` in `page.tsx` (server component —
  clean streaming boundary). **Verify with `npm run build`, not just `dev`.**
- **Legacy `#funding`:** hashes never reach `useSearchParams`. On mount, a `useEffect` reads
  `window.location.hash`; if `#funding`, `setTab('funding')` and clear the hash. One release of
  grace, then the CommandRail stops emitting it (Phase B).
- Build the target URL from `usePathname()` (`${pathname}?tab=…`) so the `projectId` segment is
  preserved; pass `{ scroll: false }` to avoid scroll jumps on tab change.

### 5.2 Agent-poll continuity (acceptance #4 — the load-bearing constraint)

`AgentPassPanel` holds `activeRunId` locally and polls inside `<AgentRunTrace>`; **unmounting
stops the poll and drops run-selection.** Therefore:

- **Research + Instruments render keep-alive**: always mounted, toggled with a `hidden` class
  (e.g. `className={cn(active !== 'instruments' && 'hidden')}`), **not** conditionally rendered.
  This preserves `activeRunId` and keeps `refetchInterval` alive when the user visits Funding/Crew.
- **Crew / Funding / Overview** are cold config surfaces with no in-flight state → **conditional
  render** (mount on first activation) for a lighter default paint.
- Do **not** attempt to lift agent-run polling into workspace-level state for v1 (bigger refactor,
  no added value once keep-alive is in place). Note it as a possible Phase D cleanup only.

### 5.3 Public read + write gating

No new gating logic. Every tab renders for signed-out visitors; each panel already shows its own
honest empty / sign-in / member-gated state (`canManageProject`, `canRun`, dark-launch detection).
Confirm no tab becomes a *missing nav item* for visitors (proposal §2.7) — all five labels always
render; only in-panel CTAs gate.

---

## 6. Phases

Each phase is independently shippable. **Phase A is the demoable declutter and can ship alone.**

### Phase A — Tab shell (P0) · target `0.14.0` · risk: low (pure composition)

- [ ] **A1** `use-project-tab.ts`: `ProjectTabId` union + `useProjectTab()` (read `?tab=`, validate,
      default `research`, `setTab` via `router.replace` + `{scroll:false}`). Legacy `#funding`
      normalizer (§5.1).
- [ ] **A2** `project-tabs.tsx`: console-aligned tablist + a11y (roving tabindex, ←/→, Home/End),
      2px signal edge tick, hairline strip (§4). Accepts `active`, `setTab`, and `counts` (badges
      deferred to Phase C — accept the prop, render nothing yet).
- [ ] **A3** `project-header.tsx`: extract back link + status + Edit toggle + title + question +
      truncated description + contested strip + compact metric line (§3.1). Props only, no state.
- [ ] **A4** Refactor `project-workspace.tsx` → thin orchestrator: keep the four shared queries +
      selection state; add `useProjectTab()`; render `<ProjectHeader> <ProjectTabs> <TabBody>`.
- [ ] **A5** Tab body + mount strategy (§5.2): Research + Instruments keep-alive (`hidden` toggle);
      Crew/Funding/Overview conditional. Wire the `<Suspense>` boundary in `page.tsx` (§5.1).
- [ ] **A6** Distribute panels per §3.2. Instruments: add the sticky **context readout**
      (`Thread: … · Branch: …`, read from shared state). Overview: full six-metric grid + Background
      + description + `ProjectEditForm` entry; header Edit handler routes to Overview (§3.2).
- [ ] **A7** States audit: no-thread → Research shows per-column awaiting (not a blank tab);
      sealed-branch behaviour intact on timeline + toolbench; public visitor sees all tabs.
- [ ] **A8** Verify: `npm run typecheck && npm run lint && npm run build` (build catches the
      Suspense deopt). Manual walk of the §8 acceptance list.

### Phase B — CommandRail sync + retire the fakes (P1) · target `0.14.1` · risk: low–med

- [ ] **B1** Share the `ProjectTabId` union between rail and tabs (single import).
- [ ] **B2** `command-rail.tsx`: when `onProject`, render real zone links → `${pathname}?tab=<id>`
      for Research / Instruments / Crew / Funding; derive each zone's `active` from the current
      `?tab=` (read via `useSearchParams`). Rail + in-page strip stay in sync via the URL.
- [ ] **B3** Retire the `#funding` hash target (now `?tab=funding`) and the **inert Agents hatch**:
      point Agents → `?tab=instruments` (or relabel "Operators"). No zone stays permanently inert.
- [ ] **B4** Verify rail active-state, keyboard, and `aria-current` across all five tabs.

### Phase C — Polish (P2) · target `0.14.2` · risk: med (polish only)

- [ ] **C1** Finalize compact header metric line; ensure full grid on Overview reads as reference.
- [ ] **C2** Contested-claim click-through: clicking a contested item in the header `setTab('research')`
      + scrolls/highlights the claim in `ClaimListPanel` (needs a claim-focus signal — a
      `focusClaimId` prop or an imperative scroll; keep it minimal).
- [ ] **C3** Tab badges (§4): contested count on Research; member/invite count on Crew; running-pass
      `LiveDot` on Instruments (derive "running" from the newest `AgentRun.status`).
- [ ] **C4** Sticky Instruments context readout refinement (sealed-line note, no-thread copy).

### Phase D — Deep-link selection + nav finalization (P3, optional) · risk: med

- [ ] **D1** `?thread=` / `?branch=` query params for shareable Research deep links (extend
      `useProjectTab` into a small `useProjectView` or sibling hook; keep `replace`).
- [ ] **D2** Agent in-flight indicator that persists across tabs (rail/strip live-dot while a poll
      is active) — the visible payoff of the §5.2 keep-alive decision.
- [ ] **D3** Sidecar decision: **recommend rail-only** (skip the in-page sidecar; Phase B already
      gives a project-context nav). Record the decision; only build a sidecar if nav genuinely
      needs > 5 zones.

---

## 7. File map

| Action | Path | Note |
|---|---|---|
| **new** | `frontend/src/components/workspace/project-header.tsx` | persistent chrome (§3.1) |
| **new** | `frontend/src/components/workspace/project-tabs.tsx` | tablist + a11y (§4); local for v1 |
| **new** | `frontend/src/lib/use-project-tab.ts` | `?tab=` state + `ProjectTabId` union (§5.1) |
| **edit** | `frontend/src/components/workspace/project-workspace.tsx` | → thin orchestrator; keep queries + state, regroup children |
| **edit** | `frontend/src/app/projects/[projectId]/page.tsx` | wrap `<ProjectWorkspace>` in `<Suspense>` (§5.1) |
| **edit (Phase B)** | `frontend/src/components/shell/command-rail.tsx` | live project zones → `?tab=`; retire `#funding` + inert Agents |
| **move only** | all existing panels under `components/workspace/**` | regrouped into tab bodies; **props unchanged** except Instruments context readout + Overview metric grid |

**No** new App Router segments, **no** backend/schema/API/migration. Verify with
`npm run typecheck && npm run lint && npm run build`.

---

## 8. Acceptance bar (carried from proposal §13, made checkable)

A signed-in member opening a mid-size project:

1. [ ] Sees **title, question, contested (if any), and the Research workspace** without scrolling
       past crew / funding / toolbench.
2. [ ] Reaches **Funding, Crew, or full Background in one click** (tab in P0; tab *or* rail in P1).
3. [ ] Selects a thread on Research → switches to Instruments → runs a tool → switches back:
       **same thread/branch**, new checkpoint on the timeline.
4. [ ] Commissions an agent pass (flag on) → leaves Instruments mid-run → returns: **trace still
       live** (validates §5.2 keep-alive).
5. [ ] Public visitor: **same nav**, write CTAs gated as today (no missing tabs).
6. [ ] Grayscale: active tab obvious from **edge tick + weight**, not colour.
7. [ ] `?tab=funding` deep-links straight to Funding; legacy `#funding` normalizes to it.
8. [ ] `npm run build` passes (Suspense boundary correct — no `useSearchParams` deopt).

---

## 9. Non-goals (v1)

- New backend routes, project sub-page segments (`/projects/x/funding`), schema, or migration.
- Reworking claim / timeline / toolbench internals or toolbench honesty rules.
- Autonomous agent UX, multi-thread orchestrator, or new instruments.
- Global app IA redesign beyond project-context zones; an in-page sidecar (see D3).
- Seed data / empty-project wizard.

---

## 10. Open items to confirm before merge

1. **Version number** — `0.14.x` assumes `0.13.x` is the Z3 line. Confirm and adjust if needed.
2. **Claim-focus mechanism (C2)** — prop drill (`focusClaimId`) vs a light imperative scroll;
   pick the smaller one when Phase C starts.
3. **Badge data source (C3)** — reuse existing queries (overview contradictions, members list,
   newest agent run) — confirm no new fetch is introduced.
