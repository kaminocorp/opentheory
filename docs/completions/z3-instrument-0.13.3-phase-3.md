# `0.13.3` — Z3 instrument Phase 3 completion notes

> **Completed:** 2026-07-22 · **Plan:** `docs/executing/z3-instrument-0.13.md` Phase 3  
> **Scope:** Frontend drive form + result cards + assumptions gating.  
> **Frontend-only; no backend, schema, or migration.**  
> Note: Phase 2 (DB write-path / API integration tests) was intentionally deferred in this
> implementation pass — the instrument is already registered and reachable via the existing
> catalog + run route; Phase 2 remains a tests-only hardening slice.

---

## What we were trying to achieve

Give members a first-class UI for `z3.prove` instead of the JSON fallback: declare variables with
sorts, edit hypotheses, set a goal, and read a result card that is **visually honest** — proofs
look like proofs, counter-models like refutations, and undecided never reads as a pass.

## What landed

| File | Change |
|---|---|
| `frontend/src/types/toolbench.ts` | Added `Z3ProveOutput` for the instrument's payload shape. |
| `drive-forms.tsx` | `Z3ProveForm` — variable rows (name + int/real `Select`), hypotheses list, goal field; pre-filled with the acceptance proof `x>0, y>0 ⊢ x+y>0`. Switched in `DriveForm`. Empty constraint rows / incomplete vars disable Run. Caps: 8 vars, 16 hypotheses. |
| `result-view.tsx` | `ProofCard` (ok edge), `UndecidedCard` (warn + hatch), `Z3ProveBody` (proof / counter-model / undecided). KaTeX via existing `Formula` + `*_latex`. `resolveOutcomeMeta` special-cases `z3.prove` so a proof labels **Proven**, undecided stays warn. |
| `assumptions-editor.tsx` | `instrumentAcceptsAssumptions("z3.prove") === false` (v1 rejects assumptions server-side). |
| `outcome.ts` | Comment: undecided is escalate, not "deferred Z3" (Z3 is now shipped). |

## Honesty presentation rules (review checks)

| Outcome | UI |
|---|---|
| `result` + `proven` | Green **Proof · machine-checked** card; certificate + used-hypothesis chips; pill **Proven**. |
| `refuted` | Reuses **Counterexample · definitive** card with witness chips; pill **Refuted**. |
| `undecided` | Hatched **Undecided · not a pass** card; reason gloss for `contradictory_hypotheses` / timeout / incomplete; pill **Undecided**. |

Never styles weak-support language as a Z3 proof, and never paints undecided as ok.

## Commands run

```bash
cd frontend && npm run typecheck && npm run lint   # both clean
```

## Deliberate non-goals

- No Phase 2 write-path tests (deferred).  
- No changelog / roadmap updates (Phase 4).  
- No boolean connectives / `z3.satisfy` UI.
