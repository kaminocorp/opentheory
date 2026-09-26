# 0.36.2 — Assessment R2 P2 bugfixes

**Goal.** Close the three bug-like residuals from
`docs/plans/codebase-assessment-2026-09-26-r2.md` (assessed against
`80495c0` / #23, filed as PR #24). One PR. No file-split ocean, no CI
standup, no R1 membership/planner redo.

**Shape.** `ThreadCreate` forbids client-stamped `status`. Agent-trace
landed steps persist a trimmed display map and pass it to
`resolveOutcomeMeta`. Write-path stubs register as `test.stub*` and
geometry write-path assertions accept `*_latex` companions.

Sits on `0.36.1` (`80495c0`, #23 still open). **No schema, no
migration.**

## What landed

- **`ThreadCreate`.** Standalone (`extra="forbid"`). No `status`.
  `create_thread` stamps `ThreadStatus.OPEN`. Create-time `stage` remains
  allowed. A member `curl` cannot hide a thread from the orchestrator by
  minting it `closed` / `dead_end` / `blocked`.
- **Agent-trace honesty.** `_executed_step` records `output` — the
  flags `resolveOutcomeMeta` reads (`proven`, `refuted`, `satisfied`,
  `unsatisfiable`, `found`, `is_relation`, `outcome`). `LandedStep` uses
  `landedStepMeta` so chrome matches ResultView. Does not fetch the
  checkpoint. Pre-0.36.2 rows without `output` keep proof/satisfy
  fallthrough (warn).
- **Write-path suite honesty.** `tests/toolbench/stubs.py` registers
  `test.stub` / `test.stub_refuted` / `test.stub_undecided` /
  `test.stub_boom`. The 0.11.3 sandbox worker looks the name up in the
  real registry; naming the stub `calc.eval` ran production
  `calc.eval` against `{value: 25}`. Geometry write-path checks
  `radians` / `degrees` and the latex companions instead of exact-matching
  the pre-0.10.4 shape. Instruments are not weakened.
- **`ValidationCreate` docstring.** Bearer JWT, not a stale
  `X-Dev-Actor-Id`-only contract.

## Tests

- DB-free: `ThreadCreate` rejects stamped `status` and extra keys;
  `_trace_display_output` / `_executed_step` persist the trimmed map;
  write-path stubs refuse a production name and dispatch through the
  sandbox as `test.stub` (not `calc.eval`); `landedStepMeta` matches
  ResultView for proof / weak-support / finite-table hold.
- Default pytest (no Postgres): **664 passed**, 222 skipped. Frontend:
  typecheck, lint, **45** tests, `next build` (15.5.15) all pass.
- DB-gated write-path tests (skip without Postgres) now use the
  registered stubs and the latex-aware geometry assertion. They were
  the 7 failures recorded on 0.36.1 and were not re-executed here.

## What did not change

- `create_checkpoint` is still the only ledger write.
- Append-only guards untouched.
- Funder ≠ contributor ≠ validator.
- Account ≠ Actor.
- Instruments stay `result | refuted | undecided`.
- R1 membership / planner / `ClaimCreate` work is not redone.
- P2 file splits, GitHub Actions, `canManageProject` rename, claim-row
  confidence chrome, fat project PATCH, dual-fork race docs, and
  `visitedTabs` stay deferred.

## What this does not claim

This completion does **not** claim the PR is merged to `main`, and it
does not claim `0.36.1` is on `main`.
