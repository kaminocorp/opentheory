# `Account` owns `Actor` — Phase 9 (Cutover, changelog)

> Implements **Phase 9** of `docs/executing/account-owns-actor-implementation-plan.md` — the
> coordinated cutover. **Workflow note (corrected):** this project has **no throwaway/staging
> Postgres** — schema changes go **straight to the prod Supabase DB**, and the migration is applied
> **by the Fly deploy's `release_command`** (`alembic upgrade head`), which runs in a temporary
> machine immediately before the new code serves (`docs/deploy.md`). So the plan's original
> "throwaway-DB round-trip" gate is **retired**: the gate is instead the **read-only pre-cutover
> audit** (done, below) plus **live verification** after `fly deploy`. There is deliberately **no**
> manual `alembic upgrade head` against prod ahead of the deploy — that would drop `actors.roles` /
> `funding.actor_id` while the currently-deployed *old* backend still reads them.

**Status:** 🟦 **CODE-COMPLETE; pre-flight audit GREEN; live `fly deploy` cutover is the remaining
step.** Phases 1–8 are done and green (backend `ruff` + DB-free `12/49`; frontend
`typecheck`/`lint`/`build` `6/6`). A9.1 (pre-flight prod audit) and A9.4 (changelog) are done.
A9.2/A9.3 (the `fly deploy` cutover + live verification) and A9.5 (executing→completions move) are
the remaining steps, sequenced to the deploy.

---

## A9.4 — Changelog (done)

`docs/changelog.md` gains a **`0.7.0`** entry (index bullet + full section) framed as the *opening,
identity slice* of `0.7.0` (Agent-Ready Execution Surface) — it lays the principal/provenance split
that agent ownership and real money require, without shipping agent execution. The entry records what
moved (`external_id`/`roles`/funding → `accounts`), what didn't (research provenance FKs + the
`ActingActor` contract), the destructive `0006` migration, the API surface, the verification
reproduced so far, and the **"still gating the production push"** list. Versioning follows the
proposal's locked recommendation ("land it as the opening slice of `0.7.0`").

## A9.1 — Pre-cutover prod audit (done; GREEN)

Re-ran the Phase 0 read-only audit against the **live** DB at cutover time (auth is live, so rows
could have appeared since Phase 0). Read-only `SELECT`s via the app's configured engine
(`scratchpad/preflight_audit.py`), uppercase enum labels, counts only:

| Check | Result | Required |
|---|---|---|
| human actors w/ NULL `external_id` | 0 | 0 |
| duplicate `external_id` | 0 | 0 |
| agent/system carrying a `sub` | 0 | 0 |
| non-human funder | 0 | 0 |
| `actors` total / `funding_allocations` total | 0 / 0 | — |

**GATE GREEN.** The live `actors` / `funding_allocations` tables are still empty, so `0006`'s
backfill moves **0 rows** and the destructive drops are on empty columns — **zero data-loss risk**.
(The migration's DDL + downgrade SQL are not exercised by row data here; they were verified
structurally in Phase 6 via the metadata↔DDL cross-check. Per the project workflow there is no
throwaway DB on which to row-exercise them — the live empty DB *is* the target.)

## A9.2 / A9.3 — Live cutover + verification (the `fly deploy` path)

The migration ships **with** the backend via Fly's `release_command` — one command, correct
ordering, no manual pre-migration:

```bash
cd backend
fly deploy            # builds the new image (Phases 1–5 + 0006), then the release_command runs
                      # `alembic upgrade head` in a temp machine (applies 0006 to prod over the
                      # direct connection), then the new code serves.
```

Then redeploy the frontend (the new types / `NEXT_PUBLIC_*` are baked at build — Vercel rebuilds on
a push to the connected branch, or `vercel --prod`).

**Verify live (A9.3), non-destructive:** sign in → `/me` returns the nested `account` with `roles`;
the identity menu shows the internal badge for an allowlisted email; an internal user funds a project
and the allocation/budget reflect it; a non-internal user is `403`'d; funding history shows the
account as funder. (`GET /api/v1/health` and a signed-in `GET /api/v1/me` shape-check are the quick
smoke checks I can run against prod afterward.)

> **Rollover caveat (low-risk here):** Fly applies the migration *before* the new machines are
> healthy, so for the brief rollover window any still-running *old* machine serves against the new
> schema. With `min_machines_running = 0` (scale-to-zero), an empty DB, and preview-level traffic,
> that window is effectively nil — but it's why the migration must go via `fly deploy`, not ahead of
> it.

## A9.5 — executing→completions move: **why not moved yet**

The plan's last step moves `account-owns-actor.md` + `…-implementation-plan.md` from
`docs/executing/` to `docs/completions/`. I left them in `docs/executing/` **on purpose**: that
lifecycle move is the repo's signal that a release is *shipped*, and the live cutover (A9.2) is still
pending a greenlight. Moving them now would misreport an un-cut-over release as done. **Do the move as
the final step of the greenlit cutover**, alongside flipping this note's status to ✅ and confirming
the changelog's "still gating" list is cleared. (The per-phase completion notes already live under
`docs/completions/account-owns-actor/`, so the *work record* is in place; only the source-of-intent
docs wait for cutover.)

## Gate result

**Code-complete and green offline (backend `ruff` + DB-free `12/49`; frontend
`typecheck`/`lint`/`build` `6/6`); pre-cutover prod audit GREEN; changelog landed.** The one
remaining step is the **`fly deploy` cutover** (applies `0006` via the release command + ships the
new backend) and the **Vercel redeploy**, then live verification (A9.3). Those are a production
deploy, so they wait on the user's go-ahead; once done, do the A9.5 executing→completions move and
flip this status to ✅.
