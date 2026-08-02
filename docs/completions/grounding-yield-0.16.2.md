# 0.16.2 — Post-review hardening on the grounding line (`0.16.0`–`0.16.1`)

**Goal.** The review pass the `review_completions` skill asks for, run over the completed evidence
ladder (`0.16.0`) and the yield measure (`0.16.1`). One **MEDIUM correctness defect** in the yield
measure, one **unimplemented promise** the code itself asserted, and five quality/robustness gaps.

**Shape.** Backend read model + one schema contract + two frontend surfaces + tests. **No migration,
no column, no new endpoint**; `compute_signal`, `compute_grounding`, and every cell of the grade
matrix remain untouched — as they were in `0.16.1`.

## What the review found held

Worth stating, because it is most of the surface: the `(instrument, status)` matrix and its backward
read (`outranks` / `instruments_reaching` / `raise_path`) are correct; the anti-injection posture is
genuinely unwidened (every `0.16.1` line is server-derived); the single-snapshot-for-two-consumers
decision is sound; `compute_yield` taking claim ids explicitly rather than the snapshots' keys is
right, and the reasoning behind it is the load-bearing kind. `ruff` was clean and the full suite
green (309 passed / 128 skipped) before this pass, and the frontend built clean. No CRITICAL, no
HIGH, no security finding.

## The defect

### 1 — A proof overturned by a counterexample scored as *no movement* (MEDIUM)

`app/services/grounding.py::_movement`

```python
if after.headline in SETTLED_HEADLINES and before.headline not in SETTLED_HEADLINES:
```

The guard existed to stop a second proof on an already-`proven` claim from re-counting as progress.
It also swallowed the transition **between** two settled headlines. A claim carrying a
machine-checked proof that then acquires an exact counterexample goes `proven → refuted` with its
*support* rung untouched — the proof is still linked — so it failed the settled branch, failed
`outranks(A, A)`, and fell through to `unchanged`. Reproduced against the real functions:

```
before headline: proven | after headline: refuted
measured=1 moved=0
   proven -> refuted | movement = unchanged
```

`moved == 0` then drove `PassYieldReadout` to the sentence branch, so the trace stated **"1 run
landed, but no claim's grounding moved."** — about a pass that had just overturned a proof. In the
release whose entire thesis is that a trace must not misreport yield, that is the failure mode
inverted onto itself.

**Reachable**, not theoretical: *"do not plan runs against a settled claim"* is system rule 8 — an
instruction to a language model, not a structural drop in `planner.py`. Nothing prevents a model
from pointing `counterexample.search` at a `proven` claim.

**Fix** — one predicate: `before.headline != after.headline`. `proven → proven` and
`refuted → refuted` still read `unchanged` (the case the original guard was actually protecting),
while a contradiction is decisive movement in **either** direction. Both directions are now named
tests.

## The unimplemented promise

### 2 — `grounding_yield` rode on the summary schema for a surface nobody built (MEDIUM)

`app/schemas/agent_run.py` deliberately broke its own *"no heavy JSON on the summary"* rule with this
justification:

> *"a history row that shows spend without result is exactly the reading the release is trying to
> prevent."*

The history row (`agent-pass-panel.tsx`) rendered `{ran_count}/{planned_count} runs` and nothing
else. The field was serialized on every summary response and read by no one — the code asserted a
fix it had not made.

**Fix** — the history row now carries `N/M moved` beside the run count, tinted `state-ok` when
anything climbed. A never-measured pass shows nothing at all rather than `0 moved`, which would
claim a measurement that was never taken.

## The rest

### 3 — Recorded changes were discarded by the UI whenever `moved === 0` (LOW–MEDIUM)

`compute_yield` deliberately records off-ladder changes (`ungrounded → cited`: a real pin, but no
rung) with the comment *"the trace should show what happened"*. `PassYieldReadout` gated the list on
`moved > 0`, so a pass that landed three citations rendered "no claim's grounding moved" and threw
the three away. The list now renders whenever anything changed, with *"Recorded, but no claim climbed
a rung"* underneath when nothing moved — which keeps the honest headline without deleting the
evidence for it. Compounded finding 1: a proof-overturned pass previously showed nothing at all.

### 4 — "Never measured" and "measured zero" were the same value (LOW)

The client's guard read `measure !== undefined` against a **non-optional** field — it could never be
false. So the documented contract *"an unmeasured pass renders `—`, never `0/0`"* held only for
`failed`/`running` passes; a completed row with the column's `'{}'` default rendered `0/0` and
**"No open claims on this thread to move."** — a sentence about a thread nobody had looked at.

The two are genuinely different statements, and the column cannot express the difference (its
default and a real zero measure are both dicts). So the **read schema** now separates them:
`grounding_yield: PassYield | None`, with a `mode="before"` validator mapping `{}` → `None`.
`compute_yield` always writes all three keys, so an empty object can only mean the measure was never
taken — an invariant now pinned by its own test. The client guard is consequently a real test, and
the surfaces render `—` vs `0/4` for what are, in fact, two different events.

*(Practically unreachable today — the loop has never been enabled in production, so no `agent_runs`
rows exist. Fixed because a guard that reads as handling a case it silently does not is worse than
no guard.)*

### 5 — `SETTLED_HEADLINES` was defined twice (LOW)

Once in `services/grounding.py`, once in `agent/prompts.py`, with a comment noting the duplication.
In a release whose thesis is *derive, never copy*, this was the one place a second copy was made —
and the two layers cannot import each other. It now lives once in `schemas/claim.py` beside the
`GroundingHeadline` union it is a subset of, imported by both.

### 6 — A failed measurement could fail a pass that had already landed everything (LOW)

The closing `grounding_by_claim` sat outside any `try`, so a DB blip there propagated to
`run_agent_pass`'s catch-all → `rollback()` → `status=failed`, for a pass whose every step had
already committed durably. That inverts this file's own invariant (*"one bad step never aborts the
pass"*) on the least important step of all — the yield is *narrative*, like `steps`, while the
checkpoints are the ledger.

Now guarded: an unmeasurable pass rolls back, re-fetches the row **by id** (never by attribute
access — rollback expires the instance, and an expired read outside the greenlet raises rather than
reloading), and completes with no measure. The re-fetched row still carries the full step trace,
because the per-step loop committed it.

### 7 — Three tests that could not fail for the reason they named (LOW)

- `test_a_pass_that_mints_but_raises_nothing_reads_moved_zero` — the headline acceptance test for
  the whole release. Its docstring said *"every run came back `undecided`… even though the
  instruments genuinely ran"*, but the fixture was `after = dict(before)`: identical maps, no
  `undecided` link anywhere. It asserted little beyond `measured == 3`. `after` now models the new
  ungraded evidence row, so the test fails the day `undecided` starts contributing a rung.
- `test_pass_records_the_rung_it_moved` — `assert seen[...] == {} or seen[...].headline ==
  "ungrounded"`. The first branch always holds, so the second was dead and the assertion could not
  distinguish a correct empty snapshot from a snapshot never taken. Now a plain equality.
- `test_grounding_block_adds_no_claim_authored_text` — the anti-injection byte-identity filter
  matched only `grounding:` / `to raise:`, missing `counter-evidence at rung:` and `settled: yes`. A
  filter narrower than the renderer lets a future author add an untrusted line and stay green. It now
  covers every line `_render_grounding` can emit, asserts the block is non-empty (so the equality is
  never vacuous), and a second test covers the settled branch's different line set.

### Also added

- **`tests/agent/test_migration_0014.py`** — `0013` had DB-free structural checks and `0014` had
  none, despite being — at the time of this pass — the one still **written but unapplied** (it has
  since landed; see Unverified). Pins the revision linkage, that it
  is the only head (a second head makes `alembic upgrade head` ambiguous mid-deploy), and that the
  model and migration agree on the column. Reads other migrations by regex rather than executing
  them, so a structural check does not depend on every historical migration staying importable.
- **`tests/agent/test_agent_run_schema.py`** — the tri-state read contract from finding 4, including
  the invariant it rests on (`PassYield().model_dump() != {}`).

## Not changed, deliberately

- **`instruments_reaching` has no production caller** (tests only); `raise_path` is the real
  consumer. Kept: it is the honest public primitive of a pure module, it is what acceptance
  criterion 3 is written against, and `raise_path` is defined in terms of the same private helper.
- **The model declares `default=dict` while migration `0014` declares `server_default '{}'`.**
  Harmless — `env.py` does not enable `compare_server_default`, and SQLAlchemy's prefetch populates
  the attribute on insert, so no `NULL` ever reaches Pydantic. The `'{}'` default is now
  *load-bearing* for finding 4's tri-state and is asserted by the new migration test.

```bash
cd backend && uv run ruff check .   # clean
cd backend && uv run pytest -q      # 319 passed, 128 skipped (DB-gated)  [was 309]
cd frontend && npm run typecheck && npm run lint && npm run build   # all clean
```

## Unverified

Unchanged from `0.16.1`, and none of it moved in this pass:

- ~~**Migration `0014` is still unapplied anywhere.**~~ **Applied to the live database on
  2026-08-02**, after this pass and before the code deploy — the correct order, since the column is
  additive and the currently-deployed backend never selects it. Verified in `information_schema`
  (`json`, `NOT NULL`, default `'{}'::json`) against **0 existing `agent_runs` rows**, which also
  confirms this pass's finding-4 legacy-row case was theoretical. This release adds no migration of
  its own. **The backend code deploy is still outstanding** — until it lands, the column exists and
  nothing reads it.
- **The DB-gated tests were still not run** — the two `0.16.1` orchestrator round-trips and the 8
  from `0.16.0`. Every rule this pass changed is pinned DB-free in `tests/test_grounding.py`,
  `tests/agent/test_agent_run_schema.py`, and `tests/agent/test_prompts.py`.
- **No browser walk** — the two changed surfaces (the history-row yield chip and the widened
  `PassYieldReadout`) were verified through typecheck/lint/build only. They join the eyeball pass
  owed since `0.14.0`.
- **No live agent pass was run.** The loop is still dark in production (`AGENT_LOOP_ENABLED=false`),
  so the planner's behavioural response to the grounding block remains unobserved.
- **Finding 6's rollback path is not covered by a test** — forcing a DB failure precisely at the
  measurement would need either a DB-gated fixture or a fault-injection seam that does not exist
  today. The code path is small and mirrors the pattern `run_agent_pass` already uses.

## Follow-ons

- **`0.16.3` — thread-level rollup** (`"3 claims at B, 1 ungrounded"`), previously numbered `0.16.2`
  and shifted by this hardening pass. Still cheap, still touches the project-overview read model.
- **A structural planner guard for settled claims.** Finding 1 was reachable because rule 8 is a
  prompt instruction, not validation. Dropping a proposed run that targets a `proven`/`refuted` claim
  in `planner.py` — recorded as `dropped_invalid` with a `settled_claim` reason, exactly like the
  existing semantic drops — would make the rule structural rather than advisory. Deliberately **not**
  done here: it changes planning behaviour, which is a feature decision and not a hardening one.
