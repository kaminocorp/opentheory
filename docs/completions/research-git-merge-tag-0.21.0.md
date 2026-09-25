# 0.21.0 — Research-git merge + tag

**Goal.** Ship the two missing research-git primitives from
`docs/vision/research-git.md`: **merge** (combine parallel exploration lines)
and **tag** (pin a named milestone / validated result / retraction) so
multi-hypothesis work can converge without deleting history.

**Shape.** Thin routes → services → models. Merge composes through
`create_checkpoint` with multiple parents. Tag is an append-only annotation
table, also recorded through the chokepoint. **Migration
`0016_research_git_merge_tag` (additive).**

## Why

The ledger already had Checkpoint (commit) + Branch + close-branch. Agents and
humans could fork and abandon, but they could not *synthesize* or *name* a
result. Merge and tag are the operations that make parallel exploration
convergent rather than permanently forked.

## What landed

- **Merge.** `POST /projects/{id}/merges` creates a checkpoint whose parents are
  the head of each open source branch plus the head of the target line (main
  line when `target_branch_id` is omitted). Source branches flip to `merged` in
  the same transaction. Claim rows may be referenced (`role=merged`); they are
  never rewritten. `resolution=resolved` requires a rationale. Coexist is not
  an API outcome — it is the decision *not* to merge. `close_branch` still
  rejects `merged` (a close cannot claim a merge that did not happen).
- **Tag.** `tags` table: `name` (unique per project), `kind`
  (`milestone` / `validated` / `retraction`), pointer at a checkpoint.
  Append-only ORM guard. A colliding name is `409`. Tagging a sealed/merged
  line still records, on the main line.
- **Frontend.** Merge affordance on the Research line bar; Tags bay on
  Research; checkpoint cards show tags that point at them.
- **Docs.** Vision operations annotated *(built)*; blueprints, TLDR, README,
  changelog, roadmap.

## Tests

- DB-free: OpenAPI paths; tags expose no PUT/PATCH/DELETE; write endpoints
  declare the acting-actor header; resolved merge without rationale is a
  schema error; blank tag name rejected; migration `0016` linkage / single-head
  / model-column agreement.
- DB-gated (skip without `TEST_DATABASE_URL`): multi-parent merge of two
  branches; one branch into main; claim refs without rewrite; closed and
  already-merged sources rejected; merged line sealed against new checkpoints;
  tag create/list; duplicate name is `409` not an overwrite; tag append-only
  guard; tag on a merged line records on main.

## What did not change

- Ledger writes still go only through `create_checkpoint`.
- Funder / contributor / validator stay separate tables.
- `close_branch` outcomes remain `dead_end` / `closed`.
- Semantic diff, blame-as-an-op, multi-thread orchestrator, Lean / Mathlib
  are out of scope.

## Verification

Filled after the check run in this PR.

## Unverified

- No pixel-level browser walk of the Merge form or Tags bay (same owed
  eyeball pass as `0.14.0`–`0.16.0`).
- Migration `0016` is not applied to the live database by this PR.
