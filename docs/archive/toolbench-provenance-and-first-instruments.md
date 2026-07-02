# Toolbench — Provenance Spine & First Instruments

> Build the **provenance spine** for the maths toolbench and the **first deterministic
> instruments** on top of it. An instrument takes typed inputs, runs deterministically, and
> returns a result the append-only ledger can hold — **always recorded against the instrument
> that derived it** (the blame tuple `(tool, version, inputs) → output` + assumptions). This plan
> turns the agreed design in `docs/plans/maths-toolbox.md` (the v1 instrument set) and
> `docs/plans/toolbench-catalog.md` (the buildable bench, sorted by integration cost) into
> methodical, shippable phases.

## Goal

A human can stand in a project workspace, run a deterministic maths instrument (e.g. *compare two
expressions*, *evaluate exactly*, *measure across a corner*, *look up a sequence*), and have the
result land in the ledger as a durable **`Artifact`** — optionally minting **`Evidence`** against a
`Claim` — with a **validated blame tuple** recorded on the append-only `Checkpoint` that captures
*which instrument + version + inputs + assumptions* produced it. Everything composes through the
existing checkpoint chokepoint; nothing writes the ledger directly.

The acceptance bar for the whole line: **point at any tool-produced result in the ledger and
reconstruct exactly how it was made** — the instrument, its version, the engine + engine version,
the inputs, the assumptions — and re-run it to the same answer.

## Why this is a data-model change first, not "a SymPy wrapper"

The value is not the call to SymPy; it is the **recorded, reproducible instrument around it**. So the
load-bearing work is the provenance record and the write path that keeps it immutable and attributed
— the instruments themselves are thin once the spine exists. The build order reflects that: spine →
adapter interface → write-path glue → instruments → surface.

This also stays inside OpenTheory's standing invariants (`CLAUDE.md`, `docs/primitives.md`):

| Invariant | How this line honours it |
|---|---|
| One write path for the ledger | Every tool run composes with `services/checkpoints.py` (`create_checkpoint`), never mints its own `Checkpoint`. |
| Append-only is ORM-enforced | The blame tuple rides on the append-only `Checkpoint`, so its immutability is free — not on the mutable `Artifact`. |
| Record only the irreversible facts | We store the blame tuple + assumptions; *exact / approximate / retrieved* and any future grade stay **derivable** from the recorded instrument, never stamped. |
| Funding ≠ contribution ≠ validation | A tool run records a **contribution** (the act of producing a result); it is not validation and not funding. |
| Human-first | Each instrument ships as a human-invokable workspace action **before** any agent drives it through the same API. |

## Decisions (locked before planning)

These were converged on in design discussion and are not re-litigated mid-build:

1. **The blame tuple is the spine.** Every result records `instrument, instrument_version, engine,
   engine_version, inputs, output, assumptions, status`. That plus assumptions is the *only*
   mandatory per-result record.
2. **It lives as a validated JSON shape on `Checkpoint.tool_invocations` — not a new table** (the
   field already exists as free-form JSON; we promote it to a validated Pydantic shape). Rationale:
   immutability comes free from the append-only `Checkpoint`, and it is literally what
   `maths-toolbox.md` and `research-git.md` already plan. Promotion to a dedicated
   `tool_invocations` table is **deferred** until cross-invocation audit queries (“all results from
   SymPy 1.13”) demand it.
3. **The instrument registry lives in CODE, not the database.** Instruments + their input/output
   schemas + result contract are the adapters themselves, served read-only over an endpoint —
   exactly the `core/openrouter_models.py` → `GET /agent-models/catalog` pattern. A DB table would be
   a second source of truth that drifts from the code that runs.
4. **No `engines` / `libraries` table.** `engine` + `engine_version` are fields in the tuple.
5. **Links are typed join tables, matching the existing idiom — never single FKs.** `Claim↔Evidence`
   already exists (`ClaimEvidenceLink`, `support/weaken/context`). The real gap to add is
   **`Evidence→Artifact`** (a typed join, “one or more”). `Checkpoint→artifact/evidence/claim`
   already exists (`CheckpointRef`).
6. **Assumptions ride on the `Evidence`/`Artifact`,** captured at write-time and surfaced on the
   evidence card — an unconditional claim recorded without its assumptions is a lie the append-only
   ledger can never edit out.
7. **The adapter interface is the real build object.** `expr.compare` / `calc.eval` /
   `oeis.search` / `geometry.coordinate_measure` are its first conformance tests. The contract has
   three honest outcomes: **ran→result / ran→refuted / couldn’t-decide**.

## Out of scope (explicitly)

- **Verifier layer — Z3, Lean.** Deferred. `counterexample.search` covers cheap local falsification
  without Z3; Lean forces the execution substrate (`agent-research-tools.md` §6) and stays far out.
- **Physics tools** (units/dimensions, constants, statistics, tensors), **heavy compute**
  (DFT/MD/PDE/FEM, a GPU/HPC job service) — math-first; deferred.
- **A stored grade / result-kind field** — derivable from the recorded instrument; not stamped.
- **An `instruments` DB table and an `engines` DB table** — code registry + tuple fields instead
  (Decisions 3, 4).
- **A dedicated `tool_invocations` table** — validated JSON on `Checkpoint` first (Decision 2).
- **Agent execution.** Agents are not wired here; the surface is human-invokable. Agents later drive
  the *same* API.
- **Object-storage write path for large artifacts.** v1 instruments produce small results stored
  inline; the URI/object-storage path for big artifacts is a later concern.

## Global conventions (apply in every phase)

- **Compose with the chokepoint.** A tool-run service `db.add(...)`s its `Artifact`/`Evidence`/link
  rows to the caller’s session and never commits, then calls `create_checkpoint(..., extra_refs=[…],
  tool_invocations=[…], contribution_action=…)`. The chokepoint owns the single `commit`; the whole
  flow is one atomic transaction (the validation/branch composition pattern).
- **`extra_refs` are trusted, client `payload.refs` are validated.** The tool-run service validated
  the rows it just wrote in the same transaction, so it passes them as trusted `extra_refs`.
- **Pin versions, canonicalize before hashing.** Record `engine_version` in the tuple; canonicalize
  expressions via `srepr` (`expr.normalize`) before hashing for dedup — `simplify()` heuristics
  drift across SymPy versions. Force `OMP_NUM_THREADS=1` for any numeric instrument when bit-identity
  is asserted; never treat a float as an exact hash.
- **Every new model is exported from `models/__init__.py`** — Alembic’s `env.py` does
  `from app.models import *`; a model missing from `__all__` is silently absent from autogenerated
  migrations.
- **New enums are named Postgres types** in `models/enums.py` (`Enum(X, name="...")`); keep `name=`
  stable. Metadata columns stay `<entity>_metadata`.
- **Writes resolve the acting actor** via the `ActingActor` dependency (`api/deps.py`) and pass it
  down so the service attributes the `Contribution`.
- **Human-first.** Every instrument is a workspace action a person can run before any agent does.

## Provenance shapes (the contract Phases 1–2 build)

The blame tuple, as a validated Pydantic model (Phase 1):

```python
# schemas/tool_invocation.py
class ResultStatus(StrEnum):          # the three honest outcomes
    result    = "result"              # ran → produced a result
    refuted   = "refuted"             # ran → falsified the claim (a counterexample, 5 ≠ 7)
    undecided = "undecided"           # ran → could not decide (escalate to a proof later)

class ToolInvocation(BaseModel):      # one entry in Checkpoint.tool_invocations
    instrument: str                   # "geometry.coordinate_measure"
    instrument_version: str           # "0.1.0"  (our adapter version)
    engine: str                       # "sympy"
    engine_version: str               # "1.13.2" (pinned, for reproduction)
    inputs: dict[str, Any]            # the exact validated inputs
    output: dict[str, Any]            # the result (a number carries its own tolerance/bound)
    assumptions: dict[str, Any] = {}  # what it was computed under (x>0, angle=90°)
    status: ResultStatus
    produced_artifact_id: UUID | None = None
```

The adapter interface, as a protocol every instrument conforms to (Phase 2):

```python
# toolbench/adapter.py
class InstrumentResult(BaseModel):
    output: dict[str, Any]
    status: ResultStatus
    artifact_kind: str                # "derivation" | "counterexample" | "measurement" | ...

class Instrument(Protocol):
    name: str                         # "expr.compare"
    namespace: str                    # "expr"
    version: str                      # adapter version
    engine: str
    engine_version: str
    InputModel: type[BaseModel]       # validates + JSON-Schema's the inputs
    OutputModel: type[BaseModel]
    def run(self, inputs: BaseModel, assumptions: dict[str, Any]) -> InstrumentResult: ...
```

---

## Phase 1 — Provenance spine (data model)

**Goal:** the ledger can hold a validated blame tuple and link evidence to the artifact a tool
produced, with assumptions captured at write-time. No instruments yet.

**Tasks**

1. **`ToolInvocation` + `ResultStatus`** (`schemas/tool_invocation.py`, `models/enums.py`). The
   validated shape above. `ResultStatus` is a named PG enum **only if** it ever becomes a column;
   while it lives inside the JSON tuple it is a plain `StrEnum` serialized as a string.
2. **Promote `Checkpoint.tool_invocations` to the validated shape.** Column stays `JSON`
   (`checkpoint.py:61`); validation moves into the checkpoint **schema** + service: on write, each
   entry must parse as `ToolInvocation`. Reads stay lenient (a historical entry that predates the
   shape must not `500` a project read) — mirror the `AgentModels` lenient-read / strict-write split
   from `0.8.10`.
3. **`EvidenceArtifactLink`** (`models/links.py`) — typed many-to-many, “one or more”, matching
   `ClaimEvidenceLink`: `evidence_id`, `artifact_id`, `role` (plain string validated in the service
   layer; allowed `derived_from`, `attachment`; PG-enum promotion deferred). `UniqueConstraint`
   on `(evidence_id, artifact_id, role)`. Export from `models/__init__.py`; add the
   `Evidence.artifact_links` / `Artifact.evidence_links` relationships.
4. **`assumptions` on `Evidence` and `Artifact`** — a dedicated nullable `JSON` column (default
   `{}`), not buried in `*_metadata`, so it is honestly surfaced on the evidence card. Validated as
   a free-form object in v1 (SymPy-style assumption keys: `positive`, `integer`, `nonzero`, …).
5. **Migration `0012_toolbench_provenance`** (additive, `down_revision="0011_project_agent_models"`):
   create `evidence_artifact_links`; add `evidence.assumptions` + `artifacts.assumptions`. No change
   to `checkpoints.tool_invocations` (already present). `alembic heads` stays single + linear.
6. **Append-only check.** Confirm the blame tuple inherits immutability via the append-only
   `Checkpoint` guard (no new guard needed). `EvidenceArtifactLink` mirrors `ClaimEvidenceLink` —
   **not** append-only-guarded (links can be created/cascaded like the existing one).

**Deliverable / demoable:** a DB-backed test writes a checkpoint carrying a valid `ToolInvocation`
and rejects a malformed one; an `Evidence` links to an `Artifact` and carries assumptions.

**Verification:** `uv run ruff check . && uv run pytest` (DB-backed cases need `TEST_DATABASE_URL`);
`alembic upgrade head` then `downgrade` round-trips clean.

---

## Phase 2 — Adapter interface, registry, conformance harness (the real build object)

**Goal:** a single shape every instrument conforms to, a **code** registry that enumerates them, and
a conformance test that any registered instrument must pass. Still no instruments shipped.

**Tasks**

1. **`toolbench/adapter.py`** — the `Instrument` protocol + `InstrumentResult` (shapes above). The
   three-outcome `status` is part of the return, not inferred.
2. **`toolbench/registry.py`** — a code registry (decorator or explicit dict) mapping
   `name → Instrument`. This is the single source of truth (Decision 3); nothing persists it.
3. **Registry → catalog serializer** — turn each instrument into a read-only descriptor: `name`,
   `namespace`, `description`, `input_schema` (JSON Schema from `InputModel.model_json_schema()`),
   `output_schema`, `result_contract`. This is what the UI/agent-API consume.
4. **Conformance harness** (`tests/toolbench/test_conformance.py`) — parametrized over the registry:
   every instrument has a non-empty `name`/`namespace`/`version`/`engine`/`engine_version`, Pydantic
   `InputModel`/`OutputModel`, and a `run` returning a valid `InstrumentResult`. Instruments register
   themselves *into* this harness; it is the contract’s executable definition.

**Deliverable / demoable:** the registry is empty-but-valid; the harness is green; the catalog
serializer produces JSON Schema for a toy fixture instrument.

**Verification:** `uv run pytest tests/toolbench` (no DB needed — pure in-process).

---

## Phase 3 — Write path: a tool run, composed through the chokepoint

**Goal:** the OpenTheory-specific glue. One service turns *“run instrument X with inputs Y in project
P”* into `Artifact` (+ optional `Evidence` + links) + a `Checkpoint` carrying the blame tuple — in
one transaction, attributed to the acting actor.

**Tasks**

1. **`services/tool_runs.py::run_instrument(...)`**:
   - validate `inputs` against `instrument.InputModel`;
   - `instrument.run(inputs, assumptions)` → `InstrumentResult`;
   - `db.add(...)` an `Artifact` (`kind = result.artifact_kind`; `content_hash` of the canonical
     output; `assumptions`); **never commit**;
   - if a target `claim_id` is supplied: `db.add(...)` an `Evidence` (carrying `assumptions`), its
     `ClaimEvidenceLink` (`relation_kind` from `status`: `refuted → weaken`, `result → support|context`),
     and an `EvidenceArtifactLink` (`derived_from`);
   - build the `ToolInvocation` (stamping `produced_artifact_id`);
   - call `create_checkpoint(..., extra_refs=[artifact, evidence?], tool_invocations=[invocation],
     contribution_action="tool_run")` — the chokepoint owns the single commit.
2. **Contribution vocabulary** — add `tool_run` to the allowed `contribution_action` set so the act
   of producing a result is attributed (a contribution, not a validation).
3. **Failure semantics** — a tool *exception* (didn’t run) does **not** mint a checkpoint or an
   artifact; it surfaces as a `4xx`/`5xx`. `undecided` is a *successful run* and **is** recorded
   (it’s a real, citable outcome). Encode this split in the service, not the route.
4. **Tests** (`tests/toolbench/test_write_path.py`, DB-backed) — a run with no claim mints
   artifact+checkpoint+contribution atomically; a run targeting a claim also mints evidence + both
   links; a forced engine error rolls back *everything* (no orphan artifact).

**Deliverable / demoable:** a unit/integration test runs a stub instrument end-to-end and the ledger
shows a durable, attributed, reproducible result.

**Verification:** `uv run pytest` against `TEST_DATABASE_URL`; assert one `Checkpoint`, one
`Contribution`, the blame tuple round-trips, and the error case leaves zero rows.

---

## Phase 4 — First in-process instruments (SymPy, Tier 0)

**Goal:** the starter kit’s compute + flagship instruments, all pure-Python in-process
(`uv add sympy`). Each is one conformance test against Phase 2 and one write-path test against
Phase 3.

**Tasks**

1. **`calc.eval`** — primitive exact calculator: arithmetic, powers, roots, exact equality
   (`3**2 + 4**2 == 5**2 → result:true`; `3 + 4 == 7 → refuted`). The falsification engine; ships
   first because it’s the thinnest.
2. **`expr.compare`** — `simplify(left - right)` with the **three** outcomes: `equivalent`
   (difference → `0` → `result`), `not_equivalent` (→ a witness → `refuted`), `unknown` (didn’t
   reduce → `undecided`, the signal to escalate to a deferred proof). The workbench’s core verb.
3. **`geometry.coordinate_measure`** (`sympy.geometry`) — distances + angles between given points
   (`A=[0,0],B=[3,0],C=[3,4] → dist(A,C)=5, angle(A,B,C)=90°`). The flagship-demo instrument
   (*measuring across a corner*).
4. **Assumptions plumbing** — each `InputModel` accepts an assumption set mapped to SymPy native
   assumptions (`Symbol('x', positive=True)`); the result is computed *under* it and the set is
   recorded on the Evidence/Artifact (Phase 1).

**Deliverable / demoable:** three real instruments runnable through the write path; the “measuring
across a corner” result lands as an `Artifact` with its `angle=90°` assumption recorded.

**Verification:** conformance + write-path tests per instrument; pin the SymPy version in the tuple
and assert it’s recorded.

---

## Phase 5 — Retrieve + pin (OEIS, Tier 1)

**Goal:** the first read-only HTTP instrument and the reusable **pinning** primitive — retrieval
evidence that is solid, not flimsy.

**Tasks**

1. **`source.pin`** — the Tier-1 pattern: given a provider response, persist a citable record
   carrying `url`, `retrieved_at`, `terms`, `formula`, `license_note`, `raw_response_hash`. Lands as
   an `Artifact` (kind `pinned_source`) and, against a claim, an `Evidence` (`source_type` set, the
   pin fields on the evidence). **Mutable-source caveat:** record retrieval time + content hash.
2. **`oeis.search`** — terms → A-number + formula (`1,1,2,3,5,8 → A000045`), wrapped in
   `source.pin`. OEIS license: **cite, don’t redistribute** — store the pin record, not a bulk copy.
3. **HTTP + cache layer** — an outbound client with a small response cache keyed by query; no code
   execution, no new infra (runs in the FastAPI process). `retrieved_at` is real-time, so this is
   the first instrument whose output is *not* a pure function of inputs — its determinism contract is
   “the pinned record reproduces what was retrieved,” not “re-running returns identical bytes.”

**Deliverable / demoable:** look up Fibonacci by its terms; the ledger holds a pinned, cited
`Evidence`/`Artifact` with the A-number as the pin.

**Verification:** conformance + write-path tests with a **mocked** OEIS response (no live network in
CI); assert the pin record carries `raw_response_hash` + `retrieved_at`.

---

## Phase 6 — Human-invokable API surface

**Goal:** the instruments are usable from the product, human-first, through the same API an agent
will later use.

**Tasks**

1. **`GET /instruments`** — public, root-mounted, read-only catalog from the Phase-2 serializer
   (the `GET /agent-models/catalog` pattern): each instrument’s name, namespace, description, input
   schema, output schema, result contract. Static reference data; cache indefinitely.
2. **`POST /projects/{id}/instruments/{name}/run`** — body: `inputs`, `assumptions`, optional
   `thread_id`, optional `claim_id` + `relation_kind`. Declares the `ActingActor` dependency; gated
   to project membership (reuse `ensure_can_manage`/member check). Calls `services/tool_runs.py` and
   returns the produced `Artifact` (+ `Evidence` + `Checkpoint` summary).
3. **Schemas** (`schemas/tool_run.py`) — request/response read models (`from_attributes=True`),
   surfacing the blame tuple + assumptions on the response so the frontend can render provenance.
4. **Tests** — the unauthenticated `POST .../run` → `401` (DB-free auth-gate regression, matching the
   `0.6.5` pattern); the catalog endpoint shape; an unknown instrument name → `404`; a bad-inputs
   body → `422`.

**Deliverable / demoable:** `curl` the catalog; run `calc.eval` over the API as a signed-in member
and see the checkpoint appear in the ledger.

**Verification:** `uv run pytest` (auth-gate + catalog cases run DB-free; the full round-trip needs
`TEST_DATABASE_URL` or the live deploy).

---

## Phase 7 — Frontend workspace actions + render surfaces

**Goal:** every instrument gets two columns — **drive** (input affordance) and **show** (render
surface) — wired through the typed API client, in the Kamino Console language. (May spin into its own
frontend plan if it grows; scoped here as the closing slice.)

**Tasks**

1. **Plumbing** — `lib/api.ts`: `getInstrumentCatalog` / `runInstrument`; `types/` for the catalog
   descriptor, the blame tuple, and the run response; a `instrumentCatalog` query key (cached
   indefinitely — static).
2. **Drive surfaces** — per instrument: a formula field (`expr.compare`, `calc.eval`), a point editor
   (`geometry.coordinate_measure`), a terms box (`oeis.search`); an **assumptions** input that is
   visibly part of the record, not a hidden flag.
3. **Show surfaces** (the reusable render library) — formula card (**KaTeX**), **counterexample
   card** (the asymmetric `5 ≠ 7` result, rendered as the strong outcome it is), citation card (the
   pinned source), and later a table (Vega-Lite is deferred with `plot.*`). Each card surfaces the
   blame tuple + assumptions so provenance is *visible*, not buried.
4. **Honesty rules in the UI** — `undecided` renders as “couldn’t decide → escalate,” never as a
   pass; “no counterexample found after N” renders as *weak support*, never “proven” (keep the search
   space + N visible).

**Deliverable / demoable:** run the flagship *measuring across a corner* thread end-to-end from the
workspace; the result card shows the measurement, its `angle=90°` assumption, and the
`geometry.coordinate_measure@0.1.0 · sympy@x.y.z` blame line.

**Verification:** `npm run typecheck && npm run lint && npm run build`; manual signed-in round-trip on
the live deploy.

---

## Release slicing (small, deployable/demoable phases)

Mapping the build order onto the repo’s `0.x.y` convention. Phases 1–2 are backend-internal
foundations; the first *demoable* ship bundles the write path + one instrument + its API.

| Release | Phases | Demoable outcome |
|---|---|---|
| `0.9.1` | 1 | Ledger holds a validated blame tuple + evidence→artifact links + assumptions. |
| `0.9.2` | 2 + 3 + 4(`calc.eval`) + 6(run/catalog for it) | Run `3²+4²==5²` over the API → durable, attributed, reproducible result. |
| `0.9.3` | 4 (`expr.compare`, `geometry.coordinate_measure`) | The flagship *corner* measurement in the ledger. |
| `0.9.4` | 5 | Sequence lookup → pinned, cited evidence. |
| `0.9.5` | 7 | The drive/show workspace surfaces (the toolbench’s frontend component library). |

Each row updates `docs/changelog.md` on completion (per `CLAUDE.md` conventions).

## Risks & watch-items

- **Lenient-read vs strict-write on `tool_invocations`.** A pre-shape or future-shape entry must
  never `500` a project read. Pin the read path to be lenient (the `AgentModels` precedent); only the
  write path rejects malformed tuples.
- **Float reproducibility.** Numeric instruments are not bit-reproducible across BLAS/SIMD/thread
  count. Don’t assert bit-identity without `OMP_NUM_THREADS=1`; never use a float as a content hash.
  (Phase 4/5 — relevant once `numeric.*` lands; the v1 SymPy instruments are exact.)
- **`simplify()` drift.** SymPy `simplify` heuristics change across versions — record `engine_version`
  and canonicalize via `srepr` before hashing, or dedup breaks silently across an upgrade.
- **OEIS / mutable-source pinning.** Cite, don’t redistribute; the pin must carry `retrieved_at` +
  `raw_response_hash` so the record reproduces what was seen, not what the source says *now*.
- **Atomicity.** The tool-run service must `db.add` and let the chokepoint commit — a stray commit (or
  minting a `Checkpoint` outside `create_checkpoint`) breaks the one-transaction guarantee and can
  orphan an artifact. This is the single most important review check on Phase 3.
- **Scope creep into the verifier.** `expr.compare`’s `unknown` is the *seam* to Z3/Lean, not an
  invitation to build them now. Record it honestly and stop.

## Verification per phase

| Phase | Backend | Frontend | DB |
|---|---|---|---|
| 1 | `ruff` + `pytest` (shape + link tests) | — | `alembic up/down` round-trip; `TEST_DATABASE_URL` for link/assumption tests |
| 2 | `pytest tests/toolbench` (conformance) | — | none (in-process) |
| 3 | `pytest` (atomic write-path + rollback) | — | `TEST_DATABASE_URL` |
| 4 | `pytest` (conformance + write-path per instrument) | — | `TEST_DATABASE_URL` |
| 5 | `pytest` (mocked OEIS; pin record) | — | `TEST_DATABASE_URL` |
| 6 | `pytest` (auth-gate DB-free; catalog; round-trip) | — | partial (auth-gate DB-free; round-trip needs DB) |
| 7 | — | `typecheck` + `lint` + `build` | live-deploy round-trip |
