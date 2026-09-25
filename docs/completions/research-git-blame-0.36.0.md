# 0.36.0 — Research-git blame

**Goal.** Ship the remaining research-git *read* from
`docs/vision/research-git.md`: for any claim in a project, return the
chain of checkpoints, actors, and tool invocations that produced or
evidence-grounded it. Substrate for attribution and for debugging a
bad result.

**Shape.** A thin public GET over a dedicated service. Not an
instrument: instruments mint a checkpoint on `result`, and a blame
must mint nothing. **No schema, no migration.** Reuses shipped
`0.21.0` parents / refs, `0.16.x` grounding, `0.29.0` ancestor-walk
helpers, and `AgentRun.steps[].checkpoint_id` for optional pass
linkage.

Sits on unmerged `0.35.0` (itself stacked on `0.34.0` / shipped `0.33.0`).
**Does not claim 0.34–0.36 as on `main`.** `main` is shipped `0.33.0`
(squash `e3a07ea`).

## Why a read

`git blame` does not create a commit. Semantic blame is the same kind
of operation as `log` / `show` / `diff`. Putting it on the toolbench
would force a ledger write on every lookup, or a special-case
"instrument that never mints" that breaks the
`result | refuted | undecided` contract.

## What landed

- **`GET /projects/{id}/claims/{claim_id}/blame`.** Always-on, public.
  Unknown project → `404`. Unknown claim, or a claim that is not in
  this project → `404` `"Claim … not found"`. No acting-actor header.
- **Touch set.** A checkpoint is on the chain when a `checkpoint_refs`
  row targets the claim, targets evidence linked to the claim, or
  records a validation of the claim. Tool invocations ride on those
  checkpoints; a well-formed tuple adds the `instrument` role.
  Unrelated commits — including idle ancestors — stay off the chain.
- **State at a step** is the ancestor closure of that checkpoint
  (self + parents, merge nodes union every parent), same math as
  semantic diff:
  - *Signal* via `compute_signal` over validations whose recording
    checkpoint is in the ancestor set.
  - *Grounding* via evidence recorded on an ancestor, plus
    hand-attached evidence with `created_at <= tip`.
  - Movement compares that snapshot to ancestors-minus-self.
- **Each step** carries the author Actor (type `human` / `agent` /
  `system` — never an Account), contribution kind, roles, instruments,
  optional agent-run (`id`, role, model, status) when a pass step
  names the checkpoint, and the after / from signal and grounding
  headlines when they moved.
- **Frontend.** Blame bay under Compare on Research. Claim picker
  from the selected thread, or a quiet *Blame* on the claim row that
  scrolls to the bay. Sentence case. Public. No write.
- **Docs.** Vision `blame` marked *(built)*; changelog / completions /
  roadmap / TLDR / README / contribution guidelines where they still
  said blame was planned.

## Tests

- DB-free: OpenAPI path is GET-only and does not require
  `X-Dev-Actor-Id`; touch classification (unrelated / claim+instrument
  / evidence+validation); instrument collector skips malformed tuples
  and sorts stably; agent-run linker picks the newest matching pass.
- DB-gated (skip without `TEST_DATABASE_URL`): empty chain when a
  claim was never referenced; asserted checkpoint carries the author
  Actor; validation records a `validate` step and `none → validated`;
  `calc.eval` on a targeted claim is `evidenced` + `instrument` and
  moves grounding `ungrounded → B`; unknown claim / foreign-project
  claim / unknown project are `404` and the checkpoint count does not
  rise; two identical GETs match; an unrelated checkpoint stays off
  the chain.

## What did not change

- Ledger writes still go only through `create_checkpoint`.
- Append-only guards are untouched.
- Funder / contributor / validator stay separate tables.
- Account ≠ Actor.
- Instruments stay `result | refuted | undecided`. Blame is not one
  of them.
- No Alembic revision — `0021_concurrent_campaign_cycles` stays the
  head on `main` (`0.33.0` added none). Stacked PRs #19–#20 also claimed no new
  migrations. This release does not add one.

## Caveats (honest)

- Claim *fields* (`statement`, stored `status`, `confidence`) have no
  history table. Presence on the ledger, the derived signal, and the
  derived grounding are what this blame can honestly report.
- Opening a claim records a `create_claim` contribution **without** a
  checkpoint. Until something refs the claim on the ledger, the chain
  is empty — that is the truth, not a missing row.
- Hand-attached evidence is timestamp-aligned, not line-aligned (it
  never recorded a checkpoint). Tool-run evidence is line-aligned via
  `checkpoint_refs`.
- Agent-run linkage is derived from mutable `AgentRun.steps` JSON, not
  an FK. A pass that failed before landing, or a step that omitted
  `checkpoint_id`, will not appear.
- No pixel-level browser walk of the Blame bay (same owed eyeball
  pass as `0.14.0`–`0.16.0` / `0.29.0`).

## Verification

- `ruff check .` clean.
- Default pytest (no `TEST_DATABASE_URL`): **634 passed, 220 skipped**
  (8 new DB-free blame gates; 9 new DB-gated HTTP round-trips skipped).
- Frontend `typecheck` / `lint` / `build` clean; `npm test` **35 passed**
  (6 new blame caption tests).
- With `TEST_DATABASE_URL` the blame suite is written to skip cleanly
  when Postgres is absent.

## Unverified

- No pixel-level browser walk of the Blame bay. The app was not
  signed in against a live backend in this environment.
- DB-gated blame round-trips skip without `TEST_DATABASE_URL`.
