# Falsify & Render Phase 3 — Frontend drive + show (completion notes)

> **Status:** implemented · **Release slice:** `0.10.3` of
> `docs/executing/falsify-and-render-0.10.md` · **Scope:** frontend only — no backend, schema,
> or migration. Wires `counterexample.search` into the Phase 7 toolbench panel (drive + show).
>
> **What it delivers:** a signed-in member can falsify `d == a + b` from the workspace, see a
> definitive counterexample card or an honest weak-support card, and land a checkpoint on the
> selected branch/main line (existing `0.9.8` scoping unchanged).

---

## 1. What this phase is (and is deliberately not)

Phases 1–2 shipped and ledger-tested the instrument. Phase 3 is the **human-invokable surface**:
bespoke drive form, bespoke result card, and honesty rules so weak support never reads as proof.

Not in this phase: KaTeX / `*_latex` (Phases 4–5), changelog batch (Phase 6).

## 2. What changed, where, and why

### 2.1 `drive-forms.tsx` — `CounterexampleSearchForm`

| Field | Default | Notes |
|---|---|---|
| Relation | `d == a + b` | Flagship sum-of-legs falsification story. |
| Variables | `a:1–10`, `b:1–10`, `d:1–15` | Name + min + max rows with stable `ce-*` ids (geometry pattern). |
| Max samples | `500` | Client validates integers; Run disabled until complete. |

Wired in `DriveForm` switch case. Emits `{ relation, variables, max_samples }` matching the backend
`InputModel`.

### 2.2 `result-view.tsx` — `CounterexampleSearchBody` + `WeakSupportCard`

| Outcome | UI |
|---|---|
| `refuted` + `found=true` | Reuses `CounterexampleCard` (fail edge): relation, `witness_relation`, assignment chips (`a=3`, …). Caption: definitive falsification in this search space. |
| `result` + `found=false` | New **`WeakSupportCard`**: hatched fill (`.hatch`), neutral left edge, headline “No counterexample found”. Shows `samples_tried`, `search_space` chips; if `truncated`, explicit capped-search caveat. **Never** “proven” / “validated”. |

`resolveOutcomeMeta()` overrides the header pill for weak-support runs: **warn** tone, label “No
witness”, gloss “Weak support only — absence in this search space is not proof.” — so the ok-green
`RESULT` pill does not mislead.

### 2.3 `assumptions-editor.tsx` + `toolbench-panel.tsx`

- `instrumentAcceptsAssumptions()` — returns `false` for `counterexample.search` (backend rejects
  non-empty assumptions in v1).
- `AssumptionsEditor` hidden for that instrument so users cannot attach rows that would 422.

`demoAssumptionRows` already returned `[]` for non-geometry instruments; no change needed there.

### 2.4 `types/toolbench.ts`

Unchanged — outputs remain `Record<string, unknown>` on the blame tuple; no new shared types
required.

## 3. Judgment calls

### 3.1 Hide assumptions editor, don't merely empty it

An empty editor still lets users add rows. Hiding the block matches the backend contract and avoids
a confusing 422 on an otherwise valid grid.

### 3.2 Weak-support uses warn tone, not ok

`result` is technically the honest backend status for “search completed, no witness,” but the
default `RESULT` / ok chrome would overstate certainty. `resolveOutcomeMeta` special-cases
`counterexample.search` + `found=false` only — other instruments unchanged.

### 3.3 Demo defaults find `(1,1,1)` first, not `(3,4,5)`

Wide ranges match Phase 1 behaviour; the narrative triple is one pin-away in the form (set
`a,b,d` min=max to 3,4,5). The UI does not hard-code the story triple in defaults so the drive
form teaches the general falsifier.

## 4. Verification

```bash
cd frontend && npm run typecheck && npm run lint && npm run build
# all green — /projects/[projectId] 63.1 kB, no new deps
```

**Manual post-deploy** (not run here): signed-in member selects `counterexample.search`, runs with
defaults or pinned triple, confirms counterexample card + checkpoint on branch/main; run
`a + b == b + a` on `1..3` for weak-support card; sealed branch still disables Run (`0.9.8`).

## 5. Scope boundary

- No backend / API / schema changes.
- No KaTeX (SymPy strings still render via monospace `Formula`).
- No changelog entry yet — batch at `0.10.3` merge.

## 6. Next step

**Phase 4 (`0.10.4`)** — backend `to_latex` + additive `*_latex` fields; hash excludes `_latex`
keys. **Phase 5** — KaTeX in `formula.tsx`.