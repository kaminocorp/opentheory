# Toolbench Phase 6 — Human-invokable API surface (completion notes)

> **Status:** implemented · **Release slice:** `0.9.2` (catalog + run for `calc.eval`) of
> `docs/executing/toolbench-provenance-and-first-instruments.md` · **Scope:** backend API layer — two
> endpoints + the request schema + the membership gate. **No frontend yet** (Phase 7). No migration.
>
> **What it delivers:** the toolbench becomes *usable from the product*. `GET /instruments` serves the
> public catalog; `POST /projects/{id}/instruments/{name}/run` runs an instrument as a signed-in
> project member and lands the result in the ledger — the same API an agent will later drive. `curl`
> the catalog, run `3²+4²==5²` over HTTP, and the checkpoint appears with its blame tuple.

---

## 1. What changed, where, and why

### 1.1 `GET /instruments` (`api/routes/instruments.py`, new) — the public catalog

A root-mounted, public, read-only endpoint returning `build_catalog()` (the Phase-2 serializer over
the *code* registry) as `list[InstrumentDescriptor]` — each instrument's name, namespace,
description, `input_schema`/`output_schema` (JSON Schema), and the three-outcome `result_contract`.
This is the `GET /agent-models/catalog` pattern exactly: static reference data, no auth, cacheable
indefinitely, and — because it reflects the code registry — it can never advertise an instrument the
runtime lacks.

### 1.2 `POST /projects/{id}/instruments/{name}/run` (same file) — the run endpoint

Declares the `ActingActor` dependency and, in order:

1. **authenticate** — `ActingActor` → `401` if unauthenticated (before the handler runs);
2. **resolve the instrument** — `registry.get(name)` → `404` on an unknown name. The route owns this
   (the Phase-3 service takes a *resolved* `Instrument`, staying registry-agnostic and stub-testable);
3. **authorize** — `ensure_is_member(db, project_id, actor)` → `404` missing project / `403` non-member;
4. **run** — hand off to `services/tool_runs.run_instrument(...)`, which composes the whole write
   through the checkpoint chokepoint in one transaction. A bad `inputs` payload (mismatching the
   instrument's `InputModel`) or a tool that fails to run surfaces as `422` and mints nothing.

Returns the Phase-3 `ToolRunResult` (`201 Created`): the `Checkpoint` with its **blame tuple**
(`tool_invocations`), the produced `artifact_id`, the optional `evidence_id`, plus `status` and
`content_hash`.

### 1.3 `ToolRunRequest` (`schemas/tool_run.py`, new) — the request body

`inputs` (raw, validated against the instrument's `InputModel` *in the service* so the envelope stays
generic across every instrument), `assumptions`, and optional `thread_id` / `claim_id` /
`relation_kind`. The response reuses the existing `ToolRunResult` (§3.1).

### 1.4 `ensure_is_member` (`services/project_members.py`, new) — the research-write gate

A membership gate that is the companion to `ensure_can_manage`, **without** the `FOR UPDATE` project
lock (§3.2). `404` missing project, `403` non-member or account-less actor; it does not distinguish
owner/admin.

### 1.5 Router wiring (`api/router.py`)

`instruments.router` mounts at the root (it declares full paths, like `threads`/`invitations`), so
`GET /instruments` and `POST /projects/{id}/instruments/{name}/run` sit under the `/api/v1` prefix.

## 2. The design decision that mattered: which gate

The plan says "gated to project membership (reuse `ensure_can_manage`/member check)". Two honest
questions fell out.

**Owner/admin, or any member?** Running an instrument is *research*, not *governance* — it mints a
`Contribution` (producing a result), which the domain model deliberately separates from management.
So the gate is **membership**, not owner/admin. Today `ProjectRole` is only `OWNER`/`ADMIN`, so the
two coincide in *who* passes; but `ensure_is_member` stays correct if a lower-privilege contributor
role is ever added (a contributor should be able to run instruments), whereas `ensure_can_manage`
would wrongly exclude them.

**Take the lock, or not?** `ensure_can_manage` holds a `FOR UPDATE` lock on the project row — it
exists to serialize *owner-mutating* writes (the owner-floor race). A tool run does **not** mutate the
project row, so borrowing that lock would needlessly serialize concurrent runs on the same project
(exactly the parallelism a research platform wants). `ensure_is_member` does the same authorization
without the lock. Hence a new gate rather than reusing `ensure_can_manage`.

## 3. Judgment calls

### 3.1 The response reuses `ToolRunResult` rather than adding rich Artifact/Evidence read models

The plan mentions returning "the produced Artifact (+ Evidence + Checkpoint summary)". The **blame
tuple already rides on `CheckpointRead.tool_invocations`** — it carries the instrument, version,
engine, inputs, output, assumptions, status, and `produced_artifact_id`. So `ToolRunResult`
(checkpoint + `artifact_id` + `evidence_id` + `status` + `content_hash`) is already a complete,
provenance-bearing response: the frontend renders provenance from the blame tuple and links the
artifact/evidence by id. There is no `ArtifactRead` schema today and `EvidenceRead` needs link
context; minting both here would be scope the blame tuple makes unnecessary. Deferred until a
consumer needs the full rows inline.

### 3.2 Membership is stricter than sibling research writes — deliberately, per the plan

Creating a thread/claim/evidence currently requires only `ActingActor` (any authenticated actor),
not membership. The run endpoint is stricter (membership) because the plan asks for it and because a
run is the heavier, compute-consuming write (and will consume budget in the funding model). Tightening
the lighter metadata writes to membership is a separate, orthogonal decision — not made here.

### 3.3 Order of checks: instrument (`404`) before membership (`403`)

The instrument catalog is public, so an unknown-instrument `404` leaks nothing, and resolving it
first (a DB-free registry lookup) keeps the service registry-agnostic. Auth (`401`) still precedes
both — it is the `ActingActor` dependency, which runs before the handler.

### 3.4 `201 Created`

A run creates ledger records (an artifact + a checkpoint, atomically), so `201` matches the other
create endpoints (`POST /projects`, `POST .../threads`).

## 4. Verification

| Check | Result |
|---|---|
| `uv run ruff check .` | **clean** |
| `uv run pytest tests/toolbench/test_instruments_api.py` | **2 passed / 4 skipped** |
| `uv run pytest` (full suite) | **115 passed / 93 skipped** (+2 passed, +4 skipped over Phase 5) |
| route registration | `/api/v1/instruments` + `/api/v1/projects/{project_id}/instruments/{name}/run` both mounted; catalog returns all four instruments |

**DB-free tests (run in the default suite — the auth-gate regression):**

- **catalog is public** — `GET /api/v1/instruments` → `200` with all four instruments and the
  three-outcome contract, with the DB dependency *unusable* (no DB access).
- **unauthenticated run → `401`** — with the dev-header path off, a run against a bogus project id
  and a *valid* body is rejected by the `ActingActor` gate before any DB access (proves the `401` is
  auth, not body-validation or a `404`) — the 0.6.5 pattern.

### Not run here (honest gap)

Per the no-local-DB / verify-against-live policy, the **4 DB-backed tests** skip without
`TEST_DATABASE_URL`:

- the **signed-in-member round-trip** — an account-backed owner runs `calc.eval` over the API → `201`,
  the response's blame tuple names `calc.eval` with `holds=true`, and exactly one `Checkpoint` lands
  in the project's ledger;
- **unknown instrument → `404`**, **non-member → `403`**, **bad inputs → `422`**.

They use the established `internal_funder` + `X-Dev-Actor-Id` setup (same as the project-stewardship
suite), so they are structurally sound; the true end-to-end HTTP round-trip is pending a throwaway
Postgres, CI, or the live deploy. This brings the toolbench's pending DB-backed set to **13** across
Phases 3–6.

## 5. Scope boundary

No frontend (Phase 7). No rich Artifact/Evidence read models in the response (§3.1). No rate limiting
/ budget accounting on runs (the funding model is a separate concern). No standalone `source.pin`
instrument. No Z3/Lean, no object-storage artifact path.

## 6. Next step — Phase 7

The frontend workspace surfaces: per instrument a **drive** column (a formula field, a point editor, a
terms box, and a visible **assumptions** input) and a **show** column (formula card via KaTeX,
counterexample card, citation card for the pin), wired through the typed `lib/api.ts` client
(`getInstrumentCatalog` / `runInstrument`) in the Kamino Console language — with the honesty rules in
the UI (`undecided` renders as "escalate", never a pass; "no counterexample found" is weak support,
never "proven"). It may spin into its own frontend plan.

**Release/deploy follow-ups** (not done here, matching Phases 1–5): the `0.9.2` entry in
`docs/changelog.md` and `fly deploy` belong to the release step, once the DB-backed round-trips are
greenlit.
