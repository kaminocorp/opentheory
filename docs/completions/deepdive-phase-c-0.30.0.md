# 0.30.0 — Deepdive Phase C polish

**Goal.** Close the deferred deepdive Phase C (historically `0.14.2`): finish
the compact header metric line, make contested claims clickable into the
Research claim list, render tab badges from data the workspace already
holds, and tell the truth on the Instruments context readout.

**Shape.** Frontend workspace chrome only. **No backend, schema, API, or
migration.** Sits on shipped `0.29.0` semantic git diff. Does not reopen
`0.14.x` as the changelog head.

## Why

`0.14.0` moved nine peer bays into a header + five tabs. `0.24.0` made the
CommandRail agree with `?tab=`. The remaining polish was the difference
between "the work is one click away" and "the honesty surface actually
takes you there":

- The compact metric line still read `threads n` rather than the locked
  `n threads · n claims · n checkpoints`.
- The contested strip was one button that only flipped to Research.
- Tab badges were partial (contested + members). No running-pass
  `LiveDot`. No invite count.
- Instruments said "none selected" / "sealed" without saying what that
  means for a run.

## What landed

- **C1.** Header metric line is `n threads · n claims · n checkpoints`
  (mono number, mute label, `·` separators). Overview's six-tile grid
  stays, with a quiet "reference" line so it does not compete with the
  operational counts above the fold.
- **C2.** Each contested statement is its own control. Click →
  `setTab("research")`, select `thread_id` when the overview item has
  one, pass `focusClaimId` into `ClaimListPanel`. The row gets a fail
  edge tick, a stronger hairline, `scrollIntoView`, and focus. The
  strip heading still opens Research without focusing a claim. Picking
  another thread clears the focus.
- **C3.** Badges reuse existing TanStack keys — no new endpoint:
  - Research: `overview.contradictions.length` (already fetched).
  - Crew: `members` + outstanding `projectInvitations` (same keys
    Collaborators already uses; steward-only invitations stay gated).
  - Instruments: `LiveDot tone="signal" pulse` iff the newest
    `AgentRun` on the *selected* thread is `running` (same
    `agentRuns` / `agentRun` keys as `AgentPassPanel`, which is
    keep-alive). The polled trace status wins over a stale list row.
    The list is invalidated on `running → terminal` so the badge
    drops when the pass settles.
  Active tab identity is still weight + the 2px signal edge tick.
  `LiveDot` / fail-tone counts are status, not the active marker.
- **C4.** Sticky Instruments readout: "No thread selected" plus "Pick
  a thread on Research — a run has nowhere to land." Sealed line:
  "This line is sealed — runs will not record here."
- Keep-alive, `?tab=`, CommandRail sync, and every panel's write path
  are unchanged.

## What did not change

- Tab set stays frozen at five. No new App Router segments.
- Research + Instruments keep-alive (`KEEP_ALIVE_TABS`).
- Phase D (`?thread=` / `?branch=`, a *project-wide* in-flight
  indicator, sidecar decision) remains open.
- Backend, schema, ledger writes, instruments. `create_checkpoint`
  is untouched. Funder / contributor / validator stay separate.
- Account ≠ Actor.

## Caveats (honest)

- The Instruments `LiveDot` is the newest pass on the **selected
  thread**, not a project-wide "something is running" light. A pass
  on another thread, a `0.22.0` orchestration, or a `0.25.0` campaign
  does not light the badge. That cross-tab indicator is Phase D.
- A contradiction whose `thread_id` is null still opens Research but
  cannot select a thread; the claim is highlighted only if it is
  already in the visible list.
- Invite count is steward-only (the invitations read 403s for
  visitors). Visitors see members only. Same as the Crew tab.
- No pixel-level browser walk (the same owed eyeball pass as
  `0.14.0`–`0.16.0`).

## Verification

Recorded after the implementation pass.

## Unverified

- Pixel-level browser walk of contested click-through, badge
  grayscale, and the sealed / no-thread readout.
- Live agent-trace keep-alive across a tab switch (mount contract
  unchanged; the poll itself was not driven).
- No backend suite is in scope; run it only to confirm this branch
  did not touch it.
