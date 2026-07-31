# 0.16.0 — Claim grounding: the evidence grade ladder

**Goal.** Make a claim's **grounding** — how strongly it is backed by *what actually ran* — a
derived, first-class part of the claim read model, so `primitives.md`'s promise (*"confidence
explainable through evidence and validation history, not a naked score"*) becomes true of the
**evidence** half, not just the validation half.

**Shape.** Backend read-model derivation + frontend surface. **No migration, no new table, no new
column, no new endpoint.** Implements `docs/completions/claim-grounding-0.16-plan.md` Phases 1–3;
Phase 4 (planner + budget consumption) was explicitly out of scope and remains so.

## Why

`services/claims.py::compute_signal` derived a claim's display signal from `list[ValidationRead]`
— **validations only**. The consequence, live in production until this release:

> A claim carrying a `z3.prove` machine-checked proof and a claim carrying nothing but an LLM's
> opinion both read `signal: "none"` until a human clicked *validate*.

Six instruments were manufacturing graded results and nothing consumed the grade. The platform's
flagship capability — machine-checked truth — was invisible to the surface that exists to express
confidence.

It also gates the autonomy spine. An agent loop needs a *state to plan against*, a *progress
measure*, and a *stopping criterion*; all three are the same missing object. The `0.12.1` planner
receives *thread + open claims + catalog* — it can see **that** a claim is open, never **how well
grounded** it is. Building continuous autonomy before this yields an expensive random walk; shipping
`0.12.5` budget metering before it meters spend with no notion of yield.

Per the standing rule (*anything an agent will do, a human should be able to do first*), this pays
off without agents: a human working the flagship *measuring across a corner* thread now watches
claims 1–4 read B with claim 5 visibly the only rung left.

## The two-axis design (the load-bearing constraint)

`signal` (validation-derived) and `grounding` (evidence-derived) are **two separate axes shown side
by side**. They are never merged, never combined arithmetically, and are rendered as
differently-shaped elements. A single blended number would recreate exactly the "naked score"
`primitives.md` forbids. `compute_signal` was not touched.

## The grading matrix (the actual domain decision)

Grade is a function of **`(instrument, status)`** — *not* instrument alone. That is the subtlety
that makes the ladder honest: `counterexample.search` returning `refuted` produced an *exact
witness* and settles a universal negatively (**B**), while the same instrument returning `result` is
finite sampling that settles nothing (**C**). The `0.9.6` / `0.9.9` honesty work made those status
distinctions rigorous; this table consumes them at the same resolution rather than flattening them.

| Instrument | `result` | `refuted` | `undecided` |
|---|---|---|---|
| `z3.prove` | **A** machine-checked proof | **A** machine-checked counter-model | *none* |
| `expr.compare` | **B** exact symbolic equivalence | **B** provably non-zero difference | *none* |
| `calc.eval` | **B** exact evaluation | **B** exact false relation | *none* |
| `geometry.coordinate_measure` | **B** exact measurement | *n/a — never refutes* | *none* |
| `counterexample.search` | **C** finite grid, weak support | **B** definitive exact witness | *none* |
| `oeis.search` | *cited* (off-ladder) | *n/a* | *none* |
| *no instrument in the chain* | **D** human-asserted | — | — |

**Aggregation** (`support` = strongest over `support` links, `counter` = strongest over `weaken`
links, `context` feeds neither). **Display precedence:** an A/B `counter` → `refuted` (dominates any
support); `support` A → `proven`; `support` B/C/D → that letter; else `cited`; else `ungrounded`.

## What changed, where, how, why

### Phase 1 — the derivation (pure; no DB, no API)

- **`backend/app/models/enums.py`** — `+ class EvidenceGrade(StrEnum)` (`A`/`B`/`C`/`D`). A plain
  `StrEnum`, **not** a named Postgres type, following the exact `ResultStatus` precedent: promotion
  is deferred until (and only if) it ever becomes a column, and it never does here (D2). The
  docstring carries the "derived, never stamped" rationale and the "D is the absence of a tool, not
  a failure" rule, so the meaning travels with the type.

- **`backend/app/toolbench/grading.py`** (**new**) — the matrix plus three pure functions.
  - `grade_for(instrument, status) -> EvidenceGrade | None`.
  - `strongest(grades)` — the `A > B > C > D` ordering, via an explicit `_RANK` table. **Not**
    `max()`: `EvidenceGrade` is a `StrEnum`, so a naive `max()` sorts lexicographically and returns
    `"D"` — the *weakest* rung. A named test (`test_strongest_is_not_lexicographic`) pins this,
    because it is a silent, plausible-looking bug that would understate every graded claim.
  - `grading_problems(name)` — the D4 coverage check, shaped like `check_conformance` (a list of
    human-readable problems, not an exception) so the harness can fold it into its own report.
  - Lives **beside the registry, not in `services/`**, and imports nothing from `services/`: adding
    an instrument must force a grading decision at the point the instrument is defined.
  - Every instrument declares all three statuses; `None` is always an **explicit** cell, never an
    omission — so `geometry.coordinate_measure`'s "never refutes" is a recorded decision rather than
    a gap. The module docstring carries honesty rules 1–3 verbatim, including the forward-looking
    rule 3 warning against a "float → B" rule when SciPy lands.

- **`backend/app/toolbench/conformance.py`** — `+ require_grading: bool = False` on
  `check_conformance`, which appends `grading_problems(name)`.
  - *Why opt-in:* the harness is also run against `demo.echo`, a test-only fixture with no business
    in a production matrix. Making it always-on would have forced a fake matrix row for a fixture.
  - *Where it bites:* `tests/toolbench/test_conformance.py`'s auto-coverage test — the one
    parametrized over the **production** `registry.all()` — now passes `require_grading=True`. So a
    newly registered instrument with no matrix row fails immediately, which is what D4 asks for,
    while throwaway fixtures are unaffected.
  - Placed *before* the harness's early returns, so a missing grade is reported even when the rest
    of the instrument is not exercisable.

- **`backend/app/toolbench/__init__.py`** — exports `grade_for` / `grading_problems` / `strongest`.

### Phase 2 — traversal + read model

- **`backend/app/schemas/claim.py`** — `+ GroundingHeadline` (a `Literal`) and
  `+ class ClaimGrounding` (`support`, `counter`, `cited`, `headline`); `ClaimRead` gains
  `grounding: ClaimGrounding`.
  - `headline` is computed **server-side** as a *discriminant*, not copy (plan §8 Q2): the
    precedence rules stay in one testable place, and every user-facing string stays on the client.
  - Constructed explicitly in the service, never via `from_attributes` — the same rule `signal`
    already lived under, which exists to stop a lazy-load of an ORM relationship.

- **`backend/app/services/grounding.py`** (**new**) — the traversal and aggregation.
  - `grounding_by_claim(db, claim_ids)` — **one** query joining `ClaimEvidenceLink → Evidence`,
    reading `relation_kind`, `source_type`, and `evidence_metadata`, then aggregating in Python.
    Batch-loaded exactly like `validations_by_claim` (the `0.4.4` no-N+1 constraint).
  - `compute_grounding(links)` is split out of the loader **specifically so the rules are testable
    without a database** — see the verification note below on why that mattered here.
  - **Reads `Evidence.evidence_metadata`, not the blame tuple** (D3, accepted denormalization R2).
    The authoritative record remains the `ToolInvocation` on the append-only `Checkpoint`, but it
    rides as JSON inside a blob; reaching it per claim would mean walking
    `CheckpointRef → Checkpoint → tool_invocations[] → produced_artifact_id → EvidenceArtifactLink`.
    `tool_runs.py` writes both in the same transaction and nothing else writes either, so the copy is
    correct by construction. Recorded in the module docstring, with the stated remedy for any
    observed divergence: read the blame tuple, never stamp a grade.

- **`backend/app/services/claims.py`** — `_to_read(claim, validations, grounding=None)`; the three
  call sites updated. `create_claim` passes nothing (a fresh claim has neither validations nor
  evidence links, so **no** query is issued for either); `list_claims` and `get_claim` batch-load.

- **`backend/app/services/projects.py`** — **verified unchanged and correct.** `_contradictions`
  calls `compute_signal` directly against `Claim` rows and never builds a `ClaimRead`, so the
  project-overview path issues no new queries. No N+1 regression (plan Phase 2 step 4's ask).

### Phase 3 — the surface

- **`frontend/src/types/research.ts`** — `+ EvidenceGrade`, `+ GroundingHeadline`,
  `+ ClaimGrounding`; `Claim` gains `grounding`.

- **`frontend/src/components/workspace/grounding-chip.tsx`** (**new**) — `GroundingChip` plus
  `groundingRaiseLine`, a `Record<GroundingHeadline, …>` so adding a headline is a type error until
  it is styled and captioned.
  - **Shape**: a mono letter in a small square tile beside a sans label. Deliberately *not* a
    `StatusPill` — the validation signal a few lines below **is** a `StatusPill`, and R3 requires the
    two axes to be distinct, adjacent, differently-shaped elements. A shared component would have
    let them read as one score.
  - **Crimson `--signal` is reserved for `refuted`, not `--state-fail`.** A refutation is a
    successful, valuable research outcome; spending the deeper error red (`#C4403A`) on it would make
    the bench doing its job look like something breaking. `proven`/`B` take the pass tone, `C` amber,
    `D` and `ungrounded` stay muted — **never alarming**, per honesty rule 2.
  - **The "what would raise this" line** is the point of the feature, not decoration: it turns a
    rung into an instruction (`B → "An exact result; a proof would settle it."`). `refuted` resolves
    its copy from the `counter` grade, because a machine-checked counter-model and an exact
    counterexample are not the same claim about rigor.
  - `undecided` cannot reach this component at all — it earns no grade server-side, so an escalation
    seam can never render as a weak pass.

- **`frontend/src/components/workspace/claim-list-panel.tsx`** — the chip inline on the claim's meta
  row (plan §8 Q1: inline, since scanning the ladder down a thread is the point), with the raise
  line beneath it.

- **`frontend/src/app/styleguide/page.tsx`** — the chip in **all nine** states it can read as,
  including the two easy-to-get-wrong ones: a B/C counter that does *not* refute, and a citation
  riding alongside a computed rung.

### Cache invalidation — a real gap this release opened

`ToolbenchPanel` and `AgentRunTrace` invalidated `checkpoints` / `overview` / `branches` / `evidence`
after a run, but **not** `queryKeys.claims(threadId)`. Before this release that was harmless: a tool
run changed nothing in the claim read model. It does now — a run against a claim moves its grounding
— so without this the chip would sit stale until a manual refresh and the feature would look broken.

- **`toolbench-panel.tsx`** — invalidates `claims(threadId)` when a run targeted a claim.
- **`agent-run-trace.tsx`** — invalidates `claims(run.thread_id)` on the `running → terminal`
  transition. `AgentRunRead` already carries `thread_id`, so no prop threading was needed.

## Deviations from the plan, and why

1. **`cited` requires a *decided* outcome.** §3.1 says `cited` is *"any link whose
   evidence.source_type is external"*. An `oeis.search` that matches nothing returns `undecided` — a
   real pin of a *non-match*. Counting it would lift a claim's headline from `ungrounded` to
   `cited`, i.e. let a failed lookup read as a weak pass, which is exactly what honesty rule 1
   exists to prevent. `_is_live_pin` therefore also requires a non-`undecided` status. The pin is
   still recorded and still citable; it just does not raise the rung. **Revert point:** drop the
   status check in `_is_live_pin` and `test_a_failed_lookup_is_not_a_citation`.

2. **`cited` also requires an `instrument` key.** Otherwise a human typing `source_type: "paper"`
   into the attach-evidence form would be promoted from Grade D to `cited`, making the ladder
   trivially gameable from the UI and contradicting honesty rule 2. `cited` means *a retrieval
   instrument landed a pin* (url + retrieved_at + response hash).

3. **`None` from the matrix never falls through to Grade D.** D asserts *"a human said so"*, which
   would be a false statement about a row a tool actually produced. So the read model branches on
   *"is there an `instrument` key at all"* first; only the no-instrument branch reaches D. An
   `undecided` run, a retrieval outcome, and a stale/unknown instrument all contribute **nothing**.

4. **`tests/test_grounding.py` is an addition** (not in the plan's file map). The plan put Phase 2's
   coverage in `test_read_models.py`, which is DB-gated. With no local Postgres this project runs
   against (see verification below), that would have shipped the entire aggregation and precedence
   logic unexecuted. Splitting `compute_grounding` out and testing it DB-free means the rules — the
   part where a wrong *epistemic* call hides — are actually verified.

5. **Cache invalidation** (above) — not in the plan's file map, but Phase 3 is not done if the chip
   does not update after a run.

## Verification

```bash
cd backend && uv run ruff check .          # clean
cd backend && uv run pytest -q             # 282 passed, 126 skipped (DB-gated)
cd frontend && npm run typecheck           # clean
cd frontend && npm run lint                # clean
cd frontend && npm run build               # clean, 9/9 static pages
```

New tests: **36** in `test_grading.py` (every matrix cell parametrized, the three honesty rules,
D4 coverage), **20** in `test_grounding.py` (aggregation + precedence + the defensive fallbacks),
**8** DB-gated in `test_read_models.py`, and `test_conformance.py`'s production auto-coverage now
runs with `require_grading=True`.

The D4 exit criterion was verified **literally**, not just by proxy — deleting `z3.prove`'s matrix
row makes `check_conformance(z3, require_grading=True)` report *"has no entry in the grade matrix"*,
and removing a single `refuted` cell reports the missing status by name.

The API contract was verified DB-free off the generated OpenAPI: `ClaimRead.grounding` `$ref`s
`ClaimGrounding`, whose `headline` enum is exactly the seven-member union.

### Unverified — read this before treating the line as prod-hardened

- **The 8 DB-gated round-trips in `test_read_models.py` have not been run.** This project verifies
  against the live deployment and keeps no local Postgres; the DB fixtures `DROP SCHEMA`, so they
  must never point at the live database. They collect cleanly and skip. To run them:
  `TEST_DATABASE_URL=postgresql+asyncpg://… uv run pytest tests/test_read_models.py`.
  What they alone would prove is that the `ClaimEvidenceLink → Evidence.evidence_metadata` chain the
  read model traverses is what the write path actually lays down. The *rules* over that chain are
  covered DB-free; the *shape* of the chain was confirmed by reading `tool_runs.py:243–280`.
- **No pixel-level browser walk.** The Chrome extension was not connected — the same blocker
  `0.14.0` and `0.15.0` recorded. What *was* checked: the styleguide serves 200, all nine chips
  render, each headline resolves to a **distinct mark + label** pair (the property grayscale survival
  depends on), and all eight raise lines are distinct. **Still owed:** the grayscale emulation pass
  and a look at a real claim row in the deepdive.
- **The flagship B/B/B/B walkthrough** (Phase 3's exit) is asserted as a unit test over the matrix,
  not driven through the live app.

## Acceptance criteria

| # | Criterion | Status |
|---|---|---|
| 1 | A `z3.prove` proof + zero validations reads `proven` | ✅ unit; DB test written, unrun |
| 2 | An exact witness reads `refuted` over three supporting runs | ✅ unit; DB test written, unrun |
| 3 | An `undecided` run changes nothing | ✅ unit (two paths); DB test written, unrun |
| 4 | A hand-created evidence row is **D** and renders calmly | ✅ unit + muted styling |
| 5 | An `oeis.search` pin reads `cited`, never a letter | ✅ unit (matrix + `_is_live_pin`) |
| 6 | No `Claim.status` / `Claim.confidence` changes | ✅ by construction; DB test written, unrun |
| 7 | No N+1 on a claim list | ✅ single-query loader; statement-counting DB test, unrun |
| 8 | A seventh instrument without a matrix row fails the harness | ✅ verified literally |

## Follow-ons (not this line)

- **`0.16.1`** — feed grounding into the `0.12.1` planner context so an agent plans to *raise* a
  claim's rung, and give `0.12.5` budget metering a yield measure. This is the payoff the ladder
  exists for.
- **`0.16.2`** — thread-level rollup (`"3 claims at B, 1 ungrounded"`), cheap now that §3.1 exists,
  but it touches the project overview read model (plan §8 Q3).
- **The reproducibility axis** (`bit-verifiable` / `env-pinned` / `tolerance-only`) stays deferred;
  it becomes real with SciPy, and honesty rule 3 is recorded in `grading.py` to warn that author.
