# Project deepdive redesign — sectioned workspace

> **Status — proposal (2026-07-22).** Frontend layout / information architecture only.
> No backend, schema, or API changes required. Aligns with `docs/blueprints/design-system.md`
> (console as command bridge; honest density; hairlines, not chrome noise).

**Problem:** The project page (`/projects/[projectId]` → `ProjectWorkspace`) stacks every
concern into one long vertical scroll. Stewardship, funding, toolbench, agent pass, and the
research ledger share equal visual weight, so the *research work* is hard to follow.

**Goal:** One clear **primary surface** for research, with major secondary concerns reachable
in one click via tabs — without inventing a second app shell or fragmenting state (thread /
branch selection) across unrelated URLs unless deep-linking earns it.

---

## 1. Diagnosis — what the page is today

`frontend/src/components/workspace/project-workspace.tsx` composes, top → bottom:

| # | Block | Role |
| --- | --- | --- |
| 1 | Back link + **header bay** | Title, question, description, status, contested claims, six count metrics |
| 2 | **Edit form** (toggle) | Owner/admin metadata + background editor |
| 3 | **Research crew** + **Collaborators** | Config + membership (two-column) |
| 4 | **Background / Context** | Collapsible Markdown |
| 5 | **Funding** | Allocations (also hinted by command-rail `#funding`) |
| 6 | **Branch bar** | Line selector for ledger scope |
| 7 | **Toolbench** | Drive + show instruments |
| 8 | **Agent pass** | Commission pass + trace |
| 9 | **Three-column workspace** | Threads · Claims (+ evidence/validation) · Checkpoint timeline |

Everything is always present (modulo empty background / dark-launched agent). Added over
`0.4` → `0.12` as independent Bays; never re-chunked. Result: a **flat stack of peer panels**
rather than a workspace with a focus mode.

The **command rail** already anticipates zones (`Workspace`, `Funding`, inert `Agents`) but
does not drive in-page structure — Funding only jumps to `#funding`, Agents is hatched
“coming soon” despite the thin loop shipping in `0.12.x`.

---

## 2. Design principles for the redesign

1. **Research is the default tab.** First paint should be: *what is this project asking, what’s contested, which thread am I on, what’s on the ledger.*
2. **Separate “work” from “configure.”** Model roster, invites, funding, and project metadata are stewardship — not the research loop.
3. **Instruments and agents are *operators on the ledger*,** not equal peers of the timeline. Prefer co-location with the research surface (drawer / sub-panel / side mode) over their own full-page exile — unless a pass is running and needs a dedicated trace focus.
4. **Shared selection state stays global to the project page:** `selectedThreadId`, `selectedBranchId` must survive tab switches so toolbench / agent / timeline stay coherent.
5. **One chrome language.** Tabs are registration ticks + mono labels, not pill marketing chrome (design system: square structural, hairline, signal edge on active).
6. **Deep-linkable where it pays off.** Tab id in the URL (search param or hash) so Funding / Collaborators links and the command rail work. Thread/branch can stay client state for v1 or join the URL later.
7. **Public read still works.** Visitors land on Research; write tabs show honest empty / sign-in states, not missing nav items.

---

## 3. Proposed information architecture

### 3.1 Persistent chrome (always visible)

Keep a **compact project header** above the tab body — do not bury identity in a tab:

- Back → Projects  
- Status pill · title · question (description optional, one line or “more”)  
- Contested claims strip (if any) — honesty surface stays above the fold  
- **Sparse** metric strip (or a single “ledger pulse” that expands on Research)  

Collapse or demote:

- Full six-metric grid → Research tab or a compact `n threads · n claims · n checkpoints` mono line in the header  
- Long description / full background → **Overview** or **Background** tab  

### 3.2 Tabs (recommended set)

| Tab id | Label | Contents | Audience |
| --- | --- | --- | --- |
| `research` | **Research** | Branch bar · three-column workspace (threads / claims / timeline) · optional inline toolbench + agent affordances | Everyone (default) |
| `instruments` | **Instruments** | Full toolbench (drive/show) · optionally agent pass panel | Members write; public read catalog |
| `crew` | **Crew & access** | Research crew models · Collaborators / invites | Config; manage gated |
| `funding` | **Funding** | `FundingPanel` | Everyone read; write gated |
| `overview` | **Overview** | Background Markdown · full description · edit form entry · optional expanded metrics / contradiction detail | Everyone |

**Five tabs max for v1.** Prefer not to grow a sixth until a real surface forces it (e.g. a dedicated Agent runs history browser).

### 3.3 Where agent pass lives

Two acceptable placements (pick one in implementation):

| Option | Placement | Rationale |
| --- | --- | --- |
| **A (recommended)** | **Instruments** tab, below toolbench | Same “run something that lands on the ledger” family; Research stays clean |
| **B** | Research tab, collapsible “Operator” bay | Fewer clicks when alternating claim work and passes; denser default |

Do **not** leave the inert rail “Agents” zone forever — either wire it to `?tab=instruments` (or a future agent history view) or relabel honesty (e.g. “Operators”).

---

## 4. Chrome options — sidecar vs top tabs

### Option 1 — Horizontal tab strip (under header)

```
[ Header bay ………………………………………………………… ]
[ Research | Instruments | Crew & access | Funding | Overview ]
[ ……………… active tab body ………………………………… ]
```

**Pros:** Familiar; works on mobile (scrollable tab list); minimal new layout; fits current single-column `main`.  
**Cons:** Competes with Branch bar for horizontal attention; on narrow screens tabs wrap or scroll.

**Fit:** Best **default** for v1 — smallest structural change, keeps the existing AppShell command rail untouched.

### Option 2 — Secondary vertical sidecar (in-page, not the global command rail)

```
[ Header ]
┌──────────┬────────────────────────────────────┐
│ Research │                                    │
│ Instr.   │         active tab body            │
│ Crew     │                                    │
│ Funding  │                                    │
│ Overview │                                    │
└──────────┴────────────────────────────────────┘
```

**Pros:** Scales to more zones; clear “mode switcher”; matches command-bridge mental model; active zone can use signal edge tick like the primary rail.  
**Cons:** Double navigation (global rail + project sidecar) risks redundancy; eats ~140–180px width; must collapse to horizontal or a select on `< lg`.

**Fit:** Strong if we **promote project zones into the primary CommandRail** when `onProject` (see §5) — then the sidecar is unnecessary. If the rail stays global-only, a **thin in-page sidecar** is still better than more vertical stacking.

### Option 3 — Hybrid (recommended product direction)

1. **v1:** Horizontal tabs under the project header (Option 1).  
2. **v1.1:** When `pathname` is a project, **extend CommandRail** with the same tab ids (or replace inert Agents / generic Workspace with real zone links). Horizontal strip and rail stay in sync — one source of truth for `activeTab`.  
3. Skip a third nav surface.

```
Global rail (project context)     In-page (optional, can hide once rail is enough)
─────────────────────────────     ──────────────────────────────────────────────
Projects                          (or omit duplicate)
Research  ←── sync ──→            tab body only
Instruments
Crew
Funding
Overview
```

This retires the fake Funding hash and the inert Agents hatch in favour of honest zones.

---

## 5. Research tab — the decluttered heart

Default body when opening a project:

```
┌ BranchBar (main line | open branches) ─────────────────────────┐
├──────────────┬────────────────────────────┬────────────────────┤
│ Threads      │ Claims / evidence /        │ Checkpoint         │
│              │ validation                 │ timeline           │
│              │                            │                    │
└──────────────┴────────────────────────────┴────────────────────┘
[ Optional: compact “Run instrument” / “Agent pass” strip → jumps to Instruments
  or opens a side drawer, so power users don’t context-switch fully ]
```

**Keep the three-column layout** — it already matches the mental model (scope → claims → history).  
**Remove from this tab:** Research crew, Collaborators, Funding, full Background essay, large toolbench, large agent trace (unless Option B).

### Selection & empty states

- No thread selected → claims + timeline show an honest awaiting state (“select a thread”); don’t empty the whole Research tab.  
- Sealed branch → existing line-sealed behaviour on timeline / instruments.  
- Contested claims in header → click-through could focus Research and scroll/highlight the claim (stretch).

---

## 6. Instruments tab

Full existing `ToolbenchPanel` + (if Option A) `AgentPassPanel`.

- Thread + branch context: **read from shared project page state**, shown as a sticky context readout at top of the tab (“Thread: … · Branch: main / …”).  
- If no thread selected, disable run CTAs with the same copy as today — don’t auto-select unless product later wants “first open thread.”  
- Agent dark-launch: hide agent block when loop off (unchanged).

---

## 7. Crew & access / Funding / Overview

| Tab | Notes |
| --- | --- |
| **Crew & access** | Existing two-column Research crew + Collaborators; natural home for invite UX |
| **Funding** | Move `FundingPanel` off the research scroll; rail “Funding” → `?tab=funding` |
| **Overview** | Background Markdown (default open), description, Edit entry for stewards, optional full metric grid + contradiction list if header is compacted |

Edit form can remain a toggle *within* Overview (or a modal) rather than injecting a bay between header and tabs.

---

## 8. State, routing, and URL

### Recommended v1 URL contract

```
/projects/{projectId}?tab=research|instruments|crew|funding|overview
```

- Default `tab=research` when missing / invalid.  
- Command rail and in-page tabs both set the same param (`router.replace` to avoid history spam, or `push` if back-stack between tabs is desired — prefer **replace** for mode switches).  
- Hash `#funding` → redirect/normalize to `?tab=funding` for one release if needed.

### Client state (stay in React for v1)

- `selectedThreadId`, `selectedBranchId`, `editing`  
- Optional later: `?thread=` / `?branch=` for shareable deep links into Research  

### Data fetching

No change required: existing TanStack Query keys already project/thread scoped. Tabs only **mount or hide** panels; prefer keeping queries enabled when the user is likely to return (or keep panels mounted and CSS-hidden for hot tabs — implementation detail). Prefer **conditional render** of heavy panels (toolbench catalog, agent polling) when not active, except leave agent polling alive if a run is in flight (important: don’t unmount an active `AgentRun` poll just because the user glanced at Funding).

---

## 9. Visual / console language for tabs

Align with design system (not invent a second pattern):

- Tab list: mono uppercase readout labels (`tracking` per `ReadoutLabel`), hairline bottom rule on the strip.  
- Active tab: **2px signal edge** (top or bottom tick) + `--text`; inactive `--text-mute`.  
- No filled pill backgrounds as the primary affordance; optional recessed bay for the whole tab body.  
- Mobile: horizontal scroll for tabs, `scroll-snap` optional; no hamburger of sections if five labels fit.  
- Badge affordances (stretch): contested count on Research; open invitation / member count on Crew; running agent pass live-dot on Instruments.

---

## 10. Accessibility

- `role="tablist"` / `tab` / `tabpanel` with `aria-selected` and keyboard ←/→.  
- Focus moves into the panel on activation (or stays on tab — pick one and document; prefer focus panel heading).  
- Contested strip and metrics remain outside the tablist so they’re not “only inside Research.”

---

## 11. Explicit non-goals (v1)

- New backend routes or project sub-pages (`/projects/x/funding` as separate Next routes) — unnecessary if query tabs suffice.  
- Reworking claim/timeline internals or toolbench honesty rules.  
- Autonomous agent UX, multi-thread orchestrator, or new instruments.  
- Global app IA redesign beyond project context zones.  
- Seed data / empty-project wizard (separate problem).

---

## 12. Migration / phasing

| Phase | Deliverable | Risk |
| --- | --- | --- |
| **P0** | Extract `ProjectHeader` + tab shell; move panels into tab panels; default Research; URL `?tab=` | Low — pure composition |
| **P1** | Wire CommandRail project zones to tabs; retire inert Agents / `#funding` hack | Low–med — shell + workspace |
| **P2** | Compact header metrics; contested → claim focus; sticky thread/branch context on Instruments | Med polish |
| **P3** | Optional sidecar *or* rail-only nav; `thread`/`branch` query params; agent in-flight sticky indicator | Med |

Ship **P0** as a single frontend release (e.g. `0.13.x` slice): demoable declutter without rail perfection.

---

## 13. Acceptance bar

A signed-in member opening a mid-size project should:

1. See **title, question, contested (if any), and Research workspace** without scrolling past crew/funding/toolbench.  
2. Reach Funding, Crew, or full Background in **one click** (tab or rail).  
3. Select a thread on Research, switch to Instruments, run a tool, switch back — **same thread/branch**, new checkpoint visible on the timeline.  
4. Commission an agent pass (flag on), leave Instruments during run, return — **trace still live**.  
5. Public visitor: same nav, write CTAs gated as today.  
6. Grayscale: active tab still obvious (edge tick + weight, not colour alone).

---

## 14. Open decisions (for implementer / product)

1. **Agent pass:** Instruments tab (A) vs collapsible on Research (B)? **Recommend A.**  
2. **Horizontal tabs only (v1) vs early rail sync (P0+P1 together)?** Recommend P0 alone if schedule is tight.  
3. **Header metrics:** keep six readouts vs compact line? Recommend compact in header, full grid on Overview.  
4. **Should Background live under Overview or remain a collapsible on Research for projects that are “context-heavy”?** Recommend Overview-only so Research stays operational.  
5. **Unmount vs hide inactive tabs** when an agent run is active — must not drop polling (see §8).

---

## 15. Implementation sketch (files)

| Area | Likely touch |
| --- | --- |
| Compose | `components/workspace/project-workspace.tsx` → thin orchestrator |
| New | `project-header.tsx`, `project-tabs.tsx` (or `project-zone-nav.tsx`) |
| Panels | Existing panels largely **move, not rewrite** |
| Shell | `command-rail.tsx` — live zones when `onProject` (P1) |
| URL | `useSearchParams` / `nuqs` or thin wrapper; no new App Router segments required for v1 |
| Types | Optional `ProjectTabId` union shared by rail + tabs |

No migration. No API. Frontend-only; verify with `npm run typecheck && npm run lint`.

---

## 16. Summary

| Today | Proposed |
| --- | --- |
| One scroll of 9 peer sections | Persistent header + **5 tabs** |
| Research buried under config + tools | **Research default** |
| Funding via weak `#hash` | First-class tab (+ rail) |
| Agents rail inert | Point at Instruments / agent surface |
| Thread/branch local but easy to lose mentally when scrolling | Explicit shared context across tabs |

**One line:** Stop using vertical distance as the only organizer; use **modes** so the deepdive page is a research console with side rooms, not a vertical archive of every feature we shipped.
