# 0.36.1 — Assessment R1 remediation

**Goal.** Close the P0 and the small P1s from
`docs/plans/codebase-assessment-2026-09-26-r1.md` (assessed against
`71a8929`, filed on `main` as `375733a` / #22). One PR. No file-split
ocean.

**Shape.** Route-level membership on the original ledger POSTs, matching
instruments / agent / campaign. Planner openness from `compute_signal`.
`ClaimCreate` no longer accepts settlement fields. Shared
`resolveOutcomeMeta`. Orchestrator mid-pass policy uses the reservation
quote. Docs catch up to `0.6.0` auth.

Sits on shipped `0.36.0` (`71a8929`) and the assessment commit. **No
schema, no migration.**

## What landed

- **Membership on research writes.** `POST` checkpoint / thread / claim /
  validation / evidence / branch / close / merge / tag / funding call
  `ensure_is_member` (nested paths resolve the project from the loaded
  row). Unauthenticated → `401`. Missing project / parent → `404`.
  Signed-in non-member → `403` and mints nothing. Agent compose paths
  (`create_checkpoint`, `create_branch` inside a pass) stay ungated —
  the commissioning human was already a member.
- **Funding.** Native funding is still `internal`-only **and** now
  membership-gated. A platform comp is not a write against a project
  you have not joined.
- **Frontend.** Project write forms use `useProjectWriteAccess`
  (membership). `canWrite` on `useActingIdentity` stays "signed in" for
  creating a project.
- **Open claims.** `open_claims_for_planner` filters on
  `compute_signal != "validated"`. A human `passed` validation removes
  the claim from the planner. `Claim.status` is not written.
- **`ClaimCreate`.** `status` / `confidence` rejected (`extra="forbid"`).
- **Honesty chrome.** `resolveOutcomeMeta` extracted; agent-trace pills
  reuse it. Proof / satisfy fallthrough is **warn** unless the
  machine-checked flag is true.
- **Reservation rate.** `_policy_from_reservation(agent_run, rate)` —
  the quote that sized the hold, not `rate_for_model`.
- **Docs.** `CLAUDE.md`, `docs/operations/deploy.md`, a membership
  paragraph on `primitives.md`.

## Tests

- DB-free: unauthenticated ledger POSTs → `401`; `ClaimCreate` rejects
  stamped `status` / `confidence`; `claim_is_open_work`; reservation
  policy uses the passed rate; `resolveOutcomeMeta` proof fallthrough.
- DB-gated (local Postgres): non-member `403` on every original write
  surface and the checkpoint count does not rise; validation-only
  settlement empties `_open_claims` while `Claim.status` stays
  `proposed`. Full suite with `TEST_DATABASE_URL`: **860 passed**, 4
  skipped, **7 failed** — the failures are pre-existing toolbench
  write-path drift (stub named `calc.eval` vs sandbox registry;
  geometry `*_latex` companions), not this PR. Without a DB: 649
  passed, 222 skipped.

## What did not change

- `create_checkpoint` is still the only ledger write.
- Append-only guards untouched.
- Funder ≠ contributor ≠ validator.
- Account ≠ Actor.
- Instruments stay `result | refuted | undecided`.
- P2 file splits, CI workflows, `canManageProject` rename, and the
  claim-row confidence percentage are deferred.

## What this does not claim

This completion does **not** claim the PR is merged to `main`.
