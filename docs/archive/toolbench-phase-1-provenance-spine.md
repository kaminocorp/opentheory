# Toolbench Phase 1 — Provenance Spine (completion notes)

> **Status:** implemented · **Release slice:** `0.9.1` (Phase 1 of
> `docs/executing/toolbench-provenance-and-first-instruments.md`) · **Scope:** backend data-model
> only — no instruments, no write-path service, no API, no frontend.
>
> **What it delivers:** the ledger can now hold a **validated blame tuple** on a checkpoint, **link
> evidence to the artifact a tool produced**, and **carry the assumptions** a result was computed
> under — the three irreversible provenance facts, captured so that *"point at any tool-produced
> result and reconstruct exactly how it was made"* becomes possible in later phases. No instrument
> runs yet; this is the substrate they land on.

---

## 1. The goal for this phase (from the plan)

Phase 1 is deliberately a **data-model change first, not "a SymPy wrapper."** The value of the
toolbench is the *recorded, reproducible instrument*, so the load-bearing work is the provenance
record and the write path that keeps it immutable and attributed. This phase builds the record; the
write path (Phase 3) and the instruments (Phase 4+) are thin once the spine exists.

Concretely, Phase 1 had to make three things storable:

1. a **blame tuple** — `(instrument, instrument_version, engine, engine_version, inputs, output,
   assumptions, status)` — validated on write, lenient on read;
2. a typed **`Evidence → Artifact`** link (the one genuinely missing join);
3. **`assumptions`** on both `Evidence` and `Artifact`, captured at write-time.

## 2. Invariants honored (why the shape is what it is)

| Invariant | How Phase 1 honors it |
|---|---|
| One write path for the ledger | The blame tuple is passed *into* `create_checkpoint` as a trusted kwarg; nothing new mints a `Checkpoint`. |
| Append-only is ORM-enforced | The tuple rides on the append-only `Checkpoint`, so its immutability is **free** — no new guard. Verified by a test that tampering with `checkpoint.tool_invocations` raises `AppendOnlyError`. |
| Record only the irreversible facts | We store the tuple + assumptions. *Exact / approximate / retrieved* and any future grade stay **derivable** from the recorded instrument — never stamped. Enforced by `extra="forbid"` on the tuple (a stray `grade` key is rejected). |
| Funding ≠ contribution ≠ validation | Nothing here touches `FundingAllocation` / `Validation`. (The `tool_run` *contribution action* is a Phase 3 concern and was intentionally **not** added yet.) |
| Links are typed join tables, never single FKs | `EvidenceArtifactLink` mirrors `ClaimEvidenceLink` exactly. |

## 3. What changed, where, and why

### 3.1 The blame tuple — `ResultStatus` + `ToolInvocation`

- **`app/models/enums.py` — `ResultStatus(StrEnum)`** = `result | refuted | undecided` (the three
  honest outcomes: *ran→result / ran→refuted / couldn't-decide*). It is a **plain `StrEnum`, not a
  named Postgres enum**, because it lives *inside* the JSON tuple, not as a column — promotion to a
  PG type is deferred until (and only if) it ever becomes a column. `undecided` is the documented
  seam to escalate to the deferred verifier (Z3/Lean), never rendered as a pass.
- **`app/schemas/tool_invocation.py` — `ToolInvocation(BaseModel)`** (new file): the exact validated
  shape from the plan. `inputs` and `output` are **required** (a blame tuple with neither is
  meaningless); `assumptions` defaults to `{}`; `produced_artifact_id` is optional so the write path
  (Phase 3) can build the tuple before the artifact is flushed, then stamp it. `model_config =
  ConfigDict(extra="forbid")` makes it the **strict-write** half — a mistyped or extraneous key
  (e.g. a stamped `grade`) is rejected rather than silently persisted.

### 3.2 Promoting `Checkpoint.tool_invocations` (no DB change)

The column already existed as free-form `JSON` (baseline 0.1.0 / `research-git.md`), so **the
promotion is entirely in the schema + service layer — the DB column is untouched**:

- **`app/services/checkpoints.py`** — `create_checkpoint(...)` gains a keyword-only
  `tool_invocations: list[ToolInvocation] | None = None`, modeled on the existing trusted `extra_refs`
  kwarg. Each entry is serialized with `model_dump(mode="json")` (UUID/enum → strings) onto the new
  `Checkpoint`. Absent for every non-tool flow, so validation/branch/plain checkpoints are unchanged.
  The three existing callers (`validations.py`, `branches.py`) pass nothing and are unaffected.
- **`app/schemas/checkpoint.py`** — `CheckpointRead` now surfaces
  `tool_invocations: list[dict[str, Any]]` as **raw JSON passthrough** (the **lenient-read** half).
  See §4.2 for why raw dicts rather than a typed lenient model.

This is the `AgentModels` lenient-read / strict-write split (0.8.10) applied to the blame tuple: a
project read can never 500 on a pre-shape or future-shape entry; only the write path rejects
malformed tuples.

### 3.3 The `Evidence → Artifact` link

- **`app/models/links.py` — `EvidenceArtifactLink`** (new): `evidence_id`, `artifact_id`, `role`
  (plain `String(20)`, validated in the service layer — allowed `derived_from` / `attachment`),
  `UniqueConstraint(evidence_id, artifact_id, role)`. A carbon copy of `ClaimEvidenceLink`'s idiom
  (typed join, CASCADE both FKs, indexed FKs). **Not** append-only-guarded — a link is created and
  cascades with its endpoints; it is not itself a ledger event.
- **Relationships:** `Evidence.artifact_links` and `Artifact.evidence_links`, both
  `cascade="all, delete-orphan"`, matching `Evidence.claim_links`.
- **`app/models/__init__.py`** — `EvidenceArtifactLink` exported (import + `__all__`). This is the
  load-bearing step for Alembic: `env.py` does `from app.models import *`, so a model missing from
  `__all__` is silently absent from migrations. Verified: `evidence_artifact_links` is present in
  `Base.metadata.tables`.

### 3.4 `assumptions` on `Evidence` and `Artifact`

- **`app/models/evidence.py` / `app/models/artifact.py`** — a dedicated
  `assumptions: Mapped[dict[str, Any]]` JSON column, **not** buried in `*_metadata`, so it is
  honestly surfaced (an unconditional claim recorded without its assumptions is a lie the append-only
  ledger can never edit out). Free-form object in v1 (SymPy-style keys: `positive`, `integer`,
  `nonzero`, or a flagship `angle=90`).
- **`app/schemas/evidence.py`** — `EvidenceRead.assumptions` added (defaults to `{}`), and
  **`app/services/evidence.py::_to_read`** now threads `evidence.assumptions` through (it builds the
  read via explicit kwargs, not `model_validate`, so the pass-through is required or the field would
  always read empty). The generic evidence-create path does **not** set assumptions — that is the
  tool-run write path's job in Phase 3.

### 3.5 Migration `0012_toolbench_provenance`

Additive, `down_revision = "0011_project_agent_models"`, single linear head confirmed. It:

- creates `evidence_artifact_links` (mirroring the baseline join-table idiom — local `_uuid()` /
  `_timestamps()` helpers, no server default on id/timestamps since the ORM supplies them);
- adds `evidence.assumptions` + `artifacts.assumptions` as `JSON NOT NULL DEFAULT '{}'`, so every
  existing row backfills to an empty assumption set **with no data pass** (the exact `0011`
  agent_models pattern);
- makes **no change to `checkpoints.tool_invocations`** (already present).

`downgrade()` drops both columns and the join table, in FK-safe order.

## 4. Judgment calls (where I interpreted the plan, and why)

These are the places I made a decision the plan left slightly open or under-specified — flagged here
so they can be revisited:

### 4.1 `assumptions` is `NOT NULL DEFAULT '{}'`, not `nullable`

The plan text says *"a dedicated **nullable** JSON column (default `{}`)"*, which is mildly
self-contradictory. I chose **`NOT NULL` with a `'{}'` server default** to match every other JSON map
in the codebase (`evidence_metadata`, `artifact_metadata`, `agent_models`), keep the model type
non-optional (`Mapped[dict[str, Any]]`, no `| None` handling downstream), and still ship additively
(existing rows backfill to `{}`). If a later phase needs to distinguish *"no assumptions"* (`{}`)
from *"assumptions unknown / not captured"* (`NULL`), this is the one spot to revisit — but for the
toolbench, a result computed under no recorded assumptions **is** `{}`, so the distinction isn't
load-bearing yet.

### 4.2 Lenient read = **raw `list[dict]`**, not a typed all-optional model

`AgentModels`' lenient read is a typed model with a fixed set of known keys. I deviated for
`tool_invocations` because the historical column holds a **different, evolving shape** (the old
free-form `research-git` `name`/`version`/`inputs`/`outputs` entries vs. the new
`instrument`/`engine`/…/`status` tuple). A typed lenient model would *mangle* an old entry (drop
unknown keys, show `instrument=null`); raw pass-through preserves the recorded bytes **verbatim** —
strictly more lenient, and more honest for a provenance record whose whole point is faithful
reconstruction. The *split* (lenient read / strict write) is preserved; only the read's
implementation differs, deliberately.

### 4.3 `EvidenceRead.assumptions` surfaced now

The plan's Phase 1 task list names the *column*, not the read schema. I surfaced `assumptions` on
`EvidenceRead` (read-only, defaults `{}`) because the phase deliverable is *"an Evidence … carries
assumptions,"* and the read schema is the only conduit that makes that observable via the API. It's
additive and safe (TS clients ignore unknown fields; the create path is untouched).

### 4.4 `tool_run` contribution action **not** added

Phase 3 adds `tool_run` to the allowed `contribution_action` vocabulary. I kept it out of Phase 1 so
the spine carries no Phase-3 semantics; the Phase 1 tests record checkpoints with the default
`create_checkpoint` action.

## 5. Verification

| Check | Result |
|---|---|
| `uv run ruff check .` | **clean** |
| `uv run pytest` (full suite) | **64 passed / 80 skipped** (+7 new DB-free provenance tests pass; +4 new DB-backed tests skip with no DB) |
| `uv run alembic heads` | single linear head — `0012_toolbench_provenance` |
| Metadata discovery | `evidence_artifact_links` + both `assumptions` columns present in `Base.metadata`; `EvidenceArtifactLink` importable from `app.models` |
| Migration offline render | `alembic upgrade 0011:0012 --sql` and `downgrade 0012:0011 --sql` both emit correct, reversible DDL (table + FKs + unique + indexes + `assumptions JSON DEFAULT '{}' NOT NULL`) |

**New tests** (`backend/tests/test_toolbench_provenance.py`):

- *DB-free (run in the default suite):* `ToolInvocation` parses a valid tuple and renders JSON;
  carries `assumptions` + `produced_artifact_id`; rejects empty/`None`/bad-enum fields; rejects a
  missing required field; **forbids an extra key** (the "no stamped grade" guarantee).
- *DB-backed (skip without `TEST_DATABASE_URL`):* a checkpoint carries a validated tuple that
  round-trips on read and from the ORM column; the tuple is **immutable** (mutating it →
  `AppendOnlyError`); an `Evidence` links to an `Artifact` with both directions resolving and both
  `assumptions` persisted; the link is **not** append-only (it can be deleted).

### Not run here (honest gaps)

Per the repo's no-local-DB / verify-against-live policy, and because applying `0012` to the live
database is a **deploy** action (needs authorization), the following are **pending**:

- the **4 DB-backed tests** above (need `TEST_DATABASE_URL` → a throwaway Postgres or CI);
- the live **`alembic upgrade head` → `downgrade` → `upgrade`** round-trip against real Postgres
  (offline `--sql` render is green, but that is not an execution).

## 6. What Phase 1 deliberately did **not** do (scope boundary)

No instruments, no `toolbench/adapter.py` or registry, no `services/tool_runs.py`, no
`GET /instruments` or `POST …/run`, no frontend. No Z3/Lean, no physics tools, no object-storage
artifact path, no stored grade/result-kind, no `tool_invocations`/`instruments`/`engines` tables.
Those are Phases 2–7.

## 7. Next step — Phase 2

The **adapter interface + code registry + conformance harness** (`toolbench/adapter.py`,
`toolbench/registry.py`, `tests/toolbench/test_conformance.py`) — the real reusable build object,
against which `calc.eval` / `expr.compare` / `geometry.coordinate_measure` / `oeis.search` become
conformance tests. Pure in-process, no DB. Then Phase 3 wires `services/tool_runs.py` to compose the
first real tool run through the chokepoint using the spine this phase just laid.

**Release/deploy follow-ups** (not done here): a `0.9.1` entry in `docs/changelog.md` and
`fly deploy` (`alembic upgrade head` applies `0012`) belong to the release step, once the DB-backed
verification is greenlit.
