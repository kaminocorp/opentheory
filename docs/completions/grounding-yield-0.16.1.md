# 0.16.1 — Grounding into the planner, and the yield measure

**Goal.** Close the loop `0.16.0` opened: the ladder existed and was legible, but nothing acted on
it. The planner now receives each open claim's rung and plans to *raise* it, and every completed
pass records what it actually moved — so a pass is judged on **yield rather than activity**.

**Shape.** Planner context + orchestrator measurement + one additive column + the trace readout.
Migration `0014_agent_run_grounding_yield`. `compute_signal`, `compute_grounding`, and every cell of
the grade matrix are untouched.

## Why

The `0.12.1` planner received *thread + open claims + catalog*. It could see **that** a claim was
open, never **how well grounded** it was — so it planned for plausibility, and the trace reported
effort (`ran_count`, `tokens_used`) with no notion of what the effort bought. Six instruments
manufactured graded results, `0.16.0` rendered the grade, and the one consumer that could *act* on
it was still blind.

## What landed

### The matrix, read backwards (`app/toolbench/grading.py`)

`0.16.0` asks *"instrument X returned S — how rigorous is that?"*. Planning needs the inverse:
*"this claim sits at rung R — what could beat it?"*. Three new pure functions answer it **from the
same table**, so the advice can never drift from the grade it is advising about:

- `outranks(candidate, incumbent)` — the ladder comparison, keeping `_RANK` private (a caller
  re-deriving it would hit the StrEnum's lexicographic trap that `strongest` already guards).
- `instruments_reaching(grade)` — what an instrument is *capable* of, read across **all three**
  status cells. This is why `counterexample.search` counts as B-capable despite a C `result` cell:
  the run might refute. Grading uses the actual status; planning uses the possible one.
- `raise_path(current)` — strictly stronger than `current`. **`raise_path(A) == []` is the
  load-bearing case**: an empty list is how the planner learns a claim is done, and it is the loop's
  first real stopping signal.

Because the advice is derived, **a newly registered instrument widens the raise path with no prompt
edit** — `test_only_z3_can_reach_grade_a_today` is written to go red the day Lean lands.

### The prompt (`app/agent/prompts.py`)

Each open claim now renders its `grounding`, its counter rung when present, and either a
matrix-derived `to raise: run one of […]` line **or** a `settled: yes` stop line — never both. Two
new system rules: prefer runs that raise a rung, and do not plan runs against a settled claim. A
compact ladder legend states each rung's epistemic limit (C *"never proves"*, D *"no tool in the
loop"*), so the model reasons about the ladder instead of pattern-matching letters.

**The anti-injection posture is unchanged and tested.** Every 0.16.1 line is server-derived — the
read model's headline plus the matrix — so no new byte of claim-authored text reaches the prompt.
`test_grounding_block_adds_no_claim_authored_text` renders a benign and a hostile claim at identical
grounding and asserts the blocks are byte-identical.

### The yield measure (`app/services/grounding.py`, `app/services/agent_runs.py`)

Grounding is loaded **once before planning** and serves both consumers — the planner's context and
the `before` snapshot — then re-read at pass end. One extra batched query per pass, and the state
the model reasoned about is exactly the state the yield is measured against.

Two decisions carry the honesty:

- **`compute_yield` takes claim ids explicitly, not the snapshots' keys.** A claim with no evidence
  is absent from *both* maps — and it is precisely the claim a pass most wants to move. Inferring
  from keys would make the best-case improvement invisible on both sides of the diff.
- **Movement is three-way, and `settled` is tested first.** Comparing headlines would call
  `B → refuted` a regression; it is not (`0.16.0`: *a refutation is a successful research outcome*).
  And a refutation usually arrives with the *support* rung untouched, so a rank comparison alone
  would score the pass's best possible result as `unchanged`.

Measured point-in-time inside the pass, never derived at read: a human who raises a rung an hour
later must not be silently credited to the agent.

### The surface (`agent-run-trace.tsx`)

`Claims moved` sits in the same readout row as `Runs` and `Tokens` — spend and yield read together,
or the pass gets judged on activity alone. Below it, either the rungs that climbed
(`Ungrounded → Refuted · settled`, in the claim row's own vocabulary via the newly exported
`groundingHeadlineLabel`) or, when nothing moved, the sentence in words:

> *3 runs landed, but no claim's grounding moved.*

A pass with no recorded measure renders `—`, never `0/0` — the latter would assert something the row
does not say.

## Acceptance

| # | Criterion | Status |
|---|---|---|
| 1 | A claim at `B` gets a raise path naming `z3.prove` | ✅ unit (prompt + matrix) |
| 2 | A `proven` / `refuted` claim is marked settled, with no raise path | ✅ unit |
| 3 | `instruments_reaching(A)` widens when an A-capable instrument registers | ✅ pinned to go red on Lean |
| 4 | A pass that raises nothing records `moved: 0`, non-zero `measured` | ✅ unit + DB test written |
| 5 | `ungrounded → proven` records as `settled` | ✅ unit + DB test written |
| 6 | `B → refuted` is `settled`, never a regression | ✅ named unit test |
| 7 | The trace states "no claim moved" in words | ✅ `PassYieldReadout` |
| 8 | `compute_signal` / `compute_grounding` / matrix cells untouched | ✅ by construction |

```bash
cd backend && uv run ruff check .   # clean
cd backend && uv run pytest -q      # 309 passed, 128 skipped (DB-gated)
cd frontend && npm run typecheck && npm run lint && npm run build   # all clean
```

## Caught in passing

Adding the `grounding` kwarg broke the four **stub planners** in `test_orchestrator.py` and
`test_agent_runs_api.py` — which are DB-gated, so a green local run proved nothing about them. Fixed
by mirroring the real signature explicitly (not `**kwargs`): the planner is an injected seam, and a
stub that quietly accepts anything would let the orchestrator pass an argument the real planner
never receives with no test noticing.

## Unverified

- ~~**Migration `0014` has not been applied anywhere.**~~ **Applied to the live database on
  2026-08-02** (`0013_agent_runs` → `0014_agent_run_grounding_yield`, direct connection on `:5432`
  per the runbook). Verified in `information_schema`: `json`, `NOT NULL`, default `'{}'::json`;
  `agent_runs` held **0 rows**, so no backfill was exercised — the loop has never been enabled in
  production. Additive and backward-compatible with the deployed backend, which does not select the
  column.
- **The DB-gated tests were not run** — the two new orchestrator round-trips
  (`test_pass_records_the_rung_it_moved`, `test_a_pass_that_mints_a_checkpoint_but_moves_no_rung_says_so`)
  join the 8 still-unrun from `0.16.0`. The *rules* they cover are pinned DB-free in
  `tests/test_grounding.py`.
- **No browser walk** — the trace readout was verified through typecheck/lint/build only. It joins
  the eyeball pass owed since `0.14.0`.
- **No live agent pass was run**, so the planner's *behavioural* response to the grounding block is
  unobserved. The loop is still dark in production (`AGENT_LOOP_ENABLED=false`).

## Follow-ons

- **`0.12.5` budget metering** now has its missing half. `BudgetPolicy` was deliberately left
  unchanged — no implementer yet — but `AgentRun.grounding_yield` is what lets a budget ask *what
  did the last pass buy?* instead of only *how much did it spend?*.
- **`0.16.2`** — thread-level rollup, still cheap and still touching the overview read model.
- **An iterative plan → observe → replan within a pass** becomes meaningful now that a pass can tell
  whether it is making progress. That is the natural next step toward continuous autonomy.
