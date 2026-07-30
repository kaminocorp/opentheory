# `0.14.0` — Project deepdive tab shell (Phase A) completion notes

> **Completed:** 2026-07-30 · **Plan:** `docs/executing/project-deepdive-tabs-0.14.md` Phase A (A1–A8)  
> **Scope:** Frontend layout / information architecture only.  
> **No backend, schema, API, or migration.** No panel internals rewritten.

---

## What we were trying to achieve

The project deepdive had become a flat vertical stack of nine peer bays, in this order:

```
header (title + question + description + SIX metric tiles)
Research crew  |  Collaborators
Budget
Line (BranchBar)
Instruments · Toolbench
Agent pass · Research crew
Threads | Claims | Checkpoints        ← the actual research work, ~1900px down
```

Every bay carried identical visual weight, so nothing told you what the page was *for*.
Configuration surfaces a member touches once (crew, collaborators, funding) sat **above** the
ledger the page exists to operate, and the whole toolbench sat between them and it. Reported
symptom: *"cluttered and overwhelming… the information is all there, but it's hard to scan and
see what's what, hard/annoying to test because of this."*

The fix is ordering and grouping, not new capability: **a persistent header + five tabs, Research
first.** Move panels, don't rewrite them.

## What landed

### New files

| File | Change |
|---|---|
| `frontend/src/lib/use-project-tab.ts` | `PROJECT_TAB_IDS` (frozen at 5) + `ProjectTabId` + `DEFAULT_PROJECT_TAB`. `useProjectTab()` reads `?tab=`, validates against the union (unknown → `research`), and `setTab`s via `router.replace(…, {scroll:false})` while **preserving other params** (so a future `?thread=` deep link survives). Normalizes the legacy `#funding` hash once on mount. |
| `frontend/src/components/workspace/project-tabs.tsx` | The tablist. WAI-ARIA tabs pattern: `role="tablist"`/`role="tab"`, `aria-selected`, `aria-controls`, roving tabindex, ←/→ wrap + Home/End with automatic activation. Exports `projectTabDomId` / `projectPanelDomId` so tabs and panels reference each other. Optional count badges. |
| `frontend/src/components/workspace/project-header.tsx` | Persistent chrome: back link, `StatusPill` + Edit toggle, title, question, **one-line truncated** description, the contested-claims strip, and a **compact `threads · claims · checkpoints` readout**. Owns no state. |

### Edited files

| File | Change |
|---|---|
| `frontend/src/components/workspace/project-workspace.tsx` | Now a thin orchestrator. Keeps the four shared queries and `selectedThreadId` / `selectedBranchId` / `editing` exactly as before; adds `useProjectTab()`, a shared `listThreads` query, and renders `<ProjectHeader> <ProjectTabs> <TabPanel × 5>`. Adds two local components: `TabPanel` and `InstrumentContext`. |
| `frontend/src/app/projects/[projectId]/page.tsx` | Wrapped `<ProjectWorkspace>` in `<Suspense>` with an `AwaitingState` fallback — mandatory once `useSearchParams` is in the tree. |

### Tab → contents (as built)

| Tab | Contents | Mount |
|---|---|---|
| **research** (default) | `BranchBar` + the 3-col `ThreadList · ClaimList · CheckpointTimeline` grid (`enter-stagger` retained) | keep-alive |
| **instruments** | Sticky context readout + `ToolbenchPanel` + `AgentPassPanel` | keep-alive |
| **crew** | `ResearchCrewPanel` + `Collaborators` (existing two-column) | lazy |
| **funding** | `FundingPanel` | lazy |
| **overview** | `ProjectEditForm` (when editing) + Background/Context + full description + the six-metric `Ledger totals` grid | lazy |

**No panel's props changed.** Every panel already self-fetched from `projectId` + selection props,
which is what made the regroup a composition change rather than a refactor.

## Decisions and why

**1. `?tab=` in the URL, not component state.** The tab strip, deep links, and the CommandRail
(Phase B) all have to agree on one active tab. Component state would have to be lifted and
re-plumbed the moment the rail lands, re-touching every setter. URL from day one.

**2. Research + Instruments are keep-alive; the rest are lazy.** This is load-bearing, not a
perf tweak: `AgentPassPanel` holds `activeRunId` in local state and polls the trace inside
`AgentRunTrace`, so **unmounting Instruments would silently kill an in-flight agent pass**.
Both hot tabs render always and toggle with a class. Crew/Funding/Overview are cold config
surfaces with no in-flight state, so they mount on first activation — and then stay mounted.

**3. The panel element always renders; only its contents are gated.** A tab's `aria-controls`
must resolve to a real element. Purely conditional panels would leave dangling references on
every unvisited tab, so `TabPanel` renders the wrapper unconditionally and gates `children` on
`mounted`. Cold tabs still issue zero queries until first visited (JSX elements are constructed
eagerly but not *rendered* until mounted).

**4. Visibility is toggled on an element that carries no other display class.** `lib/cn.ts` is a
plain string joiner with **no `tailwind-merge`** — so `cn("grid gap-4", hidden && "hidden")`
would emit both `display:grid` and `display:none` and leave the winner to CSS **source order**.
That is exactly the layering footgun fixed in `0.6.6` and flagged again in `0.6.8`. `TabPanel`
therefore puts `hidden` (attribute *and* class) on the outer element alone and keeps layout
classes on an inner wrapper — unambiguous regardless of stylesheet order.

**5. The active marker is a `h-0.5` signal tick, not a filled pill.** `command-rail.tsx` marks
its active zone with a 2px `--signal` edge tick on a *vertical* edge (`w-0.5`); transposed here
to the strip's *horizontal* bottom edge. Active state reads from tick + text weight, so it
survives grayscale (design-system §0/§9.2).

**6. Six metrics → three in the header, six on Overview.** The metric grid was the single
biggest consumer of above-the-fold height. Identity and honesty stay up top; the full grid is
reference material.

**7. The contested strip became a button.** It stays in the persistent header (an honesty
surface must never be reachable "only inside Research"), and clicking it now routes to Research
where the claims live. Its hover cue lifts the *statement text* rather than the surface, because
`--panel-2` is already the lightest structural step — there is no `--panel-3` to hover into.

**8. Instruments restates the run context.** The thread/branch selection is made on Research, a
tab away, so the toolbench now carries a sticky `Thread … · Line … [· sealed]` readout. Without
it a member could run an instrument without seeing what it attaches to. Read-only by design —
`BranchBar` stays the single branch *selector*. The thread title comes from a `listThreads` query
under the **same** `queryKeys.threads(projectId)` key `ThreadListPanel` uses, so TanStack serves
both from one cache entry and **one request**.

**9. `AgentPassPanel.onSelectBranch` now also switches to Research.** The 0.12.4 "Review on its
line" action selects the agent branch; with tabs, selecting a branch while sitting on Instruments
would change something the user can't see. It now lands them on the timeline showing it.

## Deliberate deviations from the plan

| Plan said | Built | Why |
|---|---|---|
| Badges deferred to Phase C ("accept the prop, render nothing yet") | Contested count (fail tone) on Research + member count on Crew | Both derive from queries the orchestrator **already holds** — no new fetch (the plan's §10.3 constraint). They directly serve the reported "hard to scan" complaint, so holding them back had no upside. |
| Crew/Funding/Overview "conditional render" | Panel element always renders; children gated | Keeps `aria-controls` valid (see decision 3). Same laziness, correct ARIA. |
| Overview also carries "contested-claims detail" | Skipped | The header already lists every contested statement. Repeating it on Overview is the clutter this release exists to remove. |
| Background as a collapsible | Always open on Overview | The collapsible existed to defend above-the-fold space on the old stacked page. On a dedicated reference tab it is pure chrome; `backgroundOpen` state deleted. |

## Verification

```bash
cd frontend && npm run typecheck   # clean
cd frontend && npm run lint        # clean
cd frontend && npm run build       # clean — 9/9 static pages
```

`npm run build` is the meaningful one: a missing `<Suspense>` around `useSearchParams` fails the
static-generation deopt check, and `next dev` would not have caught it. The route also serves
`200` for `/projects/<id>?tab=funding` with no runtime errors in the dev log.

**Not verified: the rendered result.** The Chrome extension was not connected during this pass
and no headless browser is installed, so nothing below the type/build layer was seen. The live
Fly backend's DB-backed endpoints (`/api/v1/projects`) were also timing out at the time, so even
a driven browser would have had no data. **The §8 acceptance walk — especially #3 (selection
survives a Research → Instruments → Research round trip) and #4 (agent trace still live after
leaving Instruments mid-run) — is outstanding and should be run against a real project before
this is treated as done.**

## Deliberate non-goals (unchanged from the plan)

- **Phase B** — CommandRail still links `#funding` (the hook normalizes it) and the Agents zone
  is still inert. No rail↔tab sync yet.
- **Phase C** — no claim-focus click-through from the contested strip (it routes to the tab, not
  to the claim); no running-pass `LiveDot` badge (would need the agent-runs query at orchestrator
  level, i.e. a new fetch).
- **Phase D** — no `?thread=` / `?branch=` deep links.
- No backend, schema, migration, or new App Router segments. No panel internals, toolbench
  honesty rules, or agent UX touched.
