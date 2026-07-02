# Toolbench Phase 3 — Tool-Run Write Path (completion notes)

> **Status:** implemented · **Release slice:** part of `0.9.2` (Phase 3 of
> `docs/executing/toolbench-provenance-and-first-instruments.md`) · **Scope:** backend service layer
> — the OpenTheory-specific glue. **No real instruments yet** (Phase 4), **no HTTP route yet**
> (Phase 6).
>
> **What it delivers:** one service function that turns *"run instrument X with inputs Y in project
> P"* into a durable, attributed, reproducible ledger result — an `Artifact` (+ optional `Evidence`
> and the Phase-1 links) plus a `Checkpoint` carrying the blame tuple — **composed through the
> checkpoint chokepoint in one atomic transaction**. This is where Phase 1's provenance spine and
> Phase 2's adapter finally meet the ledger.

---

## 1. What changed, where, and why

### 1.1 `app/services/tool_runs.py::run_instrument(...)` (new — the whole phase)

Signature: `run_instrument(db, project_id, instrument, actor, *, inputs, assumptions=None,
thread_id=None, claim_id=None, relation_kind=None) -> ToolRunResult`.

The flow, in strict order:

1. **Validate the target claim up front** (when `claim_id` given) — 404 if missing, 400 if it
   belongs to another project, 422 if an explicit `relation_kind` is not in `{support, weaken,
   context}`. Fail fast, before anything is minted.
2. **Validate `inputs`** against `instrument.InputModel` → 422 on `ValidationError`.
3. **Run** `instrument.run(validated, assumptions)`. A tool *exception* → 422; **mint nothing**
   (this step is before any `db.add`, so the session is untouched — see §2).
4. **`db.add` the `Artifact`** (`kind = result.artifact_kind`, `content_hash` = sha256 of canonical
   output JSON, `assumptions`, output stashed in `artifact_metadata`) — **never commit**; `flush`
   to get its id.
5. **When targeting a claim**, `db.add` the `Evidence` (carrying `assumptions`, `content_hash`,
   `source_type="tool"`), the `ClaimEvidenceLink` (`relation_kind` = explicit override, else derived
   from the outcome), and the Phase-1 `EvidenceArtifactLink` (`derived_from`).
6. **Build the `ToolInvocation`** blame tuple, stamping `produced_artifact_id`.
7. **Compose through the chokepoint** — `create_checkpoint(..., extra_refs=[artifact, evidence?,
   claim?], tool_invocations=[invocation], contribution_action="tool_run")`. The chokepoint owns the
   **single commit**, so the whole graph persists (or rolls back) atomically and the one `tool_run`
   contribution is auto-recorded.

Returns `ToolRunResult` (the enriched `CheckpointRead` + `artifact_id` + `evidence_id?` + `status` +
`content_hash`).

### 1.2 `app/schemas/tool_run.py::ToolRunResult` (new)

The service return shape. Phase 6 wraps it in the HTTP response and adds the request body model; it's
introduced here so Phase 3 is self-contained and testable.

### 1.3 `app/services/contributions.py` — `ACTION_TOOL_RUN = "tool_run"`

Added to the contribution vocabulary so the act of producing a result is attributed as a
**contribution** (not a validation, not funding). The chokepoint records exactly one per run.

## 2. The two invariants this phase is really about

- **Atomicity via the chokepoint (the plan's #1 review check).** `run_instrument` `db.add`s the
  artifact/evidence/link rows and **never commits**; `create_checkpoint` performs the single commit
  for the entire graph (artifact + evidence + 2 links + checkpoint + refs + contribution). A stray
  commit here — or a `Checkpoint` minted outside the chokepoint — would break the one-transaction
  guarantee and could orphan an artifact. It does neither.
- **The failure split.** A tool *exception* means the instrument did not run → mint nothing, 4xx.
  This holds structurally because `run` executes **before any `db.add`**. A genuine **`undecided` is
  a successful run and IS recorded** — a real, citable outcome, never an error (a DB-backed test
  asserts the checkpoint + `status="undecided"` land).

## 3. Judgment calls

### 3.1 The service takes a resolved `Instrument`, not a name

`run_instrument` receives the `Instrument` object, not a string name. The Phase 6 route will resolve
the name via the registry (owning the 404-on-unknown-name), keeping the service decoupled from the
registry and trivially testable with stub instruments. This matches the plan's split (registry
lookup + 404 is a Phase 6 route concern).

### 3.2 `relation_kind`: explicit override, else derived from the outcome

The plan says "`relation_kind` from `status`: `refuted → weaken`, `result → support|context`". I made
the caller's explicit `relation_kind` win, falling back to an outcome-derived default: `refuted →
weaken`, `result → support`, **`undecided → context`** (a couldn't-decide is never auto-labelled
support or weaken). This honours both the plan's default mapping and the Phase 6 route's explicit
`relation_kind` input.

### 3.3 Content hashing is JSON-of-output → sha256

`_canonical_output_hash` hashes `json.dumps(output, sort_keys=True, separators=(",", ":"))`. Stable
for the exact/symbolic/string outputs of v1 instruments. The docstring flags the maths-toolbox
caveat: numeric instruments (Phase 4/5) must canonicalise (`srepr` / a pinned tolerance) before
hashing — **never hash a bare float**. Same hash is shared by the artifact and its evidence (they are
the same result).

### 3.4 Checkpoint refs: `artifact:produced`, `evidence:recorded`, `claim:evidenced`

Trusted `extra_refs` (not re-validated by the chokepoint, since we wrote the rows in the same txn),
mirroring the validation flow's `validated`/`recorded` roles. The claim ref makes the ledger timeline
show the checkpoint acted on that claim.

### 3.5 Evidence is created inline (not via `attach_evidence`), so a run is one contribution

`services/evidence.py::attach_evidence` commits and records its own `create_evidence` contribution.
A tool run must be **one** attributed event, so it builds the `Evidence` + links directly with
`db.add` (no commit) and lets the chokepoint own both the commit and the single `tool_run`
contribution. A run therefore yields exactly one contribution, not two.

## 4. Verification

| Check | Result |
|---|---|
| `uv run ruff check .` | **clean** |
| `uv run pytest tests/toolbench` | **12 passed / 6 skipped** |
| `uv run pytest` (full suite) | **76 passed / 86 skipped** (+3 DB-free from Phase 2's 73) |

**DB-free tests (run in the default suite — real verification of the riskiest invariant):**

- `test_engine_error_raises_422_without_touching_the_session` and
  `test_invalid_inputs_raise_422_without_touching_the_session` — a `_NoDbSession` stand-in raises on
  *any* attribute access, so these prove the failure paths mint nothing **hermetically** (if a future
  edit adds a DB call before `run`, they fail loudly). Same idea as `conftest.py`'s `_UnusableSession`.
- `test_canonical_output_hash_is_stable_and_key_order_independent` — the hash helper is deterministic
  and key-order-independent.

**DB-backed tests (skip without `TEST_DATABASE_URL` — pending a throwaway Postgres / CI):**

- no-claim run mints exactly one artifact + one checkpoint + one `tool_run` contribution; the blame
  tuple round-trips with `produced_artifact_id` stamped;
- claim-targeted run also mints one evidence, a `weaken` claim-link (refuted default), a
  `derived_from` evidence→artifact link, and the three checkpoint refs;
- an explicit `relation_kind` override is honoured;
- an `undecided` run is recorded (checkpoint + `status="undecided"`, `context` link);
- a forced engine error leaves zero artifacts / checkpoints / `tool_run` contributions.

### Not run here (honest gap)

Per the no-local-DB policy, the 5 DB-backed tests and the true end-to-end atomicity/rollback against
real Postgres are **pending** a throwaway DB or CI. The DB-free tests cover the failure split; the
atomic-commit-through-the-chokepoint path is exercised only in the DB-backed set.

## 5. Scope boundary

No real instruments (Phase 4), no `source.pin`/OEIS (Phase 5), no `GET /instruments` or
`POST …/run` route (Phase 6), no frontend (Phase 7). No Z3/Lean. No object-storage path (v1 outputs
are stored inline).

## 6. Next step — Phase 4

The first in-process SymPy instruments — `calc.eval`, `expr.compare`, `geometry.coordinate_measure`
(`uv add sympy`) — each registered into the production registry, each with one Phase-2 conformance
test and one Phase-3 write-path test. That's the first phase that ships something a human could
actually compute with, and it's where `check_conformance` and `run_instrument` stop being exercised
by stubs and start being exercised by real math.
