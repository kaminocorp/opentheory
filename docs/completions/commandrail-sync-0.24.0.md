# 0.24.0 — CommandRail sync

**Goal.** Close the deferred deepdive Phase B (historically `0.14.1`): make the
CommandRail / zone nav real. No dead links, no inert Agents zone.

**Shape.** Frontend shell + shared tab contract. **No backend, schema, API, or
migration.** Presentation stays the quiet-minimal `0.15.0` rail (filled tile,
no pulse).

## Why

`0.14.0` put `?tab=` behind the in-page strip and kept Research + Instruments
mounted so an agent poll survived a tab switch. The left rail did not join that
contract: Funding still emitted `#funding`, Workspace was a same-page no-op, and
Agents was a permanently inert "coming soon" hatch — leftover from before the
thin agent loop shipped. Two nav surfaces that disagreed is one too many.

## What landed

- `lib/project-tab.ts` owns `PROJECT_TAB_IDS` / `ProjectTabId` /
  `projectTabHref` / `buildCommandRailZones`. The strip, the hook, and the rail
  import the same union.
- On a project, rail zones are `<Link href="${pathname}?tab=<id>">` for
  `research` · `instruments` · `crew` · `funding` · `overview`. Active state
  (`aria-current="page"`) is derived from the URL tab.
- Off-project, the five tab zones render as contextual-off (`aria-disabled`,
  "open a project first") — the `0.6.7` present-but-inactive contract, not a
  coming-soon lie.
- **Agents removed.** It mapped to no distinct surface: the agent pass is on
  Instruments; project-wide Run research is on Overview. Relabeling it
  "Operators" and pointing it at Instruments would have duplicated that zone.
- **`#funding` hash target retired.** The Funding bay no longer carries
  `id="funding"`. The hook still rewrites a leftover `#funding` bookmark to
  `?tab=funding` once.
- Research + Instruments keep-alive is unchanged (`KEEP_ALIVE_TABS`). The rail
  does not remount the workspace.
- The rail wraps `useSearchParams` in its own `<Suspense>` so the global
  `AppShell` does not fail the Next 15 static-generation deopt.

## What did not change

- Tab set stays frozen at five. No new App Router segments.
- Keep-alive / agent-poll contract from `0.14.0`.
- Phase C (badges already partial; contested click-through; running-pass
  LiveDot) and Phase D (`?thread=` / `?branch=`) remain open.
- Backend, schema, ledger writes, instruments.

## Tests

Node's built-in test runner against the pure tab/rail contract
(`frontend/src/lib/project-tab.test.ts`):

- Five ids in strip/rail order; keep-alive is Research + Instruments.
- Every tab deep-links via `?tab=<id>`; unknown/missing falls back to research.
- Sibling query params survive a tab flip.
- On a project, exactly one rail zone is active and every tab href is live.
- On the index, Projects is active and project zones are disabled, never hashed
  or inert.
- No Agents zone and no `#funding` href in either context.

## Verification

Recorded after the implementation pass — do not treat the placeholders in the
changelog body as a count until this section is filled from a real run.

## Unverified

- Pixel-level browser walk of rail + strip staying in sync (the same owed
  eyeball pass as `0.14.0` / `0.15.0`).
- Live agent-trace keep-alive across a rail click (the mount contract is
  unchanged and unit-locked; the poll itself was not driven).
- No backend suite is in scope; run it only to confirm this branch did not
  touch it.
