# 0.29.0 — Semantic git diff

**Goal.** Ship the remaining research-git *read* from
`docs/vision/research-git.md`: a deterministic instrument-or-read that
explains what changed between two checkpoints / branch tips in *research
space* — claims, grounding, instrument results — not a raw dump of blob
bytes.

**Shape.** A thin public GET over a dedicated service. Not an instrument:
instruments mint a checkpoint on `result`, and a compare must mint
nothing. **No schema, no migration.** Reuses shipped `0.21.0` parents /
branch tips / tags and the `0.16.x` grounding yield functions.

## Why a read

`git diff` does not create a commit. Semantic diff is the same kind of
operation as `log` / `show` (already the checkpoint list / get). Putting
it on the toolbench would force a ledger write on every compare, or a
special-case "instrument that never mints" that breaks the
`result | refuted | undecided` contract.

## What landed

- **`GET /projects/{id}/diff?from=&to=`.** Resolves each token, in order:
  checkpoint UUID, tag UUID, branch UUID; then `main` / `mainline` /
  `@main` / `HEAD`; then exact tag name; then exact branch name. Unknown
  → `404` `"unknown ref: …"`. Empty token → `400`.
- **State at a tip** is the ancestor closure (self + parents, merge
  nodes union every parent):
  - Claim *presence*: referenced by an ancestor checkpoint, or created
    at or before the tip and never referenced anywhere (a project fact).
  - *Signal*: `compute_signal` over validations whose recording
    checkpoint is in the ancestor set.
  - *Grounding*: evidence recorded on an ancestor checkpoint, plus
    hand-attached evidence (no recording checkpoint) with
    `created_at <= tip`.
  - *Instruments*: `tool_invocations` on `from..to` (ancestors of `to`
    minus ancestors of `from`).
- **Ancestry.** Whether `from` is an ancestor of `to` (and vice versa),
  whether the tips diverged, the newest lowest common ancestor, and the
  exclusive checkpoint id lists — sorted.
- **Frontend.** Compare bay under Tags on Research. Two pickers (main
  tip, line tips, tags, commits). Public. Sentence-case. No write.
- **Docs.** Vision `diff` marked *(built)*; blueprints / TLDR / README /
  changelog / roadmap.

## Tests

- DB-free: OpenAPI path is GET-only and does not require
  `X-Dev-Actor-Id`; ancestor walk (linear + merge); LCA on a diamond;
  claim classify (empty / added / removed / status_changed); instrument
  collector skips malformed tuples and sorts stably.
- DB-gated (skip without `TEST_DATABASE_URL`): empty delta on the same
  tip and on two idle checkpoints; claim signal `none → validated`;
  grounding `ungrounded → D` from a hand-attached paper; `calc.eval`
  outcome on the interval; unknown UUID / name is `404` and the
  checkpoint count does not rise; two identical GETs match; `main` /
  branch id / tag name resolve; reverse direction inverts the signal.

## What did not change

- Ledger writes still go only through `create_checkpoint`.
- Append-only guards are untouched.
- Funder / contributor / validator stay separate tables.
- No Alembic revision — `0019` stays the head on `main`. In-flight
  `0.28.0` may take `0020`; this release does not collide.
- Blame-as-an-op is still planned.

## Caveats (honest)

- Claim *fields* (`statement`, stored `status`, `confidence`) have no
  history table. Presence and the derived signal / grounding are what
  this diff can honestly report.
- Hand-attached evidence is timestamp-aligned, not line-aligned (it
  never recorded a checkpoint). Tool-run evidence is line-aligned via
  `checkpoint_refs`.
- A tag and a branch that share a name: the tag wins.
- No pixel-level browser walk of the Compare bay (same owed eyeball
  pass as `0.14.0`–`0.16.0`).

## Verification

Recorded in `docs/changelog.md` after the local lint / pytest /
frontend run on this branch.
