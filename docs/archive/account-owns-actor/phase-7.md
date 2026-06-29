# `Account` owns `Actor` — Phase 7 Completion (Backend tests)

> Implements **Phase 7** of `docs/executing/account-owns-actor-implementation-plan.md`. Makes the
> test suite account-aware: the moved fields (`external_id`/`roles`/funding attribution) are asserted
> in their new home, the one-`human`-per-account index is exercised, and the funding tests prove the
> Decision-5 split (allocation → Account, `fund` contribution → Actor). DB-free gates run now;
> DB-backed assertions are written and **collect cleanly**, sequenced to run in Phase 9.

**Status:** ✅ **GATE GREEN** (the Phase 7 gate is *"DB-free subset green with the new collection;
DB-backed assertions ready to run in Phase 9"*). `uv run ruff check .` passes; `uv run pytest -q` →
**12 passed / 49 skipped** (was 9 / 47: **+3 DB-free** gate tests pass, **+2 DB-backed** tests
collect and skip without a database).

**Files:** `tests/conftest.py` (+ `internal_funder` factory fixture), `tests/test_auth.py`,
`tests/test_funding.py`, `tests/test_actors.py`, `tests/test_wiring.py`.

---

## What landed, where, and why

### A7.1 — `conftest.py`: an `internal_funder` factory fixture (no seeding)

Roles moved off `actors`, so the retired `POST /actors {roles:[...]}` seed no longer works. Added a
factory fixture: `internal_funder(client, *, roles=("internal",))` creates an **internal `Account`**
+ a linked **`human` `Actor`** and returns `(actor_id, account_id)` — the actor id for the
`X-Dev-Actor-Id` header, the account id for funder-attribution assertions. This is "build the funder
you need explicitly" (Decision #8), shared across the funding and dev-bootstrap tests.

### A7.2 — `test_auth.py`: JIT provisioning mints an Account **and** its primary Actor

- **Idempotency test** rewritten: `/me` now serializes `MeRead`, so `external_id`/`roles` are
  asserted under `body["account"]`. The DB assertions confirm **exactly one `Account`** for the
  subject and **exactly one `human` `Actor`** owned by it (the unique guard moved to
  `accounts.external_id`); email is on the principal *and* mirrored into `actor_metadata`.
- **Internal-role test**: the allowlist grant lands on `account.roles` (`body["account"]["roles"]`).
- **Dev-header-survives test**: a bare dev actor is now asserted **account-less**
  (`account_id is None`) instead of `roles == []`.
- The race fallback (`IntegrityError` re-read) is covered in spirit by the idempotency assertion
  (one account, one actor on repeat) — a true concurrent first-login race needs real parallelism and
  isn't forced deterministically here; flagged, not silently dropped.

### A7.3 — `test_actors.py`: PII gate now covers `/accounts`

Added DB-free `GET`/`POST /accounts` gate tests (404 when `auth_dev_header_enabled` is off, *before*
any DB access — they use the `dbfree_client`). `AccountRead` exposes `external_id` + email + `roles`
(the 0.6.1 email-harvest class, *moved here with the fields*), so the gate moved with them. The
module docstring records the new PII split (`ActorRead` keeps the email in `actor_metadata`;
`AccountRead` holds external_id/email/roles).

### A7.4 — `test_funding.py`: account-attributed, with the Decision-5 split locked

- Internal funders built via `internal_funder` (was the role-seeded actor).
- The settled-allocation test now asserts **both** sides of Decision #5 in the DB:
  `allocation.account_id == account_id` (money → principal) **and** `contribution.actor_id ==
  actor_id` (the `fund` act → actor), plus the existing "no checkpoint minted" (Decision #3).
- The funding read carries the privacy-safe `AccountSummary` (`rows[0]["account"]` has `id` /
  `display_name`, **no `email`**) — asserted in the list test.
- The internal-role gate is now two tests: an **account-less** actor (403) **and** an actor with a
  **non-internal account** (403) — proving the gate reads `account.roles`, not "has an account".
- The direct pending-allocation insert uses `account_id` (was `actor_id`).

### A7.5 — `test_auth.py`: the one-`human`-per-account index is enforced

New DB-backed test: a second `human` `Actor` on the same account raises `IntegrityError`, while an
`agent` actor on that account commits fine (the partial predicate is `type='HUMAN'`). This only
passes because the index is **declared on the model** (Phase 6 deviation) — `create_all` (the test
schema) installs it identically to migration 0006.

### A7.6 — `test_wiring.py`: `/accounts` wired and shaped

`test_new_paths_exist` now asserts `POST`/`GET /accounts` exist; a new
`test_account_create_takes_no_acting_actor` mirrors the `/actors` carve-out (the bootstrap mints
accounts, so it declares no `X-Dev-Actor-Id`). `/accounts` is intentionally **not** in `WRITE_PATHS`
(those require an acting actor), exactly as `/actors` is handled.

## Gate verification (reproduced, not asserted)

```
$ uv run ruff check .                 → All checks passed!
$ uv run pytest -q                    → 12 passed, 49 skipped in 0.45s
    DB-free +3:  /accounts GET+POST gates (test_actors), /accounts no-acting-actor (test_wiring)
    DB-backed +2 (collect→skip):  one-human-per-account index, non-internal-account 403
```

## Owed to Phase 9 (sequenced, not skipped)

- **Run the DB-backed suite on a throwaway Postgres** (greenlight required). Every assertion above
  marked "DB-backed" is written and *collects*, but only a real engine proves: JIT mints one
  Account+Actor; the partial unique index fires; native funding attributes the allocation to the
  account while the `fund` contribution stays actor-attributed; `project_budget` output is unchanged;
  the funding read hides the funder email. These run in A9.1 alongside the migration round-trip.
- **Concurrent first-login race** (exactly one account, no orphan) remains characterized rather than
  asserted — it exercises the `IntegrityError` re-read in `_resolve_or_provision`, which needs true
  parallelism to trigger deterministically.

## Gate result

**Ruff clean; DB-free subset green (12 passed) with the new collection; DB-backed assertions written
and collecting → Phase 7 gate is GREEN.** Proceed to Phase 8 (frontend).
