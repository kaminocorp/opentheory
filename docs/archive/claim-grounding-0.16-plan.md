# Claim grounding — the evidence grade ladder (implementation)

> **Status — executing (2026-07-31).** Backend read-model + frontend surface. **No migration,
> no new table, no new column.** Implements `docs/plans/agent-research-tools.md` §2.1 + §7.2 —
> the one §7 data-model ask that never shipped. Read that doc first for the *why*; this doc is
> the *how*: decisions locked, the grading matrix, phases, file map.
>
> **Target release line:** `0.16.x`. `0.15.0` is landed (`edfbe18`) and `0.14.1`–`0.14.2`
> (CommandRail sync, tab badges) are still open on the `0.14.x` line — they don't collide with
> this (frontend chrome vs. claim read model), but **confirm the number** before the first commit
> if either lands first.

---

## 0. One-line goal

Make a claim's **grounding** — how strongly it is backed by what actually ran — a derived,
first-class part of the claim read model, so that `primitives.md`'s promise (*"confidence
explainable through evidence and validation history, not a naked score"*) is true of the
**evidence** half, not just the validation half.

---

## 1. Why this, why now (the short version)

`services/claims.py::compute_signal` derives a claim's display signal from
`list[ValidationRead]` — **validations only**. Consequence, today, in production:

> A claim carrying a `z3.prove` machine-checked proof and a claim carrying nothing but an
> LLM's opinion both read `signal: "none"` until a human clicks *validate*.

The platform's flagship capability — machine-checked truth — is invisible to the surface that
exists to express confidence. Six instruments manufacture graded results; nothing consumes the
grade.

This also **gates the autonomy spine**. An agent loop needs three things that are all the same
missing object: a *state* to plan against (the `0.12.1` planner receives *thread + open claims +
catalog* — it sees *that* a claim is open, never *how well grounded*), a *progress measure* (did
the pass improve anything, or just mint checkpoints?), and a *stopping criterion*. Build
continuous autonomy before this and you get an expensive random walk; ship `0.12.5` budget
metering before this and you meter spend with no notion of yield.

Per the project's standing rule (*anything an agent will do, a human should be able to do
first*), this pays off **without** agents: a human working the flagship *measuring across a
corner* thread sees claims 1–4 climb D → C → B, with claim 5 visibly the only rung left.

---

## 2. Decisions locked

| # | Decision | Choice | Rationale |
|---|---|---|---|
| D1 | Stamped or derived? | **Derived, never stamped.** No caller may set a grade. | `schemas/tool_invocation.py:17` already fixed this: grade is *"derivable from the recorded instrument, never stamped"*. A stamped grade is an unverifiable assertion about rigor; a derived one is a consequence of what ran — same philosophy as the append-only guard. |
| D2 | New column / table? | **No.** Pure read-model derivation over existing rows. | The whole chain already exists (§4.1). Zero migration is what makes this a small line. Revisit only if cross-project audit queries ("every Grade-A claim") demand an index. |
| D3 | Grade source of truth on the read path | **`Evidence.evidence_metadata["instrument"]` + `["status"]`**, written by `tool_runs.py:256-260` in the same transaction as the blame tuple. | The authoritative record stays the `ToolInvocation` on the append-only `Checkpoint`; but it rides as JSON inside a blob, and traversing it per claim is an expensive, awkward query. The evidence metadata is a same-transaction denormalized copy — correct by construction, cheap to read. Recorded as an accepted denormalization (§10 R2). |
| D4 | Where does the matrix live? | `app/toolbench/grading.py`, **co-located with the registry**, asserted by the conformance harness. | Adding an instrument must *force* a grading decision. A missing entry should fail the harness, not silently read Grade D. |
| D5 | Enum home | `EvidenceGrade(StrEnum)` in `models/enums.py`, **not** a named Postgres type. | Exact `ResultStatus` precedent (`enums.py:137`): *"promotion to a named Postgres enum is deferred until (and only if) it ever becomes a column."* It never becomes a column here (D2). |
| D6 | Does grounding mutate `Claim.status` / `Claim.confidence`? | **No.** Display-derived only, exactly like `signal`. | `schemas/claim.py:10-11`: the signal *"does NOT mutate the stored `Claim.status` — confidence stays explainable."* `Claim.confidence` stays a human-set field. |
| D7 | Retrieved evidence | **Off-ladder** — `cited`, not a letter grade. | §III of the source doc: retrieval is graded by source authority + pin quality, not by computation. Discriminated by the existing `Evidence.source_type` (`"oeis"` vs `"tool"`, `tool_runs.py:253`). |
| D8 | Refutation vs support | Grounding carries **two sides**: strongest supporting grade *and* strongest countering grade. A counter at A/B **dominates**. | A claim with an exact counterexample is refuted regardless of how many supporting examples exist. Mirrors the existing `contested` precedence in `compute_signal`. |

---

## 3. The grading matrix (the actual domain decision)

Grade is a function of **`(instrument, status)`** — *not* instrument alone. This is the
subtlety that makes the whole thing honest: `counterexample.search` returning `refuted` with an
exact integer witness **settles** a universal negatively (Grade B for the negation), while the
same instrument returning `result` is finite sampling (Grade C). The `0.9.6` / `0.9.9` honesty
work already made these status distinctions rigorous — this table must respect them, not
flatten them.

| Instrument | `result` | `refuted` | `undecided` |
|---|---|---|---|
| `z3.prove` | **A** — machine-checked proof (`artifact_kind="proof"`) | **A** — machine-checked counter-model, a disproof | **none** |
| `expr.compare` | **B** — exact symbolic equivalence | **B** — provably non-zero difference | **none** |
| `calc.eval` | **B** — exact evaluation / relation holds | **B** — exact false relation (`artifact_kind="counterexample"`) | **none** |
| `geometry.coordinate_measure` | **B** — exact coordinate measurement | *(n/a — never refutes)* | **none** |
| `counterexample.search` | **C** — finite grid, weak support | **B** — a definitive exact witness | **none** |
| `oeis.search` | **cited** (off-ladder, D7) | *(n/a)* | **none** |
| *no instrument in the chain* | **D** — human-asserted or LLM-only | — | — |

**Three rules that follow, and must be tested as such:**

1. **`undecided` never contributes a grade.** It is not a weak pass; it is the escalation seam.
   Carrying it as "some grade" would be exactly the dishonesty the toolbench contract forbids.
2. **Grade D is the absence of a tool, not a failure.** A human-created `Evidence` row (no
   `instrument` key in its metadata) is legitimately D — the baseline the bench exists to climb
   out of. It must never render as an error.
3. **A tolerance-only result may never be reported as exact.** No current instrument produces
   one (all six are exact or retrieval), but the ladder must not acquire a "float → B" rule when
   SciPy (`I.2`) lands. Left as a comment on the matrix so the next author is warned.

### 3.1 Aggregation to a claim

```
grounding(claim) = {
  support:  strongest grade over links where relation_kind == "support",
  counter:  strongest grade over links where relation_kind == "weaken",
  cited:    any link whose evidence.source_type is external (e.g. "oeis"),
}
```

`relation_kind == "context"` (the `undecided` default, `tool_runs.py:61`) contributes to
neither side — consistent with rule 1. Grade ordering for "strongest": `A > B > C > D`.

**Display precedence** (what the claim shows as its headline rung):

| Condition | Reads as |
|---|---|
| `counter` is A or B | **refuted** — dominates any support (D8) |
| `support` is A | **proven** |
| `support` is B/C/D | that letter |
| neither, `cited` only | **cited** |
| nothing | **ungrounded** |

---

## 4. Target architecture

### 4.1 The chain that already exists (verified, no schema work)

```
Claim
  └─ ClaimEvidenceLink.relation_kind ∈ {support, weaken, context}     models/links.py:10
       └─ Evidence
            ├─ .source_type          "tool" | "oeis"                   tool_runs.py:253
            ├─ .evidence_metadata    {output, status, instrument}      tool_runs.py:256-260   ← D3 reads this
            └─ EvidenceArtifactLink.role = "derived_from"              models/links.py:48
                 └─ Artifact.kind ∈ {derivation, counterexample, measurement, proof, pinned_source}
                      ▲
                      └── ToolInvocation.produced_artifact_id          schemas/tool_invocation.py:44
                          {instrument, instrument_version, engine, engine_version, status, …}
                          — rides as validated JSON on the append-only Checkpoint (authoritative record)
```

Every join table and every field is in place. This line adds **consumers**, not structure.

### 4.2 New / touched files

| File | Change | Phase |
|---|---|---|
| `backend/app/models/enums.py` | `+ class EvidenceGrade(StrEnum)` (`A`/`B`/`C`/`D`) — plain StrEnum, D5 | 1 |
| `backend/app/toolbench/grading.py` | **NEW** — the §3 matrix + `grade_for(instrument, status)`; pure, no DB, no imports from `services/` | 1 |
| `backend/tests/test_grading.py` | **NEW** — matrix unit tests + the three honesty rules | 1 |
| `backend/app/toolbench/` conformance harness | `+` assert every registered instrument has a matrix entry (D4) | 1 |
| `backend/app/schemas/claim.py` | `+ class ClaimGrounding(BaseModel)`; `+ grounding: ClaimGrounding` on `ClaimRead` | 2 |
| `backend/app/services/grounding.py` | **NEW** — `grounding_by_claim(db, claim_ids)` batch loader, mirroring `validations.validations_by_claim` | 2 |
| `backend/app/services/claims.py` | `_to_read` takes grounding; the three call sites (`create_claim`, `list_claims`, `get_claim`) pass it | 2 |
| `backend/app/services/projects.py` | contested read model (`:124`) unchanged in behaviour; verify no N+1 regression | 2 |
| `backend/tests/test_read_models.py` | `+` DB-gated: grounding through the chokepoint per instrument | 2 |
| `frontend/src/types/` | `+ ClaimGrounding` mirroring the read schema | 3 |
| `frontend/src/components/projects/claim-list-panel.tsx` | `+` grade chip + "what would raise this" line | 3 |
| `frontend/src/app/styleguide/` | `+` the grade chip in all five states | 3 |

---

## 5. Phases

### Phase 1 — the derivation (pure, no DB, no API)

Ships nothing user-visible; everything downstream depends on it.

1. `EvidenceGrade` StrEnum in `models/enums.py`, docstring explaining the D5 precedent.
2. `app/toolbench/grading.py`:
   - the §3 matrix keyed `(instrument_name, ResultStatus)`,
   - `grade_for(instrument: str, status: ResultStatus) -> EvidenceGrade | None` — `None` for
     `undecided` and for retrieval instruments (the caller maps retrieval to `cited` via
     `source_type`, keeping the off-ladder rule in one place),
   - a module docstring carrying honesty rules 1–3 verbatim.
3. Wire D4 into the conformance harness: a registered instrument with no matrix entry **fails**.
4. `tests/test_grading.py` — every cell of §3; explicit tests that `undecided → None` for all
   six instruments and that `counterexample.search` grades `refuted` **B** but `result` **C**.

**Exit:** `uv run pytest tests/test_grading.py` green; harness fails if you comment out a row.

### Phase 2 — traversal + read model (backend, DB)

1. `ClaimGrounding` schema: `support: EvidenceGrade | None`, `counter: EvidenceGrade | None`,
   `cited: bool`, `headline: Literal["proven","refuted","B","C","D","cited","ungrounded"]`.
   Computed in the service, never `from_attributes` (same note as `signal`,
   `schemas/claim.py:40-41`).
2. `services/grounding.py::grounding_by_claim(db, claim_ids) -> dict[UUID, ClaimGrounding]` —
   **one** query joining `ClaimEvidenceLink → Evidence`, reading `evidence_metadata` +
   `source_type`, then aggregating in Python per §3.1. Batch-loaded exactly like
   `validations_by_claim` — **no N+1** (the `0.4.4` constraint that `projects.py:127` calls out).
3. `claims.py`: `_to_read(claim, validations, grounding)`; update `create_claim` (fresh claim →
   empty grounding, mirroring the `[]` validations), `list_claims`, `get_claim`.
4. Tests (DB-gated): run each instrument through `run_instrument` against a claim, assert the
   grounding that comes back. Include a human-created evidence row → **D**, and an `undecided`
   run → `context` link, grounding unchanged.

**Exit:** `TEST_DATABASE_URL=… uv run pytest tests/test_read_models.py` green; a claim with a
`z3.prove` proof reads `headline: "proven"` with **no** validation recorded.

### Phase 3 — the surface (frontend)

1. Mirror `ClaimGrounding` in `frontend/src/types/`.
2. Grade chip in `ClaimListPanel`, in the `0.15.0` register: sans label, mono letter, one of the
   existing state tones — **crimson `--signal` reserved for `refuted`**, `proven` gets the pass
   tone, `ungrounded`/`D` stay muted (never alarming — rule 2).
3. The *"what would raise this"* line — a single sentence derived from the headline
   (`B → "an exact result; a proof would settle it"`). This is the affordance that makes the
   ladder actionable rather than decorative.
4. Styleguide entry, all five states, **checked under grayscale emulation** (design-system §0:
   grayscale survival).

**Exit:** `npm run typecheck && npm run lint && npm run build` clean; the flagship thread's
claims 1–4 show B/B/B/B with claim 5 `ungrounded`.

### Phase 4 (separate release — **not** this line) — the payoff

`0.16.3`+ or `0.17.x`: feed grounding into the `0.12.1` planner context so an agent plans to
*raise* a claim's rung, and give `0.12.5` budget metering a yield measure. Explicitly out of
scope here — Phases 1–3 must stand alone and be useful to a human first.

---

## 6. Acceptance

1. A claim with a `z3.prove` proof and **zero** validations reads `proven` (today: `none`).
2. A claim with an exact `counterexample.search` witness reads `refuted` even if three
   supporting `result` runs are also linked (D8).
3. An `undecided` run changes nothing about grounding (honesty rule 1).
4. A hand-created evidence row grades **D** and renders calmly, not as an error (rule 2).
5. An `oeis.search` pin reads `cited`, never a letter (D7).
6. No `Claim.status` or `Claim.confidence` value changes anywhere (D6) — assert in a test.
7. Listing 20 claims issues no additional query per claim (no N+1).
8. Adding a seventh instrument without a matrix row fails the conformance harness (D4).

---

## 7. Explicitly out of scope

- Any migration, column, or table (D2).
- Touching `compute_signal` semantics — validation-derived signal and evidence-derived grounding
  are **two separate axes** shown side by side. Merging them into a single score would recreate
  exactly the "naked score" `primitives.md` forbids.
- Merge / semantic diff / tag (the rest of check-in gap #2) — grounding is the prerequisite, not
  the whole of belief integration.
- Planner and budget consumption (Phase 4).
- The mechanical reproducibility axis (`bit-verifiable` / `env-pinned` / `tolerance-only`,
  source doc §2.1). No current instrument needs it; it becomes real with SciPy (`I.2`).

---

## 8. Open questions

1. **Chip placement** — inline on the claim row, or in the claim detail only? Recommendation:
   inline, since scanning the ladder across a thread is the point.
2. **Does `headline` belong on the server?** Computing it server-side keeps the precedence rules
   in one place and testable; it does mean a presentation string in a read schema. Recommendation:
   server-side as a **discriminant**, with all copy on the client.
3. **Thread-level rollup** (`"3 claims at B, 1 ungrounded"`) — cheap once §3.1 exists, but it
   touches the project overview read model. Recommendation: defer to `0.16.2`, keep this line to
   the claim.

---

## 9. Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | The matrix encodes a *wrong* epistemic call (e.g. grading a definitive refutation C) and the ledger overstates or understates rigor. | §3 is reviewed as a domain decision, not a coding detail. Every cell is a named test. When in doubt, grade **lower** — understating rigor is recoverable, overstating is the failure mode a provenance ledger exists to prevent. |
| R2 | `evidence_metadata` (D3) drifts from the authoritative blame tuple. | Both are written in the same transaction by `tool_runs.py`; nothing else writes either. Recorded as an accepted denormalization. If a divergence is ever observed, the fix is to read the blame tuple, not to stamp a grade. |
| R3 | Grounding gets read as a confidence *score* and the two-axis design collapses. | UI shows grade and validation signal as distinct, adjacent, differently-shaped elements; no arithmetic combining them anywhere (§7). |
| R4 | N+1 on claim lists. | Batch loader mirrored on `validations_by_claim`; acceptance criterion 7 asserts it. |

---

## 10. Pointers

| Doc | Role |
|---|---|
| `docs/plans/agent-research-tools.md` §2.1, §7.2 | The grade ladder's origin and rationale |
| `docs/plans/checkin-state-2026-07-22.md` §"Main gaps" | Gap #2 (belief integration) — this is its first slice |
| `docs/blueprints/primitives.md` | The "explainable, not a naked score" invariant |
| `backend/app/schemas/tool_invocation.py` | The blame tuple + the "derivable, never stamped" decision |
| `backend/app/services/claims.py` | `compute_signal` — the validation axis this sits beside |
