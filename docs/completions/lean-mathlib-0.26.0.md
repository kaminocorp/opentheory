# 0.26.0 — Mathlib / lake Lean Grade-A path

**Goal.** Extend the shipped `0.23.0` `lean.prove` path so a claim can reach
Grade A using **Mathlib** via a bounded `lake` / `lean` project — still honest,
still optional, still through `run_instrument` → the checkpoint chokepoint.

**Shape.** Same instrument (`lean.prove`) with an explicit `mathlib` opt-in, a
pre-built lake project scaffold, optional Fly image build-args, a quiet
checkbox, tests, docs. **No schema, no migration.** No orchestrator rewrite.

## What shipped

- `lean.prove` `mathlib: bool` (default `false`). Off keeps the `0.23.0`
  prelude / `Init` contract (`import` rejected). On allows only
  `Mathlib` / `Mathlib.*` / `Init` / `Init.*`.
- Banned constructs still fail closed: `sorry`, `admit`, `axiom`, `opaque`,
  `unsafe`, `extern`, `implemented_by`, `native_decide`, `partial`, `#eval`,
  `#run`, `IO.`, `System.FilePath`, `initialize`, and any non-allow-list import.
- Mathlib mode typechecks with `lake --offline env lean` on an overlay of a
  cached project (`TOOLBENCH_MATHLIB_LAKE` / `OPENTHEORY_MATHLIB_LAKE` /
  `/opt/opentheory/lean-mathlib`). No package fetch at check time.
- Missing `lake` / Mathlib cache → `undecided` / `mathlib_unavailable`.
  Timeout → `undecided`. Crash / sandbox kill → mint nothing.
- Grade matrix unchanged: `result` → **A**; `undecided` / `refuted` → no grade.
  Certificate is `lean-kernel+mathlib` when Mathlib mode proves.
- Soft timeout `toolbench_lean_mathlib_timeout_ms` (default 20000), clamped
  under `toolbench_wall_timeout_s`.
- Dockerfile: `INSTALL_MATHLIB=1` requires `INSTALL_LEAN=1`, pins
  `MATHLIB_REV`, runs `lake update` + `lake exe cache get` + `lake build`.
  Off by default. Scaffold lives at `backend/lean-mathlib/`.
- Frontend: quiet "Allow Mathlib imports" checkbox; result cards mention
  Mathlib / the pin when present.

## What did not change

- Orchestrator, campaigns, research-git merge/tag, agent review, project budget.
- Grade-matrix raise path already named `lean.prove` beside `z3.prove`.
- Funder ≠ contributor ≠ validator. The instrument never writes a
  `Validation` or a `FundingAllocation`.
- Lean REPL / LeanDojo are still unshipped.

## Honesty (what is / isn't proven)

| Outcome | Status | Artifact | Grounding |
|---|---|---|---|
| Kernel accepts, allow-list only | `result` | `proof` | Grade A / `proven` |
| Type error / `sorry` / bad import / no theorem | `undecided` | `derivation` | none |
| Timeout / `lean` missing / Mathlib missing | `undecided` | `derivation` | none |
| Crash / sandbox kill | *exception* | — | nothing minted |

A committed lakefile without `.lake/packages/mathlib` is **not** a proof
environment. Fake `lake` binaries in tests never substitute for production
oleans — they only classify the write path.

## CI vs production toolchain

| Environment | Lean | Mathlib / `lake` cache | What the suite does |
|---|---|---|---|
| CI / default image | absent | absent | banned / missing-toolchain / fake-binary tests; real `lean` and real Mathlib tests skip |
| Prod `INSTALL_LEAN=1` only | present | absent | prelude Grade A works; `mathlib=true` is `mathlib_unavailable` |
| Prod `INSTALL_LEAN=1` + `INSTALL_MATHLIB=1` | present | present | prelude and Mathlib Grade A both possible |

```bash
cd backend
fly deploy --build-arg INSTALL_LEAN=1 --build-arg INSTALL_MATHLIB=1 \
  --build-arg LEAN_TOOLCHAIN=leanprover/lean4:v4.14.0 \
  --build-arg MATHLIB_REV=v4.14.0
```

The Mathlib cache is several GB. Do not enable these build-args on the CI
image. Confirm on the machine:

```bash
fly ssh console -C 'lean --version'
fly ssh console -C 'lake --version'
fly ssh console -C 'test -d /opt/opentheory/lean-mathlib/.lake/packages/mathlib && echo mathlib-ok'
```

## Tests

- Existing `0.23.0` prelude paths unchanged (sorry, import without opt-in,
  missing lean, fake-binary prove/fail/timeout/crash).
- Mathlib: allow-list; sorry / axiom / IO / `Lean` import still fail; missing
  cache is `mathlib_unavailable`; fake lake prove / fail / timeout; `--offline`
  is required; real Mathlib smoke skipped unless the cache exists.
- DB-gated: Mathlib import without opt-in through `run_instrument`; in-thread
  mocked Mathlib proof lands a `proof` artifact.

## Verification

- `ruff check .` clean.
- Default pytest (no `TEST_DATABASE_URL`): **473 passed, 187 skipped**.
- `tests/toolbench/test_lean_prove.py`: **40 passed, 4 skipped** (2 real
  `lean`, 2 real Mathlib/`lake` — not installed here or in CI).
- Frontend `typecheck` / `lint` / `build` clean.

## Unverified

- No Mathlib oleans in this environment — real-`lake` tests stay skipped.
- No Fly image rebuild with `INSTALL_MATHLIB=1` was performed here.
- DB-gated write-path tests were not run unless `TEST_DATABASE_URL` is set.
- No pixel-level signed-in browser walk of the checkbox.

## Sibling releases

Rebased onto `0.25.0` (continuous research) after it landed on `main`.
This line does not rewrite campaigns or the orchestrator. `0.24.0`
(CommandRail) remains a separate shipped surface.
