# 0.31.0 — Deepdive Phase D (shareable Research deep links)

**Goal.** Close the optional deepdive Phase D (after `0.14.0` / `0.24.0` /
`0.30.0` A/B/C): shareable Research selection, a cross-tab live tick while a
pass is running, and a recorded rail-only nav decision. No sidecar.

**Shape.** Frontend workspace chrome only. **No backend, schema, API, or
migration.** Sits on shipped `0.30.0` Phase C polish. Does not reopen
`0.14.x` as the changelog head.

## Why

`0.14.0` made `?tab=` the surface. `0.24.0` synced the CommandRail.
`0.30.0` added badges and contested click-through. A Research view was
still local `useState`: a shared URL opened the right tab and then the
defaults (no thread; the main line). An in-flight pass was visible on the
Instruments badge, but the keep-alive poll had no chrome outside that
label. Phase D is those two payoffs, plus writing down the nav decision
Phase B already implied.

## What landed

- **D1 — Shareable Research deep links.** `?tab=research&thread=<id>&branch=<id>`
  restores the selected thread and line. `useProjectTab` grows into
  `useProjectView`: one `router.replace` (not `push`), `{ scroll: false }`.
  The `?tab=` contract is unchanged — flipping tabs keeps `thread` /
  `branch`. Malformed ids drop immediately; unknown ids drop only after
  the matching list loads; a failed list does not erase a share link we
  could not confirm. Invalid ids never 500 — the workspace stays on
  defaults (no thread; main line).
- **D2 — Cross-tab in-flight indicator.** The same newest-run /
  keep-alive `passRunning` flag `0.30.0` already derives (no new fetch)
  now lights a quiet "Pass running" cue on the persistent strip and a
  `LiveDot` on the CommandRail Instruments zone. Gone when idle. The
  Instruments tab badge is unchanged. Active nav still reads from weight
  + edge tick / filled rail tile — never colour-only.
- **D3 — Rail-only nav.** No in-page sidecar was built. Phase B already
  gives project-context nav on the CommandRail. A third surface would
  exist only if the frozen five-tab set is no longer enough. Recorded
  here and in the archive plan / roadmap.

## What did not change

- Tab set stays frozen at five. No new App Router segments.
- Research + Instruments keep-alive (`KEEP_ALIVE_TABS`).
- Contested click-through, tab badges, header metric line (`0.30.0`).
- Backend, schema, ledger writes, instruments. `create_checkpoint` is
  untouched. Funder / contributor / validator stay separate.
- Account ≠ Actor. No auto-validate / auto-fund / auto-merge.

## Nav decision (D3)

**Rail-only.** The in-page strip is the project section tablist. The
CommandRail is the only second nav surface — live `?tab=` links, same
source of truth. An in-page sidecar would be a third way to say the same
five names. Skip it until a real sixth zone forces the question.

## Caveats (honest)

- The live cue is still the newest pass on the **selected** thread, not a
  project-wide "something is running" light. A pass on another thread, a
  `0.22.0` orchestration, or a `0.25.0` campaign does not light it. That
  would need a new fetch; Phase D does not add one.
- `branch` is a branch UUID. `branch=main` is not a name alias — it is
  malformed and ignored (main line is the default: omit the param).
- No pixel-level browser walk (the same owed eyeball pass as
  `0.14.0`–`0.16.0` / `0.30.0`). Deep-link restore and the live cue were
  checked by unit tests + typecheck/lint/build, not by clicking a live
  project.

## Verification

```bash
cd frontend && npm test            # 18 passed (including 0.31.0 deep-link contract)
cd frontend && npm run typecheck   # clean
cd frontend && npm run lint        # clean
cd frontend && npm run build       # clean — must catch a missing Suspense / useSearchParams deopt
```

`npm test` now resolves: the Node ESM runner needs a `.ts` suffix on the
local import, and `tsc` excludes `*.test.ts` so that suffix does not trip
`allowImportingTsExtensions`. A pre-existing `assert.equal` on an array
is `deepEqual`.

`npm run build` is the meaningful gate: a missing `<Suspense>` around
`useSearchParams` fails the Next 15 static-generation deopt. The
`/projects/[projectId]` route stays on-demand (`ƒ`). Backend was not
run — this release does not touch it.

## Unverified

- Pixel-level browser walk of `?thread=` / `?branch=` restore, invalid-id
  degrade, strip + rail live cue, and grayscale of the new chrome.
- Live agent-trace keep-alive across a tab switch (mount contract
  unchanged; the poll itself was not driven).
- No backend suite is in scope; run it only to confirm this branch
  did not touch it.
