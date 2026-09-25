# 0.23.0 — Lean 4 Grade-A path (`lean.prove`)

**Goal.** Lay a thin, honest path from a bounded Lean 4 snippet to Grade A /
`proven`, so Claim 5 is no longer "wait for a heavier substrate" — without
shipping Mathlib or boiling the ocean.

**Shape.** One new sync instrument, one grade-matrix row, a quiet drive form
and result cards, docs. **No schema, no migration.** Lands only through
`run_instrument` → the checkpoint chokepoint.

## What shipped

- `lean.prove` — bounded Lean 4 snippet (8k chars / 200 lines). v1 is
  prelude / `Init` only. `import`, `sorry`, `admit`, `axiom`, `opaque`,
  `unsafe`, `extern`, `implemented_by`, `native_decide`, `partial`, `#eval`,
  and `IO.` are rejected before the checker is trusted.
- Optional toolchain. Missing `lean` → `undecided` / `unavailable`. The
  catalog still lists the instrument. `z3.prove` and the rest keep working.
- Soft timeout `toolbench_lean_timeout_ms` (default 8000) under the sandbox
  wall. Timeouts → `undecided`. Crash / sandbox kill → mint nothing.
- Grade matrix: `result` → **A**; `refuted` → n/a (this instrument never
  refutes); `undecided` → no grade. A failed typecheck is `undecided`, not
  `refuted` — it does not settle the claim negatively.
- Frontend: snippet textarea prefilled with
  `example : 1 + 1 = 2 := rfl`; proof / failed / undecided cards; assumptions
  gated off.
- Fly install is opt-in (`docker build --build-arg INSTALL_LEAN=1`). Documented
  in `docs/operations/deploy.md`. Not on the default CI image.

## What did not change

- Orchestrator, research-git merge/tag, agent review opt-in, project budget.
- No Mathlib oleans, no `lake` project, no REPL / LeanDojo.
- Semantic blame / diff remain unshipped.
- Funder ≠ contributor ≠ validator. The instrument is a contributor tool;
  it never writes a `Validation` or a `FundingAllocation`.

## Honesty (what is / isn't proven)

| Outcome | Status | Artifact | Grounding |
|---|---|---|---|
| Kernel accepts, no banned constructs | `result` | `proof` | Grade A / `proven` |
| Type error / `sorry` / no theorem | `undecided` | `derivation` | none |
| Timeout / `lean` missing | `undecided` | `derivation` | none |
| Crash / sandbox kill | *exception* | — | nothing minted |

A typechecking empty file is **not** a proof (`no_theorem`). `sorry` typechecks
in Lean — we still reject it.

## Tests

- DB-free: conformance without Lean; banned constructs; no-theorem; missing
  toolchain; fake-binary timeout / failed / proved; crash raises; grade-matrix
  cells; grounding `lean.prove`+`result` → `proven` and `undecided` →
  ungrounded; planner raise path names `lean.prove` beside `z3.prove`.
- Real `lean` typecheck of `1 + 1 = 2` / `1 + 1 = 3`: skipped unless the
  binary is on PATH.
- DB-gated: sorry snippet through `run_instrument`; in-thread mocked proof
  lands a `proof` artifact with `support` on the claim.

## Verification

Filled in after the test run on this branch.

## Unverified

- No Lean binary in this environment — the real-`lean` tests stayed skipped.
- No Fly image rebuild with `INSTALL_LEAN=1` was performed here.
- No pixel-level browser walk of the drive form (no signed-in session against
  a live backend in this environment).
- Mathlib is not present and was not attempted.
