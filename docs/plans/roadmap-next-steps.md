# Roadmap Next Steps

> **Last updated:** 2026-09-26 · **Current release line:** `0.36.1`
> (research-git blame), sitting on shipped `0.35.0`
> **Last updated:** 2026-09-26 · **Current release line:** `0.36.3`
> (honesty polish on shipped `0.36.0` blame), sitting on shipped `0.36.0`
> (`71a8929`) and shipped `0.35.0`
> **Last updated:** 2026-09-26 · **Current release line:** `0.38.0`
> (Z3 boolean connectives), sitting on shipped `0.36.0`
> (research-git blame, `71a8929`) and shipped `0.35.0`
> **Last updated:** 2026-09-26 · **Current release line:** `0.37.0`
> (GitHub Actions CI with Postgres), sitting on shipped `0.36.0`
> (research-git blame, `71a8929`) and the R1 assessment (`375733a`)
> and shipped `0.35.0`
> **Last updated:** 2026-09-26 · **Current release line:** `0.36.2`
> (assessment R2 P2 bugfixes — ThreadCreate + agent-trace honesty +
> write-path suite), sitting on `0.36.1` (assessment R1 remediation,
> #23) and shipped `0.36.0` (research-git blame) and shipped `0.35.0`
> (`interval.eval` proven enclosures, `1ca7116`) and shipped `0.34.0`
> (Bench 6 tables & Vega-Lite plots, `a7cd946`) and shipped `0.33.0`
> (`z3.satisfy` model-finding, `e3a07ea`) and shipped `0.32.0`
> (concurrent campaign cycles under project budget), `0.31.0` (deepdive Phase D — shareable Research deep links), `0.30.0`
> (Phase C polish — historical alias `0.14.2`), `0.29.0`
> (semantic git diff), `0.28.0` (live OpenRouter price metering),
> `0.27.0` (concurrent sub-passes under project budget), `0.26.0` (Mathlib /
> lake Grade-A path on `lean.prove`), `0.25.0` (continuous
> research under budget), `0.24.0` (CommandRail sync — historically the
> deferred deepdive Phase B / `0.14.1`), `0.23.0` (Lean 4 Grade-A path —
> prelude `lean.prove`), `0.22.0` (thin multi-thread orchestrator), `0.21.0`
> (research-git merge + tag), `0.20.0` (plan → observe → replan), `0.19.0`
> (project-budget metering), `0.18.0` (Tier-1 literature pins), `0.17.0`
> (review is opt-in) and `0.16.3` (thread/project grounding rollup). For the
> per-phase ledger see `docs/changelog.md`; for the line just closed see
> `docs/completions/honesty-polish-0.36.3.md`. The deepdive line
> `docs/completions/z3-boolean-connectives-0.38.0.md`. The deepdive line
> `docs/completions/github-actions-ci-0.37.0.md`. The deepdive line
> (A–D) is closed; the archive plan is at
> `docs/archive/project-deepdive-tabs-0.14.md`.
>
> **Next after this line:** the still-owed browser eyeball pass.
> Quantifiers on Z3 remain later. Lean REPL / LeanDojo remain later.
> Does not claim `0.36.1` / `0.36.2` / `0.37.0`. `0.33.0`–`0.36.0` are
> on `main`. ~~Boolean connectives / `bool` sort~~ ✅ shipped as `0.38.0`.
> Unmerged assessment remediations (`0.36.1` / `0.36.2`) are not
> claimed as shipped. Lean REPL / LeanDojo remain later.
> ~~Blame-as-an-op~~ ✅ shipped as `0.36.0`. ~~CI + Postgres~~ ✅
> shipped as `0.37.0`. `0.33.0`–`0.36.0` are on `main`.
> **Next after this line:** the still-owed browser eyeball pass. Unmerged
> work is not claimed as shipped (`0.36.1` is this patch). Lean REPL /
> LeanDojo remain later.
> ~~Blame-as-an-op~~ ✅ shipped as `0.36.0` (`71a8929`). `0.33.0`–`0.36.0`
> work is not claimed as shipped (`0.36.1` / `0.36.2` / `0.37.0` /
> `0.38.0` remain open PRs). Lean REPL / LeanDojo remain later.
> ~~Blame-as-an-op~~ ✅ shipped as `0.36.0` on `main`. `0.33.0`–`0.36.0`
> are on `main`.
> work is not claimed as shipped (`0.36.1` / `0.36.2` are stacked
> branches, not `main`). Lean REPL / LeanDojo remain later. Remaining
> R1/R2 P2s (file splits, CI, naming, confidence chrome) stay deferred.
> ~~Blame-as-an-op~~ ✅ shipped as `0.36.0` on `main` (`71a8929`).
> `0.33.0`–`0.36.0` are on `main`.

## Where we are

OpenTheory is a **live research ledger** with a deterministic toolbench, two
**machine-checked verifiers** (`z3.prove`, `lean.prove`), a **model-finder**
(`z3.satisfy`), and a **thin agent
loop** — operated from a five-tab project workspace.
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
3. Fork, merge, and close branches; pin tags; record validations; read contradiction signals.
4. Run **seventeen** production instruments from the workspace — with KaTeX-readable math and bounded
   execution (subprocess isolation, wall-clock/memory caps, concurrency limit):
   `calc.eval`, `expr.compare`, `geometry.coordinate_measure`, `oeis.search`,
   `counterexample.search`, **`z3.prove`**, **`z3.satisfy`**, **`lean.prove`**, plus the literature pins
   **`crossref.lookup`**, **`arxiv.lookup`**, **`openalex.lookup`**, plus Bench 6
   **`table.create`**, **`table.derive_column`**, **`table.render`**, **`plot.function`**,
   **`plot.points`**, plus **`interval.eval`** — each landing an
   attributed checkpoint through the chokepoint.
5. Do all of it from a **five-tab deepdive** (`research` · `instruments` · `crew` · `funding` ·
   `overview`) under a persistent header, deep-linkable via `?tab=`. Research and Instruments
   render keep-alive, so an in-flight agent trace survives a tab switch. Contested header
   items land on that claim in Research; tab badges reuse existing reads (`0.30.0`).
   A Research view is shareable via `?thread=` / `?branch=` (`0.31.0`); an in-flight
   pass shows a quiet live cue on the strip and CommandRail.
6. Read each claim's **grounding rung** inline — `proven` / `refuted` / B / C / D / `cited` /
   `ungrounded` — with a one-line *"what would raise this"*, so the ladder is actionable rather
   than decorative; and read the same derivation rolled up on the thread list and Overview
   (`"3 claims at B, 1 ungrounded"`).

The flagship *measuring across a corner* thread (claims 1–4) is walkthrough-ready with
shipped instruments. Claim 5 has a **Grade-A path** (`lean.prove`, `0.23.0` prelude / `0.26.0`
Mathlib opt-in) when the optional toolchain is installed; missing Lean or
Mathlib is honest `undecided`.

**Agents are now bounded operators, and a successful pass stands.** A member commissions a
**Run agent pass** on a thread (`0.12.x` + `0.17.0` + `0.19.0` + `0.20.0`): the assigned
Research-crew model plans a short batch of *existing* instrument runs, observes the
outcomes and grounding yield, and may replan — still inside one pass, still hard-capped.
The agent Actor lands attributed checkpoints on a durable agent branch through the
**same** `run_instrument` chokepoint humans use — a full `AgentRun` trace shows each
plan version, why it replanned, and what landed. **Human review is opt-in audit** (accept
a claim, reject the line as a dead end, or fork further) — it is not required before the
pass is done for the operator. **A project-level orchestrator shipped in `0.22.0` / `0.27.0`:**
**Run research** commissions capped passes across open threads against
the shared project pot — up to `orchestration_concurrency` at a time, each
holding a reserved slice so they cannot oversell — and stops when the budget
is exhausted, no raisable claims remain, or a member cancels. **A continuous campaign shipped in `0.25.0` / `0.32.0`:** Start on Overview
re-commissions that orchestrator until the pot is empty, no raisable work
remains, the cycle cap is hit, or a member stops it — up to
`campaign_cycle_concurrency` cycles at a time (default 1 = sequential)
against the same reservation lock. Still an in-process
BackgroundTask (a lost worker is swept honestly; not a durable queue).
**Project-budget metering shipped in `0.19.0`** (historical alias `0.12.5`):
agent passes debit an append-only `ComputeDebit` ledger; `available` is a real
ceiling; per-pass safety caps still bound blast radius on top. Prod enablement
is still the ops flip `AGENT_LOOP_ENABLED=true` + the `OPENROUTER_API_KEY`
Fly secret.
The guiding constraint held throughout: every capability was human-usable through the
API *first*, so the agent simply uses what humans already could.

## Guiding principle (unchanged)

Build the smallest complete research workflow that records what changed, why it changed,
who changed it, and what evidence or artifacts were involved — then extend it without
bypassing the checkpoint chokepoint or conflating funder / contributor / validator roles.

## Recommended next releases

### `0.32.x` — Concurrent campaign cycles under project budget ✅ **shipped** (`0.32.0`)

Delivered: a `0.25.0` campaign may run a bounded number of `0.22.0`
orchestrations at once (`campaign_cycle_concurrency`, default 1; `1` is
sequential; hard-capped at 4). Cycle starts reuse the `0.27.0` project-row
reservation lock; live OpenRouter quotes (`0.28.0`) size the hold and the
debit. Trace records overlapping cycles, skips, and cancel. Same
`AGENT_LOOP_ENABLED` gate. One campaign per project still (`409`). Never
auto-validates, auto-funds, or auto-merges. Quiet "N cycles at a time" on
Overview. Migration `0021_concurrent_campaign_cycles` (additive). See
`docs/completions/concurrent-campaign-cycles-0.32.0.md`.

**Not in this release:** a durable job queue; auto-merge / auto-validate;
Mathlib expansion.

### `0.31.x` — Deepdive Phase D ✅ **shipped** (`0.31.0`)

Delivered: shareable Research deep links (`?tab=` + `?thread=` +
`?branch=`) restore selection with `router.replace`; unknown / malformed
ids degrade to defaults. A cross-tab "Pass running" cue on the strip and
CommandRail derives from the existing keep-alive newest-run flag — no
new fetch. **Rail-only nav:** no in-page sidecar (Phase B already gives
project-context nav). Historically the optional Phase D after
`0.14.0` / `0.24.0` / `0.30.0`. **No schema, no migration.** See
`docs/completions/deepdive-phase-d-0.31.0.md`.

**Not in this release:** a project-wide running light (other threads /
orchestrations / campaigns); an in-page sidecar.

### `0.30.x` — Deepdive Phase C polish ✅ **shipped** (`0.30.0`)

Delivered: compact header `n threads · n claims · n checkpoints`; Overview
keeps the full metric grid as reference; contested header items switch to
Research and focus that claim; tab badges from existing queries
(contested / member+invite / running-pass `LiveDot`); honest Instruments
sealed-line and no-thread copy. Historically the deferred Phase C
(`0.14.2`). **No schema, no migration.** See
`docs/completions/deepdive-phase-c-0.30.0.md`.

**Not in this release:** Phase D shipped separately as `0.31.0`. Semantic
diff remains `0.29.0`.

### `0.29.x` — Semantic git diff ✅ **shipped** (`0.29.0`)

Delivered: a derived ledger read compares two tips (checkpoint / branch /
tag / `main`) and returns a structured research-space delta — claims
added/removed/signal-changed, grounding-rung moves, instrument outcomes
on `from..to`, merge-base ancestry. Deterministic. Mints nothing. Quiet
Compare bay on Research. **No schema, no migration.** See
`docs/completions/semantic-diff-0.29.0.md`.

**Not in this release:** blame-as-an-op; LLM prose diffs; live OpenRouter
prices (shipped as `0.28.0`).

### `0.28.x` — Live OpenRouter price metering ✅ **shipped** (`0.28.0`)

Delivered: agent-pass `ComputeDebit` rows bill at the model's live OpenRouter
prompt / completion rates when `GET /models` is reachable (process cache,
short timeout). Missing key, timeout, fetch failure, or an unknown model
falls back to the configured blended `agent_token_rate_usd_per_1k` (or a
catalog `usd_per_1k` override) and records that fallback on the row —
metering is never skipped. Snapshot columns for the split and the rate
source. Reservation envelopes (`0.27.0`) use the same quote. Migration
`0020_compute_debit_live_rates` (additive). Rebased after shipped `0.27.0`.
See `docs/completions/live-openrouter-prices-0.28.0.md`.

**Not in this release:** per-replan extra debit rows (one debit per pass
still); a Redis price cache; changing funder ≠ contributor ≠ validator.

### `0.27.x` — Concurrent sub-passes under project budget ✅ **shipped** (`0.27.0`)

Delivered: the `0.22.0` orchestrator (and therefore each `0.25.0` campaign cycle)
can run a small number of `run_agent_pass` calls at once
(`orchestration_concurrency`, default 2; `1` is sequential). Before a pass
starts, a short critical section locks the project row and holds a slice of
`available` on the `AgentRun`. Debit stays after tokens; the hold cannot
oversell the pot. The trace records which threads ran in the same wave, skips,
and the stop reason (including cancel). Same `AGENT_LOOP_ENABLED` gate. Never
auto-validates, auto-funds, or auto-merges. Quiet concurrency status + Stop on
Overview. Migration `0019_concurrent_subpasses` (additive). See
`docs/completions/concurrent-subpasses-0.27.0.md`.

**Not in this release:** concurrent *campaign cycles* (shipped later as
`0.32.0`); a durable job queue; auto-merge / auto-validate; Mathlib expansion.

### `0.26.x` — Mathlib / lake Grade-A path ✅ **shipped** (`0.26.0`)

Delivered: `lean.prove` `mathlib=true` — a closed Mathlib import set typechecked
through a bounded offline `lake` project on the existing sandbox. Grade A /
`proven` only on kernel success. Missing Mathlib/`lake`, timeout, and banned
constructs are honest `undecided`. Optional image (`INSTALL_MATHLIB=1`); CI
does not install Mathlib. **No schema, no migration.** See
`docs/completions/lean-mathlib-0.26.0.md`.

**Not in this release:** Lean REPL / LeanDojo; a default-on Mathlib image.

### `0.25.x` — Continuous research under budget ✅ **shipped** (`0.25.0`)

Delivered: a `ResearchCampaign` repeatedly commissions the 0.22.0 orchestrator
against the shared `ComputeDebit` ceiling until budget / no-work / max cycles /
cancel / error budget. Same `AGENT_LOOP_ENABLED` dark-launch flag. Trace
records each cycle and why the campaign stopped. Never self-validates or
auto-merges. Quiet Start / Stop on Overview. Migration
`0018_research_campaigns`. See `docs/completions/continuous-research-0.25.0.md`.

**Not in this release:** a durable job queue; concurrent cycles (shipped
later as `0.32.0`); auto-merge. Mathlib / `lake` shipped separately as
`0.26.0`. CommandRail shipped as `0.24.0`.

### `0.24.x` — CommandRail sync ✅ **shipped** (`0.24.0`)

Delivered: the left rail's project zones are live `?tab=` links for the five
deepdive tabs; active state is derived from the URL, the same source as the
in-page strip. The `#funding` hash target and the inert Agents hatch are gone
(Agents mapped to no distinct surface — the agent pass is Instruments).
Historically the deferred Phase B (`0.14.1`). **No schema, no migration.** See
`docs/completions/commandrail-sync-0.24.0.md`.

### `0.23.x` — Lean 4 Grade-A path ✅ **shipped** (`0.23.0`)

Delivered: `lean.prove` — a bounded Lean 4 snippet typechecked by the optional
`lean` binary, through the existing killable sandbox. Grade A / `proven` only
when the kernel accepts the file and the source has no `sorry`/`axiom`/import/IO.
Missing toolchain and timeouts are honest `undecided`. Failed checks are not
refutations. **No schema, no migration.** No Mathlib / `lake` in v1. See
`docs/completions/lean-prove-0.23.0.md`.

### `0.22.x` — Thin multi-thread orchestrator ✅ **shipped** (`0.22.0`)

Delivered: a project-level loop selects open threads with raisable claims,
commissions capped sequential `run_agent_pass` calls against the shared
`ComputeDebit` ceiling, and stops on budget / no-work / `orchestration_max_passes`.
Same `AGENT_LOOP_ENABLED` dark-launch flag. Trace records which threads ran and
why others were skipped. Orchestrator never self-validates. Quiet **Run research**
on Overview. Migration `0017_orchestration_runs`. See
`docs/completions/multi-thread-orchestrator-0.22.0.md`.

**Not in this release (0.22.0):** concurrent sub-passes (shipped later as
`0.27.0`); auto-merge / auto-tag after a landed pass (`0.21.0` merge/tag stay
human/API ops). Continuous re-commission shipped as `0.25.0`.

### `0.21.x` — Research-git merge + tag ✅ **shipped** (`0.21.0`)

Delivered: parallel exploration lines can converge without rewriting history. A
merge is a new multi-parent checkpoint (source heads + target tip) that records
which branches and claims were combined and marks sources `merged`. A tag is a
named immutable pointer (`milestone` / `validated` / `retraction`); a colliding
name is `409`, never a silent overwrite. Workspace: Merge on the line bar, a
Tags bay on Research. Migration `0016_research_git_merge_tag` (additive). See
`docs/completions/research-git-merge-tag-0.21.0.md`.

**Not in this line:** ~~semantic diff~~ ✅ shipped as `0.29.0`; blame-as-an-op. `lean.prove` shipped as
`0.23.0` (prelude/Init). Mathlib / `lake` remain later. The multi-thread
orchestrator shipped as `0.22.0`.

### `0.20.x` — Plan → observe → replan ✅ **shipped** (`0.20.0`)

Delivered: a pass is no longer one planning call then deterministic execute. After each
instrument batch the orchestrator records observations and may replan, bounded by
`agent_pass_max_replans` / `agent_pass_max_batch_runs` / `agent_pass_max_runs`. The trace
shows every plan version and the observe summary that caused a replan. Failed/empty steps
still mint nothing. The planner stays on the fixed catalog. Human review stays opt-in.
**No schema, no migration.** `BudgetPolicy.check` is wired to the shipped `0.19.0`
project ceiling. See `docs/completions/plan-observe-replan-0.20.0.md`.

### `0.19.x` — Project-budget metering ✅ **shipped** (`0.19.0`)

Delivered: agent passes debit an append-only `ComputeDebit` ledger from recorded
planning tokens; `project_budget.spent` is the sum; `available` is a real ceiling.
Refuse to start when exhausted; skip remaining instrument runs mid-pass with
`budget_exhausted`. The agent never funds and never self-validates. Per-pass safety
caps unchanged. Migration `0015_compute_debits` (additive). Historical alias
`0.12.5`. See `docs/completions/project-budget-metering-0.19.0.md`.

**Natural follow-ons:** ~~the orchestrator that allocates project budget across
subagents~~ ✅ shipped as `0.22.0`; ~~live OpenRouter prices instead of the
blended `agent_token_rate_usd_per_1k` default~~ ✅ shipped as `0.28.0`.
Plan→observe→replan shipped in `0.20.0`.

### `0.17.x` — Phase 1 agent autonomy ✅ **shipped** (`0.17.0`)

Delivered: a completed pass's attributed checkpoints stand without a mandatory human gate.
`requires_review` is a computed `false` on the `AgentRun` read model; `AgentRunStatus` has no
`awaiting_review`; the trace copy is driven by that field. Accept / reject / fork remain the
shipped Validation and Branch write paths. **No schema, no migration.** Safety caps unchanged.
See `docs/completions/agent-autonomy-0.17.0.md`.

**Natural follow-ons:** ~~`0.12.5` / `0.19.0` project-budget metering~~ ✅ shipped;
~~plan→observe→replan within a pass~~ ✅ shipped as `0.20.0`; ~~the orchestrator
that allocates project budget across subagents~~ ✅ shipped as `0.22.0`.

### `0.16.x` — Claim grounding ✅ **shipped and hardened** (`0.16.0`–`0.16.3`)

Delivered: the `(instrument, status)` grade matrix beside the registry (with the conformance harness
now *forcing* a grading decision on every registered instrument), the batch-loaded `ClaimGrounding`
read model, and the grade chip + raise line on the claim row. Pure read-model derivation — no
migration, table, column, or endpoint; `compute_signal` untouched.

**The open follow-ons are the payoff the ladder exists for:**

- ~~**`0.16.1` — grounding into the planner + budget**~~ ✅ **shipped**. The planner now receives
  each open claim's rung plus a matrix-derived raise path (and a *settled* stop line), and every
  completed pass records what it moved (`AgentRun.grounding_yield`, migration `0014`). The loop is
  judged on yield, not activity. **`BudgetPolicy` now has its implementer in `0.19.0`**
  (historical `0.12.5`); the recorded yield is what metering reads beside the debit.
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

### `0.14.x` / `0.24.0` / `0.30.0` / `0.31.0` — Project deepdive tabs ✅ **Phase A–D shipped**

Delivered in `0.14.0`: the five-tab shell with `?tab=` as the single source of truth, the
persistent header, keep-alive Research/Instruments mounting (load-bearing for the agent poll),
the WAI-ARIA tabs pattern, and the `<Suspense>` boundary.

Delivered in `0.24.0` (historical alias `0.14.1`): CommandRail sync. Project zones are live
`?tab=` links; active state is derived from the URL; the `#funding` hash target and the inert
Agents hatch are gone. See `docs/completions/commandrail-sync-0.24.0.md`.

Delivered in `0.30.0` (historical alias `0.14.2`): Phase C polish. Contested click-through,
tab badges, compact metric line, Instruments readout. See
`docs/completions/deepdive-phase-c-0.30.0.md`.

Delivered in `0.31.0`: Phase D. Shareable `?thread=` / `?branch=` Research deep
links; strip + CommandRail live cue from keep-alive newest-run state; rail-only
nav recorded (no sidecar). See `docs/completions/deepdive-phase-d-0.31.0.md`.
Checklist in `docs/archive/project-deepdive-tabs-0.14.md` §6:

- ~~**Phase B (`0.14.1` / `0.24.0`)**~~ ✅ **shipped** — rail ↔ strip sync via `?tab=`.
- ~~**Phase C (`0.14.2` / `0.30.0`, polish)**~~ ✅ **shipped** — contested click-through,
  tab badges, compact metric line, Instruments readout.
- ~~**Phase D (`0.31.0`, optional)**~~ ✅ **shipped** — `?thread=` / `?branch=` deep
  links, cross-tab in-flight indicator, rail-only nav decision (no sidecar).

### Tier 1 retrieval wave — literature pin instruments ✅ **shipped** (`0.18.0`)

Delivered: `crossref.lookup`, `arxiv.lookup`, and `openalex.lookup` on the proven `source.pin`
shape — DOI / versioned arXiv id / OpenAlex id land as attributed checkpoints through
`run_instrument`, with `url` + `source_url` + `retrieved_at` + `raw_response_hash`. Network
failures mint nothing; a successful empty match is honest `undecided`. OpenAlex does **not**
hard-require a prod secret: optional `OPENALEX_API_KEY`, demo-pool degrade when absent (the
polite-pool `mailto` was retired Feb 2026; a key is the real quota). See
`docs/completions/literature-pin-instruments-0.18.0.md`.

### `0.12.x` — Thin agent loop ✅ **shipped** (`0.12.0`–`0.12.4`)

Delivered: a bounded pass (planner → capped instrument runs on a durable agent branch through the
same chokepoint), a request-scoped `202` + background execution, the pollable `AgentRun` trace, and
the workspace trigger/trace UI, and **`0.17.0` made review opt-in**. **`0.19.0` (historical
`0.12.5`) shipped project-budget metering** — agent passes debit `ComputeDebit`; the
per-pass safety caps (`agent_pass_max_runs`, token cap) still bound blast radius on top.
The prod light-up step is **both** `AGENT_LOOP_ENABLED=true` **and** the
`OPENROUTER_API_KEY` Fly secret (`fly secrets set`, never `fly.toml [env]`) — one without
the other is not a launch. Flag off ⇒ every agent route `404`s.

**Natural follow-ons (pick per demand):** ~~project-budget metering~~ ✅ shipped as
`0.19.0`; ~~an iterative plan→observe→replan within a pass~~ ✅ shipped as `0.20.0`;
~~the orchestrator that allocates project budget across subagents~~ ✅ shipped as
`0.22.0`.

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

- ~~`z3.satisfy` — model-finding as the primary output.~~ ✅ shipped as `0.33.0`.
- ~~Boolean connectives / `bool` sort (needs a parser beyond `split_relation`).~~ ✅ shipped as `0.38.0`.
- Quantifiers; full replayable proof terms (out of scope for v1).
- **Lean + Mathlib** (Tier 2 remainder) — `lean.prove` shipped in `0.23.0`
  (prelude / `Init`) and `0.26.0` (optional Mathlib / offline `lake`). REPL /
  LeanDojo are still later.

### `0.35.x` — `interval.eval` ✅ **shipped** (`0.35.0`)

Delivered: proven numeric enclosures via `python-flint` / Arb (mpmath.iv
fallback). `result` is Grade C (a bound, not a proof); a definitive miss
is `refuted` / B; overlap / timeout / domain is honest `undecided`.
Never Grade A from an interval alone. Re-spec'd from `maths-toolbox.md`
after the old falsify-and-render appendix B was removed. **No schema, no
migration.** Sits on `0.34.0`. See
`docs/completions/interval-eval-0.35.0.md`.

**Not in this release:** Lean REPL / LeanDojo; boolean Z3 parser
(later `0.38.0`); blame-as-an-op; browser eyeball.

### `0.36.x` — Research-git blame ✅ **shipped** (`0.36.0`)

Delivered: a derived ledger read walks the checkpoints, actors, and
tool invocations that produced or evidence-grounded a claim
(`GET /projects/{id}/claims/{claim_id}/blame`). Deterministic. Mints
nothing. Quiet Blame bay next to Compare on Research. **No schema, no
migration.** Sits on `0.35.0`. See
`docs/completions/research-git-blame-0.36.0.md`.

**Not in this release:** merging this PR; Lean REPL / LeanDojo;
auto-validate / auto-fund / auto-merge; content-addressed commit ids;
rewriting claim field history; browser eyeball.

### `0.36.3` — Honesty polish ✅ **this branch**

Delivered: `BranchCreate` / `ValidationCreate` OpenAPI copy describes
the signed-in JWT actor, not the local-only header; the planner prompt
prints `compute_signal` instead of stored `Claim.status`. Auth
assistant/ops copy matches. **No schema, no migration.** Off `main`
(`0.36.0`). Does not claim `0.36.1` / `0.36.2` / `0.37.0` / `0.38.0`.
See `docs/completions/honesty-polish-0.36.3.md`.

**Not in this release:** membership gating; planner open-claim filter
rewrite; Lean / Z3 expansion; browser eyeball.
### `0.37.x` — GitHub Actions CI with Postgres ✅ **shipped** (`0.37.0`)

Delivered: `.github/workflows/ci.yml` runs `ruff` + `pytest` against a
throwaway Postgres 16 service (`TEST_DATABASE_URL` so the DB-gated
suite actually runs) and frontend `typecheck` / `lint` / `test` /
`build` on every pull request and push to `main`. Lean / Mathlib stay
off. No secrets. Infra only — **no schema, no migration.** Sits on
`0.36.0`. See `docs/completions/github-actions-ci-0.37.0.md`.

**Not in this release:** Lean / Mathlib in CI; `0.36.1` / `0.36.2`;
changing branch protection.

### Deferred / deprioritized

| Item | Notes |
|---|---|
| **`0.5.0` demo seeding** | Plan doc since removed; team preference is **no seed data** — projects start from scratch. Revisit only if empty-state UX becomes a product problem. |
| **`formula.render` instrument** | Superseded for v1 by additive `*_latex` + KaTeX in `formula.tsx` (`0.10.4`–`0.10.5`). |
| **Tables / plots (`table.*`, `plot.*`)** | ~~Bench 6~~ ✅ shipped as `0.34.0`. Plots remain optional viz, never Grade A. |
| **Real funding / settlement** | `FundingAllocation` is recorded; Stripe etc. remain future. |
| **Reputation / influence** | Vision doc; no data model yet. |
| **Object storage for large artifacts** | Blobs stay off Postgres; upload path not built. |

## Priority order (from here)

1. ~~**Execution sandbox** (`0.11.x`)~~ ✅ shipped.
2. ~~**Thin agent loop** (`0.12.x`)~~ ✅ shipped — Research crew is now a bounded operator.
3. ~~**Z3 instrument** (`0.13.x`)~~ ✅ shipped — first machine-checked proof path (`z3.prove`).
4. ~~**Z3 write-path tests**~~ ✅ closed in `0.13.5` alongside the review-pass hardening.
5. ~~**Deepdive tab shell** (`0.14.0`)~~ ✅ shipped — Phase A; ~~Phase B~~ ✅ shipped as
   `0.24.0` (item 11); ~~Phase C~~ ✅ shipped as `0.30.0` (item 13);
   ~~Phase D~~ ✅ shipped as `0.31.0` (item 14).
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
10. ~~**Tier 1 retrieval** — literature pin instruments (Crossref / arXiv / OpenAlex)~~ ✅
    shipped in `0.18.0` on the proven `source.pin` shape. OpenAlex degrades without a key.
11. ~~**`0.14.1` / `0.24.0` Phase B** — CommandRail sync~~ ✅ shipped — live `?tab=`
    zones; `#funding` and the inert Agents hatch retired.
12. ~~**`0.12.5` / `0.19.0` project-budget metering**~~ ✅ shipped — debit the project's
    compute budget per pass. Per-pass safety caps still bound a single pass. See
    `docs/completions/project-budget-metering-0.19.0.md`.
    ~~**`0.20.0` plan → observe → replan**~~ ✅ shipped on the same loop.
    ~~**`0.21.0` research-git merge/tag**~~ ✅ shipped.
    ~~**`0.29.0` semantic git diff**~~ ✅ shipped.
    ~~**`0.36.0` research-git blame**~~ ✅ shipped.
    ~~**`0.22.0` multi-thread orchestrator**~~ ✅ shipped — sequential sub-passes
    under the shared project pot.
    ~~**`0.25.0` continuous research under budget**~~ ✅ shipped — re-commission
    the orchestrator until the pot is empty or no raisable work remains.
    ~~**`0.32.0` concurrent campaign cycles**~~ ✅ shipped — bounded
    in-campaign cycle waves under the same reservation lock.
13. ~~**`0.14.2` / `0.30.0` Phase C**~~ ✅ shipped — tab badges, contested
    click-through, context-readout polish. See
    `docs/completions/deepdive-phase-c-0.30.0.md`.
14. ~~**`0.31.0` Phase D**~~ ✅ shipped — shareable Research deep links,
    cross-tab live cue, rail-only nav (no sidecar). See
    `docs/completions/deepdive-phase-d-0.31.0.md`.
15. ~~**Bench 6 surfaces**~~ ✅ shipped as `0.34.0` — `table.create` /
    `table.derive_column` / `table.render` / `plot.function` / `plot.points`.
    Plots are optional viz; tables are the falsification grid.
16. ~~**Lean Grade-A path**~~ ✅ shipped as `0.23.0` (`lean.prove`, optional
    toolchain, prelude/Init) and `0.26.0` (Mathlib / offline `lake` opt-in).
    **REPL / LeanDojo** remain later.
17. ~~**`z3.satisfy` model-finding**~~ ✅ shipped as `0.33.0` — sat → concrete
    model; unsat → honest no-model; unknown/timeout → undecided.
    ~~Boolean connectives / `bool` sort~~ ✅ shipped as `0.38.0`.
    Quantifiers remain later.
18. ~~**`interval.eval` proven enclosures**~~ ✅ shipped as `0.35.0` — Arb
    ball / mpmath.iv fallback; Grade C support, B on a definitive miss;
    never A. Overlap is honest `undecided`.
19. ~~**Research-git blame**~~ ✅ shipped as `0.36.0` — derived claim
    provenance read; mints nothing; not an instrument.
20. ~~**GitHub Actions CI with Postgres**~~ ✅ shipped as `0.37.0` —
    the contribution contract on every PR, with the DB-gated suite
    actually running. Lean / Mathlib stay off.

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
| `0.14.x` | Project deepdive — persistent header + five `?tab=` tabs, keep-alive agent trace; CommandRail sync shipped as `0.24.0`; Phase C polish shipped as `0.30.0`; Phase D deep links shipped as `0.31.0` |
| `0.15.x` | Quiet-minimalist re-skin — neutral near-black system, ornament retired |
| `0.16.x` | Claim grounding — the evidence grade ladder, derived beside the validation signal, consumed by the planner as a yield measure, post-review hardened, and rolled up at thread/project scale (`0.16.3`) |
| `0.17.x` | Phase 1 agent autonomy — a completed pass stands; human accept/reject/fork is opt-in audit |
| `0.18.x` | Tier-1 literature pins — `crossref.lookup`, `arxiv.lookup`, `openalex.lookup` on `source.pin` |
| `0.19.x` | Project-budget metering — `ComputeDebit` from agent-pass tokens; funding `spent`/`available` are real (historical `0.12.5`) |
| `0.20.x` | Bounded plan → observe → replan inside one agent pass |
| `0.21.x` | Research-git merge + tag — multi-parent synthesis and named immutable pointers |
| `0.22.x` | Thin multi-thread orchestrator — allocate project budget across sequential sub-passes |
| `0.23.x` | `lean.prove` — optional Lean 4 kernel check; Grade A only on a real proof (prelude / Init) |
| `0.24.x` | CommandRail sync — rail zones are live `?tab=` links; `#funding` + inert Agents retired (historical `0.14.1`) |
| `0.25.x` | Continuous research campaign — re-commission the 0.22.0 orchestrator under the project pot |
| `0.26.x` | `lean.prove` Mathlib opt-in — bounded offline `lake`; Grade A only on a real kernel + allow-list success |
| `0.27.x` | Concurrent sub-passes under the shared project budget — reserved slices, no oversell |
| `0.28.x` | Live OpenRouter price metering — `ComputeDebit` at prompt/completion rates, honest blended fallback |
| `0.29.x` | Semantic git diff — structured claim / grounding / instrument delta between two tips |
| `0.30.x` | Deepdive Phase C polish — contested click-through, tab badges, compact metric line (historical `0.14.2`) |
| `0.31.x` | Deepdive Phase D — shareable Research `?thread=` / `?branch=`, cross-tab live cue, rail-only nav |
| `0.32.x` | Concurrent campaign cycles under the shared project budget — reserved slices, no oversell |
| `0.33.x` | `z3.satisfy` — model-finding (sat assignment / unsat no-model / honest undecided) |
| `0.34.x` | Bench 6 tables & plots — typed grids, derived columns, Vega-Lite specs (not rasters) |
| `0.35.x` | `interval.eval` — proven numeric enclosures (Arb / mpmath.iv; never Grade A alone) |
| `0.36.x` | Research-git blame — derived checkpoint / actor / instrument chain for a claim |
| `0.38.x` | Boolean connectives + `bool` sort on `z3.prove` / `z3.satisfy` |
| `0.37.x` | GitHub Actions CI with Postgres — ruff / pytest (DB-gated) + frontend typecheck/lint/test/build |

## Success criteria for the next milestone

**`0.19.0` (project-budget metering)** is shipped: agent passes debit an append-only
`ComputeDebit` ledger; `project_budget.spent` / `available` are real; an exhausted
project refuses to start. Historical alias `0.12.5`. Per-pass safety caps unchanged.

**`0.20.0` (plan → observe → replan)** is shipped: a pass replans from instrument outcomes
and grounding yield, under hard caps, with each plan version visible on the trace.

**`0.21.0` (research-git merge + tag)** is shipped: a merge is a multi-parent
checkpoint that marks sources `merged`; a tag is a named immutable pointer;
neither rewrites history.

**`0.22.0` (multi-thread orchestrator)** is shipped: a project-level loop commissions
capped sequential passes across open threads against the shared `ComputeDebit`
ceiling, and stops when the pot is empty or no raisable work remains.

**`0.23.0` (Lean Grade-A path)** is shipped: `lean.prove` can raise a claim to
Grade A when the optional `lean` binary typechecks a prelude snippet. Missing
Lean is honest `undecided`. Mathlib is not in this release.

**`0.24.0` (CommandRail sync)** is shipped: project rail zones navigate via
`?tab=` and share active state with the in-page strip. Historical alias
`0.14.1`. The `#funding` hash and the inert Agents hatch are gone.

**`0.25.0` (continuous research under budget)** is shipped: a campaign
re-commissions the 0.22.0 orchestrator until the project pot is empty, no
raisable work remains, the cycle cap is hit, or a member cancels. Same
`AGENT_LOOP_ENABLED` flag. Merge / tag stay human.

**`0.26.0` (Mathlib / lake Grade-A path)** is shipped: `lean.prove` can raise
a claim to Grade A with Mathlib when the optional `lake` cache is present.
Missing Mathlib is honest `undecided`. REPL / LeanDojo are not in this release.

**`0.27.0` (concurrent sub-passes)** is shipped: the orchestrator can run a
capped number of `run_agent_pass` calls at once against the shared
`ComputeDebit` pot. A reservation hold prevents oversell; debit stays after
tokens. `concurrency=1` is sequential. Campaigns inherit the inner
concurrency. Never auto-validates or auto-funds.

**`0.28.0` (live OpenRouter price metering)** is shipped: agent passes debit
at the model's live prompt/completion rates when the price catalog answers,
and fall back to the configured blended rate with that fallback recorded.
Reservation envelopes use the same quote. Rebased after `0.27.0`.

**`0.29.0` (semantic git diff)** is shipped: two ledger tips compare as a
structured research-space delta. Deterministic. Mints nothing. Blame is
not in this release.

**`0.30.0` (deepdive Phase C polish)** is shipped: contested header items
land on that claim in Research; tab badges reuse existing reads; the
header metric line and Instruments readout are finalized. Historical
alias `0.14.2`. Frontend-only.

**`0.31.0` (deepdive Phase D)** is shipped: `?thread=` / `?branch=` restore
Research selection; a keep-alive live cue shows on the strip and
CommandRail while a pass runs; nav stays rail-only (no sidecar).
Frontend-only.

**`0.32.0` (concurrent campaign cycles)** is shipped: a continuous
campaign may run a bounded number of orchestrations at once against the
shared pot. `concurrency=1` is sequential. Reservation holds prevent
oversell; debit stays after tokens at the live/fallback quote. Never
auto-validates or auto-funds.

**`0.33.0` (`z3.satisfy`)** is shipped: model-finding as a first-class
instrument. `sat` lands a concrete model; `unsat` is an honest no-model
(`refuted`); timeout / `unknown` is `undecided`. Boolean connectives
shipped later as `0.38.0`. Quantifiers remain later. Lean REPL /
LeanDojo remain later.

**`0.34.0` (Bench 6 tables & plots)** is shipped: typed tables, a computed
column with calc-spine honesty, a render artifact, and Vega-Lite specs
for `y = f(x)` and point lists. Plots are optional viz and never Grade A.
`formula.render` is not reintroduced. No migration. Sits on `0.33.0`.

**`0.35.0` (`interval.eval`)** is shipped: a closed-form real expression
evaluates to a proven `[lo, hi]`. Supporting enclosure is Grade C;
a definitive miss is `refuted` / B; overlap / timeout is `undecided`.
Never Grade A from an interval alone. Sits on `0.34.0`.

**`0.38.0` (Z3 boolean connectives)** is shipped: `z3.prove` /
`z3.satisfy` accept `And` / `Or` / `Not` / `Implies` / `Xor` /
`Equivalent` and a `bool` sort on the existing InputModel. Grade A
only on a real Z3 success; vacuous hypotheses stay undecided.
Quantifiers are not in this release. Does not claim `0.36.1` /
`0.36.2` / `0.37.0`.

**Next product step:** the still-owed browser eyeball pass.
Quantifiers on Z3 remain later. Lean REPL / LeanDojo remain later.
