# Roadmap Next Steps

> **Last updated:** 2026-09-25 · **Current release line:** `0.17.x` (Phase 1 agent autonomy —
> human review is opt-in) sitting on `0.16.x` (claim grounding, now rolled up at thread/project
> scale). For the per-phase ledger see `docs/changelog.md`; for the two most recent lines see
> `docs/completions/agent-autonomy-0.17.0.md` and `docs/completions/grounding-rollup-0.16.3.md`.
> The `0.14.x` plan (phases B–D still open) now lives at
> `docs/archive/project-deepdive-tabs-0.14.md`.
>
> **In flight / next (Phase 1 overnight train — not shipped):** Tier 1 literature pin
> instruments — Crossref / arXiv, and OpenAlex if the key/readiness is there — on the proven
> `source.pin` shape. Human-review opt-in (`0.17.0`) and the `0.16.3` thread-level grounding
> rollup are **shipped**. Unmerged work is not claimed as shipped.

## Where we are

OpenTheory is a **live research ledger** with a deterministic toolbench, a **machine-checked
verifier** (`z3.prove`), and a **thin agent loop** — operated from a five-tab project workspace.
The foundation through `0.4.x` (ledger writes, validation, branching), identity and collaboration
through `0.8.x`, auth and funding through `0.6.x`–`0.7.x`, the toolbench spine plus flagship math
instruments through `0.9.x`–`0.10.x`, the execution sandbox through `0.11.x`, the thin agent loop
through `0.12.x`, `z3.prove` through `0.13.x`, the tabbed deepdive through `0.14.x`, the
quiet-minimalist re-skin in `0.15.0`, and **claim grounding in `0.16.0`**, are all shipped.

**Confidence now has two axes.** `0.16.0` closed the gap where a claim carrying a machine-checked
proof and a claim carrying nothing but an opinion both read `signal: "none"`: evidence-derived
**grounding** (A/B/C/D, with retrieval off-ladder as `cited`) sits beside the validation-derived
signal, derived from what actually ran and never stamped. The two are deliberately never merged —
a single blended number would be the "naked score" `primitives.md` forbids.

**One verification gap carries forward:** neither `0.14.0`, `0.15.0`, nor `0.16.0` got a
pixel-level browser walk — no connected browser extension was available in any of the three passes.
All are green on typecheck/lint/build and runtime-spot-checked (pages 200, served markup carries the
new tokens/states), but the eyeball pass recorded in `docs/completions/design-overhaul-0.15.0.md` is
still owed — now with the `0.16.0` grade chip added to its checklist. `0.16.0` also left its 8
DB-gated read-model round-trips unrun (no local Postgres); see
`docs/completions/claim-grounding-0.16.0.md` §Unverified.

A signed-in member can today:

1. Own or collaborate on a project; invite others; assign Research crew models (UI only).
2. Decompose work into threads; add claims; attach evidence; record checkpoints.
3. Fork and close branches; record validations; read contradiction signals.
4. Run **six** production instruments from the workspace — with KaTeX-readable math and bounded
   execution (subprocess isolation, wall-clock/memory caps, concurrency limit):
   `calc.eval`, `expr.compare`, `geometry.coordinate_measure`, `oeis.search`,
   `counterexample.search`, **`z3.prove`** — each landing an attributed checkpoint through the
   chokepoint.
5. Do all of it from a **five-tab deepdive** (`research` · `instruments` · `crew` · `funding` ·
   `overview`) under a persistent header, deep-linkable via `?tab=`. Research and Instruments
   render keep-alive, so an in-flight agent trace survives a tab switch.
6. Read each claim's **grounding rung** inline — `proven` / `refuted` / B / C / D / `cited` /
   `ungrounded` — with a one-line *"what would raise this"*, so the ladder is actionable rather
   than decorative; and read the same derivation rolled up on the thread list and Overview
   (`"3 claims at B, 1 ungrounded"`).

The flagship *measuring across a corner* thread (claims 1–4) is walkthrough-ready with
shipped instruments. Claim 5 (Lean proof → Grade A) remains explicitly out of scope until
the execution substrate exists.

**Agents are now bounded operators, and a successful pass stands.** A member commissions a
**Run agent pass** on a thread (`0.12.x` + `0.17.0`): the assigned Research-crew model plans a
capped sequence of *existing* instrument runs, and the agent Actor lands attributed checkpoints
on a durable agent branch through the **same** `run_instrument` chokepoint humans use — a full
`AgentRun` trace shows what it tried and what landed. **Human review is opt-in audit** (accept a
claim, reject the line as a dead end, or fork further) — it is not required before the pass is
done for the operator. Still bounded, not continuous: no scheduled loop, no multi-thread
orchestrator, no project-budget metering yet (`0.12.5`, deferred — per-pass safety caps bound
blast radius). Prod enablement is still the ops flip `AGENT_LOOP_ENABLED=true` + the
`OPENROUTER_API_KEY` Fly secret. The guiding constraint held throughout: every capability was
human-usable through the API *first*, so the agent simply uses what humans already could.

## Guiding principle (unchanged)

Build the smallest complete research workflow that records what changed, why it changed,
who changed it, and what evidence or artifacts were involved — then extend it without
bypassing the checkpoint chokepoint or conflating funder / contributor / validator roles.

## Recommended next releases

### `0.17.x` — Phase 1 agent autonomy ✅ **shipped** (`0.17.0`)

Delivered: a completed pass's attributed checkpoints stand without a mandatory human gate.
`requires_review` is a computed `false` on the `AgentRun` read model; `AgentRunStatus` has no
`awaiting_review`; the trace copy is driven by that field. Accept / reject / fork remain the
shipped Validation and Branch write paths. **No schema, no migration.** Safety caps unchanged;
`0.12.5` budget metering still deferred. See `docs/completions/agent-autonomy-0.17.0.md`.

**Natural follow-ons:** `0.12.5` project-budget metering; an iterative plan→observe→replan
within a pass; eventually the orchestrator that allocates project budget across subagents.

### `0.16.x` — Claim grounding ✅ **shipped and hardened** (`0.16.0`–`0.16.3`)

Delivered: the `(instrument, status)` grade matrix beside the registry (with the conformance harness
now *forcing* a grading decision on every registered instrument), the batch-loaded `ClaimGrounding`
read model, and the grade chip + raise line on the claim row. Pure read-model derivation — no
migration, table, column, or endpoint; `compute_signal` untouched.

**The open follow-ons are the payoff the ladder exists for:**

- ~~**`0.16.1` — grounding into the planner + budget**~~ ✅ **shipped**. The planner now receives
  each open claim's rung plus a matrix-derived raise path (and a *settled* stop line), and every
  completed pass records what it moved (`AgentRun.grounding_yield`, migration `0014`). The loop is
  judged on yield, not activity. **`BudgetPolicy` was deliberately left unchanged** — no implementer
  until `0.12.5` — but the recorded measure is what metering will read.
- ~~**`0.16.2` — post-review hardening**~~ ✅ **shipped**. The review pass over `0.16.0`–`0.16.1`.
  No CRITICAL/HIGH; closes one MEDIUM (a `proven → refuted` transition — a proof overturned by an
  exact counterexample — scored `unchanged`, so the trace reported no movement on the most
  consequential event the ledger can record), builds the history-row yield the summary schema already
  claimed, and separates *never measured* from *measured zero*. No schema, no migration. See
  `docs/completions/grounding-yield-0.16.2.md`.
- ~~**`0.16.3` — thread-level rollup**~~ ✅ **shipped**. Thread list, thread read, and project
  overview carry a derived `grounding_rollup` (`"3 claims at B, 1 ungrounded"`). Pure
  aggregation of existing `ClaimGrounding` headlines — no schema, no migration. See
  `docs/completions/grounding-rollup-0.16.3.md`. *(Was numbered `0.16.2`; shifted by the
  hardening pass, per the repo convention that a review pass takes the next patch.)*
  Paired with `0.17.0` (agent-pass human review is opt-in).

### `0.15.x` — Design overhaul ✅ **shipped** (`0.15.0`, `edfbe18`) · browser pass owed

Delivered: the ornamental Console language (measured-field grid, grain,
vignette, brackets, chamfers, hatch, all-caps mono kickers) retired for a neutral near-black
system — flat 12px cards, 1px hairlines, sentence-case sans, mono for data only, crimson the lone
accent. Presentation-only: every query, mutation, gate, aria pattern, and the `?tab=` contract are
untouched, and the honesty rules (failure at full weight, undecided never reads as a pass) carry
over intact.

**To close the line:** run the recommended eyeball pass from
`docs/completions/design-overhaul-0.15.0.md` — `/styleguide` (all primitives + grayscale
emulation), the deepdive's five tabs, a toolbench result card, and the sign-in dropdown. No
pixel-level browser walk has been possible since `0.14.0` (no connected browser extension).

### `0.14.x` — Project deepdive tabs ✅ **Phase A shipped** (`0.14.0`); B–D outstanding

Delivered: the five-tab shell with `?tab=` as the single source of truth, the persistent header,
keep-alive Research/Instruments mounting (load-bearing for the agent poll), the WAI-ARIA tabs
pattern, and the `<Suspense>` boundary. **The plan's later phases did not ship** and remain the
cheapest available frontend wins — full checklists in
`docs/executing/project-deepdive-tabs-0.14.md` §6:

- **Phase B (`0.14.1`, low–med risk)** — CommandRail sync: real zone links → `?tab=<id>` with
  active state derived from the URL; retire the legacy `#funding` hash target and the **inert
  Agents zone** (no rail zone should stay permanently dead).
- **Phase C (`0.14.2`, polish)** — contested-claim click-through into `ClaimListPanel`, tab badges
  (contested count, member count, a running-pass `LiveDot` derived from the newest `AgentRun`),
  and the Instruments context-readout refinement.
- **Phase D (optional)** — `?thread=` / `?branch=` deep links, a cross-tab agent in-flight
  indicator, and recording the rail-only nav decision (recommendation: skip the in-page sidecar).

### Tier 1 retrieval wave — literature pin instruments

The highest-value *product* step from here: it directly widens what an agent pass can do.
**Phase 1 overnight train (a) — in flight, not shipped.**

- Crossref / arXiv pin instruments first (reuse the `source.pin` pattern from `oeis.search`).
- OpenAlex on the same shape **if** the API key / readiness is there (the polite-pool retired;
  catalog notes a key is required as of Feb 2026).
- See `docs/plans/toolbench-catalog.md` Tier 1 table.

### `0.12.x` — Thin agent loop ✅ **shipped** (`0.12.0`–`0.12.4`)

Delivered: a bounded pass (planner → capped instrument runs on a durable agent branch through the
same chokepoint), a request-scoped `202` + background execution, the pollable `AgentRun` trace, and
the workspace trigger/trace UI, and **`0.17.0` made review opt-in**. **`0.12.5` (project-budget
metering) deferred** — the per-pass safety caps (`agent_pass_max_runs`, token cap) bound blast
radius, so the line demos without it. The prod light-up step is **both**
`AGENT_LOOP_ENABLED=true` **and** the `OPENROUTER_API_KEY` Fly secret
(`fly secrets set`, never `fly.toml [env]`) — one without the other is not a launch.
Flag off ⇒ every agent route `404`s.

**Natural follow-ons (pick per demand):** `0.12.5` project-budget metering (debit the project's
compute budget per pass, honoring funder/contributor separation); an iterative plan→observe→replan
within a pass; and eventually the orchestrator agent that allocates project budget across subagents.

### `0.13.x` — Z3 (`z3.prove`) ✅ **shipped and hardened** (`0.13.0`–`0.13.5`)

Delivered: `z3-solver` + soft-timeout config; closed-allow-list SymPy→Z3 translator; two-stage
validity check (vacuous-hypotheses guard → `H ∧ ¬goal`); catalog registration; drive form +
proof / counter-model / undecided cards. A supporting `result` is now a **proof** (`artifact_kind=
"proof"`), not weak support. Soft timeout stays under the subprocess wall-clock so hard problems
record as honest `undecided`.

**The deferred Phase 2 write-path slice is closed** (`0.13.5`): DB-gated prove/refute round-trips
through `run_instrument`, a real killable-subprocess test, and a deterministic unit test for the
`unknown → {timeout, incomplete}` honesty mapping. The review pass found no CRITICAL/HIGH defect —
no false-proof path exists.

**Natural follow-ons (verifier wave remainder):**

- `z3.satisfy` — model-finding as the primary output.
- Boolean connectives / `bool` sort (needs a parser beyond `split_relation`).
- Quantifiers; full replayable proof terms (out of scope for v1).
- **Lean** (Tier 2) — Claim 5 / Grade A; still gated on a heavier execution substrate.

### `0.10.6+` (optional stretch) — `interval.eval`

Proven numeric enclosures via `python-flint` / Arb — originally Appendix B of the
`falsify-and-render-0.10` plan, **which no longer exists in the repo**, so this would need
re-specifying before it could be picked up. Not required for flagship claims 1–4, and `z3.prove`
now covers the symbolic-validity need — worth reviving only if *numeric* interval bounds become a
demo requirement.

### Deferred / deprioritized

| Item | Notes |
|---|---|
| **`0.5.0` demo seeding** | Plan doc since removed; team preference is **no seed data** — projects start from scratch. Revisit only if empty-state UX becomes a product problem. |
| **`formula.render` instrument** | Superseded for v1 by additive `*_latex` + KaTeX in `formula.tsx` (`0.10.4`–`0.10.5`). |
| **Tables / plots (`table.*`, `plot.*`)** | Bench 6; after core agent loop or when a demo needs tabular falsification grids. |
| **Real funding / settlement** | `FundingAllocation` is recorded; Stripe etc. remain future. |
| **Reputation / influence** | Vision doc; no data model yet. |
| **Object storage for large artifacts** | Blobs stay off Postgres; upload path not built. |

## Priority order (from here)

1. ~~**Execution sandbox** (`0.11.x`)~~ ✅ shipped.
2. ~~**Thin agent loop** (`0.12.x`)~~ ✅ shipped — Research crew is now a bounded operator.
3. ~~**Z3 instrument** (`0.13.x`)~~ ✅ shipped — first machine-checked proof path (`z3.prove`).
4. ~~**Z3 write-path tests**~~ ✅ closed in `0.13.5` alongside the review-pass hardening.
5. ~~**Deepdive tab shell** (`0.14.0`)~~ ✅ shipped — Phase A; B–D still open (item 8).
6. ~~**Design overhaul** (`0.15.0`)~~ ✅ shipped — but the **browser eyeball pass** is still owed
   (`/styleguide` with grayscale emulation **including the `0.16.0` grade chip**, the five tabs, a
   toolbench result card, the sign-in dropdown). Cheapest item on the list, and the only check the
   last *three* frontend releases missed.
7. ~~**Claim grounding** (`0.16.0`)~~ ✅ shipped — the evidence axis. Its 8 DB-gated round-trips
   are written but unrun (no local Postgres); run them next time a test database is available.
8. ~~**`0.16.1` grounding → planner + budget**~~ ✅ shipped, ~~**`0.16.2` post-review hardening**~~ ✅
   shipped — the loop plans to *raise* a rung, reports what it moved, and the review pass closed the
   case where a `proven → refuted` contradiction read as no movement at all. Migration `0014` is
   ✅ **applied to the live database** (2026-08-02); the **backend code deploy is outstanding** — the
   column exists and nothing reads it yet. Run the two DB-gated orchestrator round-trips when a test
   DB is available.
9. ~~**`0.16.3` thread-level grounding rollup + `0.17.0` review opt-in**~~ ✅ shipped
    (same branch).
10. **Tier 1 retrieval** — literature pin instruments (Crossref / arXiv; OpenAlex if ready) on the
    proven `source.pin` shape. Directly widens what an agent pass can *do*. (Each new instrument now
    also needs a grade-matrix row — the harness will insist.) **Phase 1 overnight train (a).**
11. **`0.14.1` Phase B** — CommandRail sync; retires the last two fakes (`#funding`, inert Agents
    zone). Small, self-contained, and removes visible dead affordances.
12. **`0.12.5` project-budget metering** — debit the project's compute budget per pass (stretch; the
    per-pass safety caps already bound a single pass). The yield measure (`0.16.1`) is what
    metering will read.
13. **`0.14.2` Phase C** — tab badges, contested click-through, context-readout polish.
14. **Bench 6 surfaces** — tables and Vega-Lite plots when a thread needs them.
15. **Lean + full substrate** — Claim 5; only after the above.

## Shipped milestones (reference)

| Release | What landed |
|---|---|
| `0.3.x` | Human-operable ledger write path + workspace |
| `0.4.x` | Validation, branching, enriched read models |
| `0.6.x`–`0.7.x` | Auth (Supabase JWT), `Account`/`Actor`, funding allocations, live deploy |
| `0.8.x` | OpenTheory Console, stewardship, `@username`, invitations, Research crew UI |
| `0.9.x` | Toolbench spine, adapter/registry, five instruments, drive/show UI, security hardening |
| `0.10.x` | `counterexample.search`, LaTeX companions, KaTeX — flagship claims 1–4 ready |
| `0.11.x` | Execution sandbox — killable subprocess, wall-clock/memory caps, concurrency limit |
| `0.12.x` | Thin agent loop — planner, bounded orchestrator, `202`+background API, workspace UI |
| `0.13.x` | `z3.prove` — machine-checked validity (proof / counter-model / undecided) + hardening |
| `0.14.x` | Project deepdive — persistent header + five `?tab=` tabs, keep-alive agent trace |
| `0.15.x` | Quiet-minimalist re-skin — neutral near-black system, ornament retired |
| `0.16.x` | Claim grounding — the evidence grade ladder, derived beside the validation signal, consumed by the planner as a yield measure, post-review hardened, and rolled up at thread/project scale (`0.16.3`) |
| `0.17.x` | Phase 1 agent autonomy — a completed pass stands; human accept/reject/fork is opt-in audit |

## Success criteria for the next milestone

`0.16.1` / `0.16.2` already closed the yield-measure line (planner sees each open claim's rung;
a pass reports what it moved). **`0.17.0` (review → opt-in)** and **`0.16.3` (thread-level
rollup)** are shipped: a completed pass stands without a human gate, and a thread with three
B claims and one ungrounded reads that sentence on the thread list and Overview.

**Tier 1 retrieval** (the remaining Phase 1 overnight train) is successful when an agent pass
(or a human) can pin a literature source (Crossref / arXiv, and OpenAlex if ready) as
content-addressed Evidence via the same `source.pin` shape `oeis.search` proved — landing an
attributed checkpoint through the chokepoint, with a reproducible citation
(`url` + `retrieved_at` + `raw_response_hash`), and carrying its grade-matrix row
(retrieval instruments are off-ladder: `cited`, never a letter).
