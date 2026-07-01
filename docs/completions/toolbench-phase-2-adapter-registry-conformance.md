# Toolbench Phase 2 — Adapter Interface, Registry, Conformance (completion notes)

> **Status:** implemented · **Release slice:** part of `0.9.2` (Phase 2 of
> `docs/executing/toolbench-provenance-and-first-instruments.md`) · **Scope:** backend, pure
> in-process — **no DB, no API, no frontend, and still no instruments shipped.**
>
> **What it delivers:** the *single shape every instrument conforms to* (the adapter protocol), a
> **code** registry that enumerates instruments as the single source of truth, a serializer that
> turns the registry into a JSON-Schema catalog for the UI/agent API, and a **conformance checker**
> that is the contract's executable definition. Proven end-to-end with a toy fixture instrument; the
> production registry is deliberately **empty-but-valid**.

---

## 1. Why this is "the real build object"

Per the plan's Decision 7, the adapter interface — not any individual instrument — is the reusable
thing being built. `calc.eval` / `expr.compare` / `oeis.search` / `geometry.coordinate_measure` are
its first *conformance tests*, arriving in Phase 4. Phase 2 builds the contract and the machinery
around it so that, from Phase 4 on, adding an instrument is "implement the protocol + one conformance
test", nothing structural.

## 2. What changed, where, and why (all net-new; nothing modified)

Phase 2 is purely additive — a new `app/toolbench/` package plus one schema and one test suite. No
existing file was touched.

### 2.1 `app/toolbench/adapter.py` — the contract

- **`InstrumentResult(BaseModel)`** — `output: dict`, `status: ResultStatus`, `artifact_kind: str`
  (`min_length=1`, `extra="forbid"`). `status` is **returned by the instrument, never inferred**;
  `artifact_kind` lives on the *result* (not the instrument) because one instrument yields different
  kinds per run — e.g. `expr.compare` → `derivation` when equivalent, `counterexample` when refuted.
- **`Instrument(Protocol)`, `@runtime_checkable`** — the exact shape from the plan
  (`name`, `namespace`, `version`, `engine`, `engine_version`, `InputModel`, `OutputModel`,
  `run(inputs, assumptions) -> InstrumentResult`) **plus `description`** (see §3.1). A `Protocol`
  means an instrument is *any* object with the right shape — no base class to inherit. `runtime_checkable`
  is what lets the registry reject a non-conforming object at registration time.

### 2.2 `app/toolbench/registry.py` — the code registry (Decision 3)

- **`InstrumentRegistry`** — a `name → Instrument` map that **fail-fasts** on a blank name, an object
  that fails the `Instrument` protocol (`isinstance` gate), or a duplicate name. `all()` returns
  instruments **name-ordered** for stable catalog/test output; `__contains__` / `__len__` /
  `__iter__` provided.
- **`registry`** — the module-level production singleton, **empty in Phase 2**. Phase 4 registers the
  first real instruments into it. It's a *class* with a singleton rather than a bare module dict
  precisely so tests can spin up throwaway registries without polluting production (see §3.2).

### 2.3 `app/schemas/instrument.py` — the catalog descriptor

- **`InstrumentDescriptor`** — `name`, `namespace`, `version`, `engine`, `engine_version`,
  `description`, `input_schema` / `output_schema` (real JSON Schema from
  `model_json_schema()`), `result_contract`. This is the read model the UI/agent API (Phase 6)
  serves — the `ModelOptionRead` precedent.
- **`ResultContractOutcome`** — one `{status, meaning}` pair; the descriptor carries all three
  (the contract is universal), so a client reads one entry and knows how to render each outcome —
  including that `undecided` must render as "escalate", never a pass.

### 2.4 `app/toolbench/catalog.py` — registry → descriptors

- **`describe(instrument)`** builds one descriptor; **`build_catalog(registry=production)`** maps the
  whole registry. `RESULT_CONTRACT` is the single constant tuple of the three universal outcomes,
  attached to every descriptor. Reflecting the *code* registry means the catalog can never advertise
  an instrument the runtime doesn't actually have.

### 2.5 `app/toolbench/conformance.py` — the executable contract

- **`check_conformance(instrument, *, example_inputs=None, assumptions=None) -> list[str]`** returns
  a list of problems (empty ⇒ conforms). Two layers:
  - **structural** (always): the six required non-empty string attrs; `name` is a real
    `namespace.verb`; `InputModel`/`OutputModel` are `BaseModel` subclasses that emit JSON Schema.
  - **behavioural** (only with `example_inputs`): validate the inputs → call `run` → assert it
    returns an `InstrumentResult` → **assert `result.output` validates against the declared
    `OutputModel`** (Pydantic does *not* enforce this on its own, since `InstrumentResult.output` is
    a free-form dict — this is the check that keeps an instrument's advertised output schema honest).
- It returns problems (rather than raising or using pytest) so it's callable from a test
  (`assert check_conformance(...) == []`) **and** from any non-test caller. It lives in **production
  code, not the test tree**, so Phase 4's per-instrument tests import it directly.

### 2.6 `tests/toolbench/test_conformance.py` — the harness

A toy `demo.echo` instrument (test-only, never registered into production) drives the machinery:
the toy satisfies the protocol and passes full conformance; a deliberately-broken object is flagged;
a "liar" whose `run` output violates its own `OutputModel` is caught; the registry
register/get/duplicate/ordering/reject-nonconforming behaviours hold; the catalog serializes the toy
to real JSON Schema with the three-outcome contract; and a parametrized test over the **production**
registry auto-covers every future instrument (empty now → one designed skip).

## 3. Judgment calls (interpretations of the plan)

### 3.1 Added `description` to the `Instrument` protocol

The plan's protocol snippet omits `description`, but its catalog-serializer task lists `description`
as a descriptor field. An instrument must therefore carry one, so I added `description: str` to the
protocol. Minor, and strictly required by the serializer.

### 3.2 Registry as a class + singleton (not a module-global dict or a decorator-only API)

The plan allows "decorator or explicit dict". I chose an `InstrumentRegistry` **class** with a
`registry` singleton because (a) it makes the production registry's *emptiness* testable in isolation
while tests use throwaway registries, and (b) `register()` returning the instrument still supports the
decorator ergonomics Phase 4 may want (`registry.register(CalcEval())`). No global mutable state leaks
between tests.

### 3.3 `check_conformance` returns problems; lives in production code

The plan names `tests/toolbench/test_conformance.py`. I kept the *test* there but extracted the
reusable checker into `app/toolbench/conformance.py` so Phase 4's per-instrument tests import it
without test-package import gymnastics — and so a non-test caller (a future admin/health check, or
`register()` itself) could reuse it. Returning a `list[str]` rather than raising keeps it
framework-agnostic.

### 3.4 `result_contract` is universal, surfaced per descriptor

Every instrument can in principle return any of the three outcomes, so the same three
`ResultContractOutcome`s ride on every descriptor rather than each instrument declaring a subset.
This keeps each catalog entry self-contained for the UI. If a later need arises to say "this
instrument never returns `undecided`", that becomes a per-instrument narrowing — not needed now.

## 4. Verification

Pure in-process — **fully verified locally, no deferred DB checks** (unlike Phase 1).

| Check | Result |
|---|---|
| `uv run ruff check .` | **clean** |
| `uv run pytest tests/toolbench -v` | **9 passed / 1 skipped** (the skip is the empty-registry auto-coverage parametrization — "empty-but-valid") |
| `uv run pytest` (full suite) | **73 passed / 81 skipped** (+9 from Phase 1's 64; the +1 skip is the designed empty-parametrize) |

**What the tests prove:** the adapter protocol is satisfiable and `runtime_checkable`; conformance
catches structural violations *and* an output-schema liar; the registry fail-fasts on
duplicate/non-conforming and orders by name; the catalog emits real JSON Schema plus the three-outcome
contract; and the production registry is empty-but-valid with an empty catalog.

## 5. Scope boundary (what Phase 2 did **not** do)

No `services/tool_runs.py` write path (Phase 3), no real instruments (Phase 4), no `source.pin`/OEIS
(Phase 5), no `GET /instruments` or `POST …/run` endpoints (Phase 6), no frontend (Phase 7). No Z3/Lean.

## 6. Next step — Phase 3

`services/tool_runs.py::run_instrument(...)` — the OpenTheory-specific glue that turns *"run
instrument X with inputs Y in project P"* into an `Artifact` (+ optional `Evidence` + the
`EvidenceArtifactLink` from Phase 1) and a `Checkpoint` carrying the blame tuple, **composed through
the checkpoint chokepoint in one transaction** (the single most important review check: `db.add` and
let `create_checkpoint` own the one commit — a stray commit or a Checkpoint minted outside the
chokepoint breaks atomicity and can orphan an artifact). It also adds `tool_run` to the allowed
`contribution_action` vocabulary and encodes the failure split: a tool *exception* mints nothing;
an `undecided` is a successful, recorded run. This is where Phase 1's spine and Phase 2's adapter
meet the ledger.
