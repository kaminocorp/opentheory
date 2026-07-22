# `0.13.x` — Z3 (`z3.prove`): the first machine-checked verifier

> **Status — largely shipped (2026-07-22).** Phases 0, 1, 3, 4 landed as `0.13.0`–`0.13.4`
> (completion notes in `docs/completions/z3-instrument-0.13.*`). **Phase 2** (DB write-path /
> API / execution-safety tests) is **deferred** — production still routes through the existing
> `run_instrument` chokepoint; unit + conformance coverage is green. The **verifier wave, part 1**
> from `docs/plans/roadmap-next-steps.md` and the two Z3 open threads in
> `docs/plans/toolbench-catalog.md` are resolved. Prerequisites — the toolbench spine (`0.9.x`),
> the honesty model + `counterexample.search` (`0.10.x`), and the execution sandbox (`0.11.x`) —
> were already shipped. Depends on the adapter contract (`app/toolbench/adapter.py`) and the
> shared SymPy plumbing (`app/toolbench/instruments/_sympy_support.py`), both reused verbatim.

> Add the first instrument that can **prove** — not merely fail to falsify. `z3.prove` takes typed
> variables, a set of linear-arithmetic hypotheses, and a goal relation, and returns one of the
> three honest outcomes backed by an SMT decision procedure: **`result`** (the goal is *entailed* —
> `unsat` certificate), **`refuted`** (a concrete counter-model that satisfies the hypotheses but
> breaks the goal), or **`undecided`** (the solver returned `unknown`). It slots into the existing
> Tier-0 subprocess sandbox, needs **zero net-new infrastructure** (`z3-solver` is a native wheel),
> and — unlike every current instrument — its supporting side is a *proof*, not weak support.

---

## Why this is the right next instrument (and why it's still "thin")

`counterexample.search` can only ever **weaken** a claim (find a witness) or offer **weak support**
(no witness in a bounded grid — "absence of evidence, never proof"). Nothing in the shipped bench
can land a *definitive supporting* result. Z3 closes exactly that gap: `unsat` of `hypotheses ∧
¬goal` is a machine-checked proof that the goal holds for **all** assignments, not just the sampled
grid. And it costs almost nothing to add — the entire write / attribution / sandbox / catalog spine
already exists and is reused unchanged.

| Existing piece | File | This line's use |
|---|---|---|
| `Instrument` Protocol (structural — no base class) | `toolbench/adapter.py:48` | `z3.prove` conforms by shape; nothing to subclass. |
| `run_instrument(...)` — the tool-run write path | `services/tool_runs.py:94` | **The single call.** Composes artifact + evidence + blame tuple + checkpoint through the chokepoint. Untouched. |
| Killable subprocess sandbox (sync `run` → child process, wall-clock + `RLIMIT_AS`) | `toolbench/execution/policy.py:33`, `execution/runner.py` | `z3.prove.run` is **sync**, so `execution_mode_for` auto-routes it to the sandbox. Z3 objects never cross the process boundary — `run` returns a plain-dict `InstrumentResult`. |
| Registry + catalog serializer | `toolbench/registry.py`, `toolbench/catalog.py:45` | Self-registration on import; the catalog descriptor + three-outcome contract fall out for free. |
| Membership-gated run route + public catalog | `api/routes/instruments.py` | The same `POST …/instruments/{name}/run` surface serves it — humans now, the agent loop later. |
| **Hardened** input safety: `_reject_unsafe_source` (AST allow-list *before* `parse_expr`'s `eval`), `split_relation`, `parse`, `relation_to_latex` | `toolbench/instruments/_sympy_support.py` | Reused **verbatim** for parsing each relation. The `0.9.7` `parse_expr`-is-`eval` RCE lesson is inherited, not re-learned. |

**What is genuinely net-new** (all additive — no schema, no migration):

| New piece | Where | Note |
|---|---|---|
| `z3-solver` dependency | `backend/pyproject.toml` | `uv add z3-solver`. Native wheel, MIT, Tier-0 (see `toolbench-catalog.md`). |
| Z3 support module — SymPy-expr→Z3 translation + solver harness + engine pins | `app/toolbench/instruments/_z3_support.py` | The **one security-critical file**. Mirrors `_sympy_support.py`. |
| The instrument | `app/toolbench/instruments/z3_prove.py` | Mirrors `counterexample_search.py` in shape and size. |
| Registration | `instruments/__init__.py` (`INSTRUMENTS`, `__all__`) | One line + the export. |
| Config: `toolbench_z3_timeout_ms` | `core/config.py` | Z3's *internal* soft timeout — set **below** the subprocess wall-clock so a hard problem returns an honest `unknown`→`undecided` instead of being killed. |
| Frontend drive form + result card | `workspace/toolbench/drive-forms.tsx`, `result-view.tsx` | Polish — the `JsonForm` fallback (`drive-forms.tsx:471`) makes it usable in the UI *before* this lands. |

---

## The design question, resolved

The catalog left two Z3 forks open. This plan resolves both:

**1. One instrument, `z3.prove`, not a `prove`/`refute` pair.** A single validity check subsumes
both directions. To prove the goal `G` under hypotheses `H₁…Hₙ`, assert `H₁ ∧ … ∧ Hₙ ∧ ¬G` and check:

| Z3 result | Meaning | Honest outcome | `artifact_kind` | Payload |
|---|---|---|---|---|
| `unsat` | No assignment satisfies the hypotheses while breaking the goal → **the goal is entailed** | `result` | `proof` | certificate marker (`"unsat"`); optional unsat-core |
| `sat` | An assignment satisfies the hypotheses **and** breaks the goal → **counter-model** | `refuted` | `counterexample` | the model (exact rationals/ints as strings) |
| `unknown` | Solver could not decide (nonlinear, timeout, incompleteness) | `undecided` | `derivation` | reason (`"timeout"` / `"incomplete"`) |

The `sat` branch already yields a witness, so this one instrument also does exact
counterexample-finding for linear arithmetic — a strict upgrade over `counterexample.search`'s
bounded grid on that fragment. A dedicated `z3.satisfy` (model-finding / constraint-solving as the
*primary* output) is a natural follow-on, not v1.

**2. Certificate lives on the artifact/output.** `unsat` records a certificate marker (and, when
cheap, the unsat-core of the named hypotheses) in the result `output`; the produced `Artifact.kind`
is the new free-form value **`"proof"`** (no migration — `Artifact.kind` is a `VARCHAR`, and
`InstrumentResult.artifact_kind` is `Field(min_length=1)`). Full replayable proof terms
(`solver.proof()`) are deliberately **out of scope** for v1 — they are large, brittle across Z3
versions, and the `engine_version` pin already makes the result reproducible.

### The correctness subtlety this plan must not get wrong

**Vacuous proof from contradictory hypotheses.** If `H₁ ∧ … ∧ Hₙ` is itself `unsat`, then
`H ∧ ¬G` is trivially `unsat` for *every* `G` — Z3 would report "proven" for a nonsense goal (*ex
falso quodlibet*). Recording that as `result` would be exactly the "undecided rendered as a pass"
dishonesty this bench exists to prevent. So `run` **first checks the hypotheses alone**: if they are
`unsat`, it returns `undecided` with reason `"contradictory_hypotheses"` (never a `result`); if
`unknown`, `undecided` with reason `"hypotheses_undecided"`. Only when the hypotheses are `sat`
(or absent) does the main `H ∧ ¬G` check run and its `unsat` count as a genuine proof.

---

## Goal & acceptance bar

A project **member** picks `z3.prove` in the toolbench, declares variables, hypotheses, and a goal,
and runs it. The platform validates inputs, translates each relation to Z3 through the hardened
parser, runs the two-stage check in the subprocess sandbox, and lands an attributed checkpoint (+
evidence when a claim is targeted) through the chokepoint — with the honest outcome on the blame
tuple.

**Acceptance (worked examples, all landing through `run_instrument`):**

1. **Proof.** `variables={x: real, y: real}`, `constraints=["x > 0", "y > 0"]`, `goal="x + y > 0"`
   → `unsat` → **`result`**, `artifact_kind="proof"`.
2. **Refutation with witness.** `variables={x: int}`, `constraints=[]`, `goal="x*x != x"` →
   `sat` with model `x=0` (or `x=1`) → **`refuted`**, witness recorded.
3. **Undecided (honest, not a pass).** A nonlinear goal Z3 returns `unknown` on within the timeout
   → **`undecided`**, reason recorded; **mints a real checkpoint** (a citable "couldn't decide"),
   never an error.
4. **Vacuous guard.** `constraints=["x > 0", "x < 0"]`, any goal → **`undecided`**
   (`contradictory_hypotheses`), *not* `result`.
5. **Hard problem → clean undecided, not a kill.** A goal that exceeds `toolbench_z3_timeout_ms`
   returns `unknown`→`undecided` (Z3's internal timeout fires *before* the subprocess wall-clock),
   so it is recorded, not minted-nothing.

Flagship tie-in: on the *measuring across a corner* thread, `z3.prove` can now **prove** the
linear-arithmetic claims (e.g. the triangle-inequality-style relations) definitively, where
`counterexample.search` could previously only weak-support them.

---

## Standing invariants (how this line honours them)

| Invariant | How honoured |
|---|---|
| **One write path** | Reaches the ledger **only** via `run_instrument` → `create_checkpoint`. No new mint path. |
| **Failure split** | A translation/parse failure raises inside `run` (or before it) → the write path mints nothing and returns `422`. A genuine `unknown` is a **successful** run and *is* recorded as `undecided`. |
| **Honesty over confidence** | `undecided` is never a pass; `result` is emitted **only** on an `unsat` of a *satisfiable*-hypotheses check; `refuted` only with a concrete counter-model. The vacuous-proof guard is part of this. |
| **Reproducibility / no naked floats** | `engine="z3"`, `engine_version=z3.get_version_string()` on the blame tuple. Real models are Z3 rationals rendered as **exact fraction strings** (`p/q`), never `float` — so `_canonical_output_hash` stays stable. Float *literals* in inputs are rejected (exact rationals only). |
| **Security** | Every relation string passes the existing `_reject_unsafe_source` AST gate *before* `parse_expr`. The SymPy→Z3 translator is a closed allow-list of node types — no `eval`, no attribute walk, no new parser. |
| **Human-first** | Ships on the identical `POST …/instruments/{name}/run` surface humans and (later) the agent loop both use. No agent-only path. |
| **Append-only / stages optional** | No edits; nothing enforces stages. Pure additive instrument. |

---

## Decisions

1. **`z3.prove` only in v1** (validity check; `sat` branch doubles as exact counterexample-finding).
   `z3.satisfy` (model-finding), boolean connectives in-string, and quantifiers are follow-ons.
2. **Theory scope = quantifier-free linear integer + real arithmetic (LIA/LRA).** Free variables are
   implicitly universally quantified via the assert-`¬goal` trick. Nonlinear terms are *permitted*
   (Z3 accepts them) but honestly degrade to `undecided`. Sorts: `int`, `real` in v1 (`bool` +
   connectives deferred, since they need a parser beyond `split_relation`).
3. **Constraints and goal are each a single top-level relation** (`lhs OP rhs`, `OP` ∈ the existing
   `RELATIONAL_OPS`). Hypotheses are conjoined; the goal is the one relation to prove. This reuses
   `split_relation` + `parse` **verbatim** — the only net-new parsing is the closed-allow-list
   SymPy→Z3 tree translation. (In-string `And`/`Or`/`Not`/`Implies` is the deferred boolean phase.)
4. **The translator is the security boundary and is a closed allow-list.** It maps a *whitelist* of
   SymPy node types (`Integer`, `Rational`, `Symbol`, `Add`, `Mul`, `Pow` with a non-negative
   integer constant exponent, unary minus) to Z3, binding each `Symbol` to its declared Z3 sort.
   Undeclared symbols, `Float` literals, and any non-whitelisted node **raise** (→ `422`, mints
   nothing). No SymPy→string→Z3 round-trip, no `eval`.
5. **Z3 internal timeout < subprocess wall-clock.** `solver.set("timeout", toolbench_z3_timeout_ms)`
   with a default (e.g. `10_000` ms) safely under `toolbench_wall_timeout_s` (30 s). A soft timeout
   → `unknown` → honest `undecided` (recorded). The subprocess wall-clock/`RLIMIT_AS` remains the
   hard backstop for a pathological case that ignores the soft timeout (→ killed → mints nothing).
6. **Certificate = marker + optional unsat-core; no full proof terms in v1** (Decision above).
7. **New `artifact_kind="proof"`** — free-form, no migration. `refuted`→`counterexample` (existing),
   `undecided`→`derivation` (existing).

---

## Phases

Each phase is a deployable/reviewable micro-release, mirroring the `0.10.1`→`0.10.3` instrument
cadence (backend instrument → DB/API tests → frontend → docs). Versions are proposals.

### Phase 0 — Dependency, config, and the honesty contract (`0.13.0`) ✅

**Backend-only; no schema, no migration.** See `docs/completions/z3-instrument-0.13.0-phase-0.md`.

- [x] `cd backend && uv add z3-solver` — resolved `z3-solver==5.0.0.0` / `z3.get_version_string()` → `5.0.0`.
- [x] `core/config.py`: add `toolbench_z3_timeout_ms: int = 10_000` under the toolbench-sandbox
      block, with a comment stating the "< wall-clock ⇒ honest undecided" rationale.
- [x] `.env.example`: document the new knob (default is fine for local).
- [x] Sanity: `uv run python -c "import z3; print(z3.get_version_string())"` resolves in-process.

**Review checks:** dependency is a wheel (no system solver required); the config default is strictly
below `toolbench_wall_timeout_s`.

### Phase 1 — The instrument + the safe translator (`0.13.1`) ✅

**Backend-only; the security-critical core. No schema, no migration.** See
`docs/completions/z3-instrument-0.13.1-phase-1.md`.

- [x] `app/toolbench/instruments/_z3_support.py` — engine pin, closed allow-list `to_z3`,
      `relation_to_z3`, two-stage `solve` + unsat-core track names, exact-string models.
- [x] `app/toolbench/instruments/z3_prove.py` — `Z3Prove` / inputs/outputs / sync `run`.
- [x] Register `Z3_PROVE` in `instruments/__init__.py`.
- [x] `tests/toolbench/test_z3_prove.py` — conformance + each honest outcome + translator safety.
- [x] `tests/toolbench/test_conformance.py` — `"z3.prove"` in expected-names set.

**Review checks:** the translator raises (not silently coerces) on `Float`, undeclared symbols, and
non-whitelisted nodes; no `eval`/`parse_expr` is called outside the hardened `parse`; every payload
that reaches the write path is JSON-exact (fraction strings, not floats); `run` is **sync** (so it
lands in the subprocess sandbox).

### Phase 2 — Ledger write path + API round-trip + execution safety (`0.13.2`) ⏸ deferred

**Tests-only slice (no production code change), DB-gated (auto-skips without `TEST_DATABASE_URL`).**
Skipped in the 2026-07-22 implementation pass (Phases 0→1→3→4). Production still uses
`run_instrument`; unit tests cover the instrument. Pick up when hardening for prod confidence.

- [ ] `tests/toolbench/test_z3_prove_write_path.py` (or extend `test_instruments_write_path.py`):
      prove/refute/undecided each compose through `run_instrument` → a `Checkpoint` with the blame
      tuple (`engine="z3"`, pinned version), the produced `Artifact` (`kind="proof"` on a proof),
      and — when a `claim_id` is targeted — `Evidence` with the outcome-defaulted `relation_kind`
      (`support`/`weaken`/`context`). Assert the append-only guards hold (no edit path).
- [ ] `tests/toolbench/test_instruments_api.py`: the catalog now lists `z3.prove` (schemas +
      three-outcome contract); `POST …/instruments/z3.prove/run` returns `201` for a member, `403`
      for a non-member, `404` for an unknown project, `422` on bad inputs / untranslatable relation.
- [ ] `tests/toolbench/test_execution_safety.py`: a goal exceeding `toolbench_z3_timeout_ms` returns
      `undecided` (Z3 soft-timeout, **not** a subprocess kill → a real checkpoint is minted); a
      resource-heavy input stays within the sandbox caps.

**Review checks:** the DB gate is respected (green-but-skipped without Postgres is *not* a pass for
this phase — run against a throwaway DB); the timeout test asserts a *minted* `undecided`, proving
the soft-timeout-under-wall-clock ordering (Decision #5) actually holds.

### Phase 3 — Frontend drive form + result card (`0.13.3`) ✅

**Frontend-only.** See `docs/completions/z3-instrument-0.13.3-phase-3.md`.

- [x] `types/toolbench.ts`: `Z3ProveOutput`.
- [x] `drive-forms.tsx`: `Z3ProveForm` + `case "z3.prove"`.
- [x] `result-view.tsx`: `Z3ProveBody` (proof / counter-model / undecided) + outcome meta.
- [x] `assumptions-editor.tsx`: `instrumentAcceptsAssumptions("z3.prove") === false`.
- [x] KaTeX via existing `formula.tsx` `*_latex` companions.

**Review checks:** `npm run typecheck && npm run lint` clean; a proof is visually distinct from weak
support; `undecided` is never presented as a pass (design-system honesty rule).

### Phase 4 — Docs + post-review hardening (`0.13.4`) ✅ (docs)

**Docs/comments.** See `docs/completions/z3-instrument-0.13.4-phase-4.md`. A formal
`/code-review` pass was not run in this session; self-checks (ruff, toolbench unit tests,
frontend typecheck/lint) are green. Schedule a review pass if shipping to prod immediately.

- [x] `docs/changelog.md`: prepend the `0.13.0`–`0.13.4` index entries + full sections.
- [x] `docs/plans/roadmap-next-steps.md`: Z3 moved to shipped; follow-ons noted; Lean gated.
- [x] `docs/plans/toolbench-catalog.md`: Z3 open threads resolved; starter-kit updated.
- [x] `docs/plans/maths-toolbox.md`: `z3.prove` in §Shipped.
- [ ] Run `/code-review` (or `review_completions`) over the slice when ready for prod push.

---

## Commands

```bash
# Phase 0
cd backend && uv add z3-solver
uv run python -c "import z3; print(z3.get_version_string())"

# Per phase
cd backend && uv run ruff check .
cd backend && uv run pytest tests/toolbench -q                 # unit + conformance (no DB needed)
TEST_DATABASE_URL=postgresql+asyncpg://…  uv run pytest tests/toolbench -q   # write-path/API (Phase 2)
cd frontend && npm run typecheck && npm run lint               # Phase 3
```

---

## Open decisions (need your call before Phase 1)

1. **Sorts in v1.** Plan proposes `int` + `real` only (LIA/LRA), deferring `bool` + in-string
   connectives (`And`/`Or`/`Not`/`Implies`) to a boolean phase — because those need a parser beyond
   the reused `split_relation`. Accept, or pull booleans into v1?
2. **Nonlinear terms.** Plan **permits** them (Z3 accepts `x*y`; result honestly degrades to
   `undecided` on the undecidable fragment). Alternative: reject nonlinear at translation time for a
   sharper "this instrument only does linear" contract. Recommend permit (honest `undecided` is the
   whole point). Your call.
3. **Unsat-core.** Include the core of the *named* hypotheses in the `result` payload (requires
   tracked assertions — a little more code), or ship v1 with a bare `"unsat"` marker and add the
   core later? Recommend include — it's the "which hypotheses did the proof actually use" signal a
   reader wants, and it's cheap with `solver.assert_and_track`.
4. **Version line.** Proposed `0.13.x` (new capability line; `0.12.5` stays reserved for budget
   metering). Confirm, or fold Z3 into a `0.12.x` point release?
