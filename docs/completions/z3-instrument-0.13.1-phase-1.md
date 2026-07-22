# `0.13.1` — Z3 instrument Phase 1 completion notes

> **Completed:** 2026-07-22 · **Plan:** `docs/executing/z3-instrument-0.13.md` Phase 1  
> **Scope:** Security-critical translator + `z3.prove` instrument + unit tests.  
> **Backend-only; no schema, no migration.**

---

## What we were trying to achieve

Ship the first instrument that can **prove** (not merely fail to falsify): a closed-allow-list SymPy→Z3 translator, a two-stage solver harness (vacuous-hypotheses guard → `H ∧ ¬goal`), and the `z3.prove` instrument registered into the production catalog — with unit coverage for every honest outcome.

## Open decisions (resolved as plan recommendations)

| # | Decision | Choice |
|---|---|---|
| 1 | Sorts in v1 | **`int` + `real` only** (bool/connectives deferred) |
| 2 | Nonlinear terms | **Permit** — Z3 accepts them; honest `undecided` on the undecidable fragment |
| 3 | Unsat-core | **Include** via `assert_and_track` → `used_hypotheses` on proof payloads |
| 4 | Version line | **`0.13.x`** |

## What landed

### `app/toolbench/instruments/_z3_support.py` (new)

| Piece | Role |
|---|---|
| `ENGINE` / `ENGINE_VERSION` | Import-time pin from installed Z3 (`5.0.0` with current wheel) |
| `SORTS`, `declare` | `int` → `z3.Int`, `real` → `z3.Real` |
| `to_z3` | Closed allow-list: `Integer`, `Rational`, `Symbol`, `Add`, `Mul`, `Pow` (non-neg int const exponent). Raises on `Float`, undeclared symbols, non-whitelisted nodes, negative exponents. Mixed Int/Real arithmetic promotes via `ToReal`. |
| `relation_to_z3` | `split_relation` → hardened `parse` per side → `to_z3` → op |
| `solve` | Two-stage: (1) hypotheses alone → `contradictory_hypotheses` / `hypotheses_undecided`; (2) tracked `H` + `¬goal` → proven / refuted+model / undecided. Soft `timeout` set on the solver. |
| `render_model` | Exact strings: ints via `as_long`, reals via `as_fraction` → `p/q` |
| `SolveOutcome` | `kind`, `model`, `reason`, `certificate`, `used_hypotheses` |

### `app/toolbench/instruments/z3_prove.py` (new)

| Piece | Role |
|---|---|
| `Z3ProveInput` | `variables` (1..8, safe names, int/real), `constraints` (≤16, each a relation), `goal` (required relation). Field caps mirror `counterexample.search`. |
| `Z3ProveOutput` | `proven` / `refuted` / `status_reason` / `witness` / `certificate` / `used_hypotheses` + `*_latex` companions |
| `Z3Prove.run` | Rejects non-empty assumptions (v1). Maps solve outcome → `(RESULT, proof)` / `(REFUTED, counterexample)` / `(UNDECIDED, derivation)`. **Sync** so the execution sandbox routes it to the killable subprocess. |
| Timeout source | `settings.toolbench_z3_timeout_ms` (Phase 0) |

### Registration

- `INSTRUMENTS` + `__all__` in `instruments/__init__.py` include `Z3_PROVE`.
- Conformance expected-names set includes `"z3.prove"`.

### Tests — `tests/toolbench/test_z3_prove.py`

Covered:

1. **Proof** — `x>0, y>0 ⊢ x+y>0` → `result` / `proof` / `certificate=unsat` + unsat-core names.  
2. **Refutation** — `⊢ x*x != x` → `refuted` with exact string witness `0` or `1`.  
3. **Vacuous guard** — `x>0 ∧ x<0` → `undecided` / `contradictory_hypotheses`, never a proof.  
4. **Translator safety** — Float, undeclared, non-whitelist, negative exponent, injection, assumptions.  
5. **Exact models** — `1/2` fraction string, no floats in payloads.  
6. **Conformance** + sync `run` + input validation.

## Review checks (Phase 1)

- [x] Translator raises (not coerces) on Float / undeclared / non-whitelist.  
- [x] No `eval`/`parse_expr` outside hardened `parse`.  
- [x] JSON-exact payloads (fraction strings, not floats).  
- [x] `run` is synchronous.  
- [x] `ruff check` clean; `pytest tests/toolbench` → **137 passed**, 22 skipped (DB-gated).

## Deliberate non-goals (later phases)

- Phase 2: DB write-path / API / soft-timeout-under-wall-clock integration tests.  
- Phase 3: frontend drive form + result cards.  
- Phase 4: changelog / roadmap / catalog docs.

## Implementation notes / gotchas

- **Vacuous proof is the load-bearing honesty bug.** Stage-1 hypotheses-sat is mandatory; skipping it would let `ex falso` mint `result` for nonsense goals.  
- **Track names** for unsat-core are `h{i}:{original constraint text}` so a reader sees which hypotheses the proof used without a separate id map.  
- **Unused declared variables** are allowed (unlike `counterexample.search`) — they only widen the quantified space for a validity check.  
- **Float rejection** happens both at the SymPy node (`Float`) and via decimal source text that parses to Float.  
- Mutating `settings.toolbench_z3_timeout_ms` in tests is intentional and restored in `finally`.
