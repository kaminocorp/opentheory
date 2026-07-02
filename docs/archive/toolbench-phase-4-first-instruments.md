# Toolbench Phase 4 — First In-Process Instruments (SymPy, Tier 0) (completion notes)

> **Status:** implemented · **Release slice:** `0.9.2` (`calc.eval`) + `0.9.3` (`expr.compare`,
> `geometry.coordinate_measure`) of `docs/executing/toolbench-provenance-and-first-instruments.md` ·
> **Scope:** backend — the first *real* instruments, pure-Python in-process. **No HTTP route yet**
> (Phase 6), **no frontend** (Phase 7), **no OEIS/`source.pin`** (Phase 5).
>
> **What it delivers:** three deterministic maths instruments a human could actually compute with —
> `calc.eval` (exact calculator + falsification engine), `expr.compare` (equivalence, three
> outcomes), and `geometry.coordinate_measure` (the flagship *measuring across a corner*) — each
> registered into the production registry, each conformance-checked and driven end-to-end through the
> Phase-3 write path. This is where `check_conformance` and `run_instrument` stop being exercised by
> stubs and start being exercised by real math.

---

## 1. What this phase is (and is deliberately not)

Phases 1–3 built the substrate: the blame tuple on the append-only `Checkpoint` (Phase 1), the
adapter protocol + code registry + conformance harness (Phase 2), and the write path that composes a
run through the chokepoint atomically (Phase 3). Phase 4 is the first phase that adds *content* on
that substrate — but the content is deliberately thin, because "the value is not the call to SymPy;
it is the recorded, reproducible instrument around it" (the plan's framing). Each instrument is a
Pydantic `InputModel`/`OutputModel` pair plus a `run` that returns one of the three honest outcomes;
everything load-bearing — immutability, attribution, atomicity, provenance — already exists.

`uv add "sympy>=1.13"` (resolved **1.14.0**) is the only dependency added.

## 2. What changed, where, and why

All net-new except two small, anticipated edits (§2.5).

### 2.1 `app/toolbench/instruments/_sympy_support.py` (new) — the shared SymPy plumbing

Three concerns pulled out so the instruments stay thin:

- **The engine pin.** `ENGINE = "sympy"`, `ENGINE_VERSION = sympy.__version__`, read at import and
  stamped into every blame tuple. A recorded result therefore names the *exact* engine that produced
  it — the reproducibility contract the plan asks for ("pin the SymPy version in the tuple and assert
  it's recorded"). A write-path test asserts it lands verbatim.
- **A curated-namespace parser.** `parse(text, assumptions)` runs `parse_expr` restricted to an
  allow-list `_SAFE_NAMESPACE` (constructors the parser's own transformations emit —
  `Symbol`/`Integer`/`Float`/`Rational` — plus a curated math surface: `sqrt`, `sin`, `pi`, …).
  **This is not a security sandbox** (that is the deferred execution substrate,
  `agent-research-tools.md` §6); it is a cheap, honest reduction of the obvious injection vectors,
  because a bare `sympify` `eval`s against the whole SymPy namespace. A DB-free test asserts
  `__import__('os')` fails to run.
- **Assumptions → SymPy symbols.** `symbol_assumptions(...)` reads the free-form assumption map and
  extracts the *per-symbol* SymPy assumptions (`{"x": {"positive": true}}`), which `parse` binds as
  assumption-carrying `Symbol`s so a result is computed *under* them. Contextual keys
  (`{"angle": 90}`) are ignored here (still recorded on the Evidence/Artifact); a **misspelled
  predicate fails loud** — silently dropping an assumption would record a misleading unconditional
  result the append-only ledger could never edit out.

### 2.2 `app/toolbench/instruments/calc_eval.py` (new) — `calc.eval`

The primitive exact calculator, in two modes chosen by whether the input carries a top-level
relational operator (`_split_relation`):

- **value** — `2 + 2` → `4`, `1/3 + 1/6` → `1/2`, `sqrt(2)` → `sqrt(2)`: **exact, never a float**
  (the ledger hashes the output; a float is not an exact hash — the maths-toolbox caveat).
- **relation** — `3**2 + 4**2 == 5**2` holds (`result`); `5 == 7` does not (`refuted`, a
  counterexample — the asymmetrically-strong outcome); `x**2 == 2*x` cannot be decided
  (`undecided`). This is the falsification engine: exact equality over concrete values settles a
  case and reports `refuted` when false. `==`/`!=` hinge on `simplify(left-right).is_zero`;
  inequalities need a decidable sign of a concrete difference; a lone `=` is rejected ("use `==`").

### 2.3 `app/toolbench/instruments/expr_compare.py` (new) — `expr.compare`

*Are two expressions the same thing?* via `simplify(left - right)`, with the three outcomes exactly
as the plan defines them:

- difference `is_zero` → **equivalent** (`result`, kind `derivation`);
- difference `is_number` and non-zero → **not equivalent** with a witness (`refuted`, kind
  `counterexample`);
- otherwise (free symbols remain) → **unknown** (`undecided`, kind `derivation`) — the seam to
  escalate to the deferred verifier, never a pass.

The single `difference` output field carries `"0"` / the witness constant / the unreduced form, so
provenance always shows *why* the outcome is what it is. Assumptions plumb through: `√(x²)` vs `x`
is `undecided` unconditionally but `equivalent` under `{"x": {"positive": true}}` — a DB-free test
pins exactly that flip.

### 2.4 `app/toolbench/instruments/geometry_measure.py` (new) — `geometry.coordinate_measure`

The flagship demo instrument (`sympy.geometry.Point`). Given `A=[0,0]`, `B=[3,0]`, `C=[3,4]` and
requested `distances`/`angles`, it returns `dist(A,C) = 5` and `angle(A,B,C) = 90°` — **exact**: the
distance is the integer `5`, the right angle the exact `pi/2` (`90` degrees), computed via
`acos(u·v / |u||v|)` on the vertex-relative vectors. Coordinates accept exact ints / exact strings
(`"1/2"`, `"sqrt(2)"`) / floats (inexact, documented). A measurement always `result`s (it isn't
testing a claim, so `refuted`/`undecided` don't arise); a `model_validator` requires at least one
measurement and that every referenced point name exists.

### 2.5 Registration wiring (the one subtle bit)

- **`app/toolbench/instruments/__init__.py` (new)** registers the three instances into the production
  `registry`. Importing the subpackage *is* the registration (idempotent — module import is cached;
  the registry rejects duplicates/non-conforming objects).
- **`app/toolbench/__init__.py` (edited)** gains a side-effect import of the `instruments`
  subpackage, so the production registry is populated the moment anything under `app.toolbench` is
  imported. This is what the Phase-2 conformance auto-coverage test needs (it parametrizes over
  `registry.all()` **at collection time**) and what Phase 6's catalog/run endpoints will need. Import
  order within the block is irrelevant — the instrument modules import their own dependencies
  (`adapter`/`registry`) directly, so there is no cycle (verified: `from app.main import create_app`
  imports clean with SymPy now in the graph).

### 2.6 `tests/toolbench/test_conformance.py` (edited) — the empty-registry assertion flips

`test_production_registry_is_empty_but_valid` → `test_production_registry_holds_the_tier0_instruments`:
the registry is no longer empty by design, so the test now asserts the three instruments are present
and the catalog reflects them 1:1. The auto-coverage parametrization
(`test_registered_instruments_are_structurally_conformant`) consequently runs once per real
instrument instead of collecting a single "empty parameter set" skip.

## 3. Judgment calls (interpretations of the plan)

### 3.1 The plan's `calc.eval` refuted example is corrected in the tests

The plan writes "`3 + 4 == 7 → refuted`", but `3 + 4` **is** `7`, so that relation is *true*. The
implemented (and intended) semantics is: a **false** relation is `refuted`. The tests use correct
witnesses — `5 == 7` and `1/2 >= 1` refute; `3**2 + 4**2 == 5**2` and `sqrt(2) < 2` hold. The
maths-toolbox "`5 ≠ 7`" counterexample (checking `d == a+b` where `d=5, a+b=7`) is the real shape.

### 3.2 `expr.compare`'s "not equivalent" requires a *concrete* witness (a symbolic non-zero is `undecided`)

Per the plan's definition — not_equivalent = "reduces to a witness", unknown = "didn't reduce" — a
difference that stays symbolic (e.g. `x**2 - x`) is `undecided`, not `refuted`, even though the two
expressions clearly differ at some point. Hunting a falsifying substitution is
`counterexample.search`'s job (Bench 4), deliberately a different instrument. `expr.compare` stays
conservative and honest: it only refutes on a concrete non-zero difference.

### 3.3 Assumptions are per-symbol dicts; geometry records but does not consume them

`assumptions` is free-form and recorded verbatim on the Evidence/Artifact (Phase 1). The symbolic
instruments interpret entries **whose value is a dict** as SymPy per-symbol flags
(`{"x": {"positive": true}}`) and **fail loud on an unknown predicate**; non-dict entries are
contextual. `geometry.coordinate_measure` computes on concrete coordinates, so it does **not** call
`symbol_assumptions` at all — the corner thread's `angle = 90°` context rides on the artifact as
provenance, not as a SymPy flag. A write-path test asserts that context lands verbatim on
`artifact.assumptions`.

### 3.4 The safe namespace is hardening, not a sandbox

`_SAFE_NAMESPACE` blocks the obvious `__import__`/attribute-walk vectors and keeps parsing
deterministic, but it does not bound CPU/memory (a `9**9**9`-style input can still be expensive).
Resource limits are the deferred execution substrate's concern; until then these instruments are
human-invokable and Phase 6 gates them to project membership. Flagged so a reviewer doesn't mistake
the allow-list for a real sandbox.

### 3.5 Outputs are exact strings, hashed as-is (no `srepr` canonicalization yet)

Every output field is an exact string / bool / null — never a float — so the Phase-3
`json.dumps(...)→sha256` content hash is stable within a SymPy version. Cross-version `srepr`
canonicalization (the plan's dedup hedge) is **not** added: no dedup logic consumes the hash yet, and
the engine version is pinned in the tuple, so two runs on different SymPy versions are honestly
*different* provenance. The hook is noted for when dedup lands.

## 4. Verification

| Check | Result |
|---|---|
| `uv run ruff check .` | **clean** |
| `uv run pytest tests/toolbench` | **38 passed / 8 skipped** |
| `uv run pytest` (full suite) | **102 passed / 88 skipped** (+26 passed over Phase 3's 76) |
| `from app.main import create_app` | imports clean with SymPy in the graph |
| catalog serialization | all three descriptors emit JSON Schema and are JSON-serializable (Phase-6-ready) |

**The +26 passing** are the DB-free instrument tests (`tests/toolbench/test_instruments.py`) plus the
auto-coverage parametrization now running over three real instruments instead of one empty skip.

**DB-free tests (run in the default suite — the real math verification):**

- **`calc.eval`** — exact values (`4`, `1/2`, `sqrt(2)`, `^`-as-power); a true relation → `result`;
  a false relation → `refuted` counterexample; inequalities; an undecidable relation → `undecided`;
  a lone `=` rejected.
- **`expr.compare`** — equivalent (incl. `sin²+cos²=1`) → `result`; not-equivalent with witness →
  `refuted`; unknown → `undecided`; **assumptions flip the outcome** (`√(x²)=x` only under `x>0`);
  an unknown predicate fails loud.
- **`geometry`** — the corner measured exactly (`dist=5`, `angle=pi/2=90°`); exact string + 3-D
  coordinates; validators reject a missing measurement / unknown point name.
- **cross-cutting** — every instrument pins `engine_version` to the installed SymPy; every live
  `run` output validates against its declared `OutputModel`; the parse namespace blocks
  `__import__`.

### Not run here (honest gap)

Per the repo's no-local-DB / verify-against-live policy, the **3 DB-backed write-path tests**
(`tests/toolbench/test_instruments_write_path.py`) — the real instruments landing in the ledger with
the engine pinned in the blame tuple, a refuting `calc.eval` weakening a claim as a `counterexample`,
and the flagship corner recording `angle = 90°` on `artifact.assumptions` — **skip** without
`TEST_DATABASE_URL`. They are structurally identical to Phase 3's passing stub-driven write-path
tests (same fixtures, same `run_instrument` path), differing only in using real instruments; the
end-to-end atomic-commit path is exercised only in that DB-backed set. Pending a throwaway Postgres
or CI.

## 5. Scope boundary

No `source.pin`/OEIS or any HTTP instrument (Phase 5). No `GET /instruments` or
`POST …/run` route (Phase 6). No frontend drive/show surfaces (Phase 7). No Z3/Lean, no physics
tools, no `numeric.*`/`interval.*` (the v1 SymPy instruments here are exact), no object-storage
artifact path.

## 6. Next step — Phase 5

`source.pin` + `oeis.search` (Tier 1): the first read-only HTTP instrument and the reusable pinning
primitive — retrieval evidence that carries `url` + `retrieved_at` + `raw_response_hash`, tested
against a **mocked** OEIS response (no live network in CI). It is the first instrument whose output
is *not* a pure function of its inputs, so its determinism contract shifts to "the pinned record
reproduces what was retrieved."

**Release/deploy follow-ups** (not done here, matching Phases 1–3): the `0.9.2`/`0.9.3` entries in
`docs/changelog.md` and `fly deploy` belong to the release step, once the DB-backed write-path
verification is greenlit.
