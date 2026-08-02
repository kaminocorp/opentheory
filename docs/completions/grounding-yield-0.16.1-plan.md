# 0.16.1 — Grounding into the planner + the yield measure

**Goal.** Close the loop `0.16.0` opened. The ladder exists and is legible; nothing *acts* on it.
This release feeds each open claim's rung into the `0.12.1` planner so an agent plans to **raise**
it, and measures what a pass actually moved — so a pass can be judged on **yield rather than
activity**.

**Shape.** Backend planner context + orchestrator measurement + one additive column, plus the trace
readout. Migration `0014_agent_run_grounding_yield` (additive JSON, nullable-by-default). No
change to `compute_signal`, `compute_grounding`, the grade matrix's cells, or any write path.

## Why

`docs/completions/claim-grounding-0.16.0.md` §Why states the gap plainly:

> An agent loop needs a *state to plan against*, a *progress measure*, and a *stopping criterion*;
> all three are the same missing object.

`0.16.0` built the object. The planner still receives *thread + open claims + catalog* — it sees
**that** a claim is open, never **how well grounded** it is. So it plans for plausibility, and the
pass reports effort (`ran_count`, `tokens_used`) with no notion of what the effort bought. The
roadmap's success criterion for this release is exactly the missing half:

> A pass that mints five checkpoints and raises nothing must be legible as such.

## Decisions

### D1 — The raise path is derived from the matrix, never hand-written

`grading.py` gains `instruments_reaching(grade)`: the instruments whose matrix row can produce a
grade at least as strong as `grade`. The planner's *"to raise this, run one of …"* hint is computed
from that, so it cannot drift from the ladder, and it **auto-updates when a new instrument lands**
(when Lean arrives, the A-path widens with no prompt edit). This is the same philosophy as the
grade itself: derived from what the matrix says, never a second copy of it.

Note the asymmetry it inherits for free: `counterexample.search` reaches **B** (via `refuted`) even
though its `result` cell is **C**, because the function asks *what can this instrument produce*,
not *what does it usually produce*.

### D2 — The prompt carries the rung, and the settled claims are named as settled

Each open claim renders with `grounding`, `counter` (when present), and the derived raise path. Two
new system rules: prefer a run that raises a rung, and **do not re-run instruments against a claim
that is already `proven` or `refuted`** — those are settled, and more support runs on them are the
purest form of activity-without-yield.

Claim text stays data, never instructions (the `0.12.1` anti-injection posture is unchanged) — the
grounding block is server-derived, so nothing new from the claim body reaches the prompt.

### D3 — Yield is measured point-in-time at both ends of the pass, never derived at read

Grounding is loaded **once before planning** (feeding both the prompt and the `before` snapshot),
and re-loaded **once at pass end** for the same claim ids. Deriving the *after* state lazily at read
time was rejected: a human who raises a rung an hour later would silently be credited to the agent
pass, which is precisely the attribution confusion `primitives.md` forbids.

### D4 — Movement is three-way, because a refutation is progress

Comparing headline strings would call `B → refuted` a regression. It is not — the `0.16.0`
changelog is explicit that *"a refutation is a successful research outcome, not an error"*. So each
measured claim gets:

- **`settled`** — reached `proven` or `refuted` from neither. Decisive, either direction.
- **`raised`** — the support rung strictly strengthened (rank up, or `None` → a grade).
- **`unchanged`** — neither.

`moved = settled + raised`. Only *changed* claims are listed (with `measured` / `moved` counts
alongside), so the record stays bounded on a thread with many claims.

### D5 — One additive JSON column, not an overload of `plan`

`agent_runs.grounding_yield`. `plan` means "the model's proposed runs" and overloading it would rot.
The column is additive and defaulted, so existing rows read as an empty measure.

### D6 — `BudgetPolicy` is documented, not changed

The protocol has no implementer until `0.12.5`. Churning its signature now would be speculative; the
recorded `grounding_yield` **is** the yield measure metering will read. Recorded in its docstring.

## Phases

| # | Scope | Files |
|---|---|---|
| 1 | `instruments_reaching` on the matrix | `app/toolbench/grading.py`, `tests/test_grading.py` |
| 2 | Grounding in the planner context | `app/agent/prompts.py`, `app/agent/planner.py`, `tests/agent/` |
| 3 | Yield measurement + column | `app/models/agent_run.py`, `app/schemas/agent_run.py`, `app/services/agent_runs.py`, `alembic/versions/0014_*`, tests |
| 4 | Trace readout | `frontend/src/types/agent-run.ts`, `components/workspace/agent-pass/agent-run-trace.tsx` |

## Acceptance

1. A claim at `B` renders a raise path naming `z3.prove` (the only A-capable instrument today).
2. A claim at `proven` / `refuted` is marked settled in the prompt.
3. `instruments_reaching(A)` widens automatically when an A-capable instrument is registered.
4. A pass whose runs raise no rung records `moved: 0` with a non-zero `measured`.
5. A pass that takes a claim from `ungrounded` to `proven` records it as `settled`.
6. A `B → refuted` transition is `settled`, never a regression.
7. The trace states "no claim moved" explicitly when `ran_count > 0` and `moved == 0`.
8. `compute_signal`, `compute_grounding`, and every matrix cell are untouched.

## Explicitly out of scope

- Budget *enforcement* (`0.12.5`) — this release supplies the measure, not the meter.
- Iterative plan → observe → replan within a pass.
- Thread-level rollup (`0.16.2`).
- Any change to grading cells, the two-axis separation, or a merged confidence score.
