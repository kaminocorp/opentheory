# `Account` owns `Actor` — Phase 4 Completion (Funding service rewiring)

> Implements **Phase 4** of `docs/executing/account-owns-actor-implementation-plan.md`. The one
> ledger FK that moves (`FundingAllocation` funder = the **Account**, Decision #5) is wired through
> the funding service. The `fund` **Contribution stays actor-attributed** — *allocation = the
> account's money; contribution = the actor's act.*

**Status:** ✅ **GATE GREEN.** `uv run ruff check .` passes; `app.services.funding` imports clean;
`git diff` confirms **`services/funding.py` is the only service touched** (checkpoint chokepoint and
all other services untouched).

> ⚠️ **Intermediate-state note.** Funding *write/read* code is now account-correct, but the live DB
> still has the old `funding_allocations.actor_id` column until migration `0006` (Phase 6). The
> DB-backed `test_funding` still asserts the old `body["actor"]` shape and drives funding via a dev
> actor that is now account-less → the native gate will `403` it until Phase 7 rewires those tests
> to bootstrap an internal `Account` (which Phase 5's `POST /accounts` + dev-actor linking enables).

---

## What landed, where, and why (`backend/app/services/funding.py`)

### A4.1 — `create_funding`: allocation attributes to the principal

- `FundingAllocation(account_id=actor.account_id, …)` (was `actor_id=actor.id`).
- **Native gate unchanged in code** — still `if payload.source == NATIVE and not
  actor_is_internal(actor): 403`. The predicate is the same call; what changed (Phase 3) is that
  `actor_is_internal` now walks `actor.account.roles`. A dev/account-less actor → no account → not
  internal → `403`, the intended behavior.
- **Invariant relied on:** by the time the allocation is built, the native gate has proved the actor
  is internal, which *requires* an account — so `actor.account_id` is non-null for any native
  allocation (documented inline).
- **`fund` Contribution unchanged** — `record_contribution(…, action=ACTION_FUND, actor=actor,
  funding_allocation_id=allocation.id, checkpoint_id=None)`. `Contribution.actor_id` stays on the
  actor (Decision #5/#6); the service still owns the single `commit`, so allocation + contribution
  remain atomic.

### A4.2 — `_enrich` / `_to_read`: resolve the funder Account

- `_to_read(allocation, account: AccountSummary | None)` now builds `FundingRead(account_id=…,
  account=…)` (was `actor_id`/`actor`).
- `_enrich` batches a single `select(Account).where(Account.id.in_(account_ids))` (was over `Actor`),
  keyed by `allocation.account_id` — still one query, no N+1.
- Resolves to **`AccountSummary`** (`id` + `display_name`, **no email**) — the privacy-safe shape
  decided in Phase 2, since the funding read endpoints are public.
- **Import churn:** added `app.models.account.Account` + `app.schemas.account.AccountSummary`;
  removed `app.schemas.checkpoint.ActorSummary` (now unused — ruff would have flagged it). `Actor`
  is still imported (the `create_funding(..., actor: Actor)` annotation).

### A4.3 — `project_budget` confirmed unchanged

Re-read: it reads only `FundingAllocation.amount` / `status` / `source` / `currency` — it never
referenced the funder — so its output is identical and now principal-attributed "for free" (the
totals are the same numbers regardless of whether the funder is an actor or an account).

---

## Gate verification (reproduced, not asserted)

```
$ uv run ruff check .
All checks passed!
$ uv run python -c "import app.services.funding"   → services.funding imports OK
$ git diff --name-only app/services/               → backend/app/services/funding.py   (only)
```

The "only `funding.py` changed" check is the Phase 4 gate's real content: the checkpoint chokepoint
(`services/checkpoints.py`) and every composing service receive a resolved `Actor` exactly as
before — the Account-owns-Actor change does not reach them.

## Deferred / needs a DB (not verifiable here)

- Runtime proof that a native allocation's `account_id` is the funder's account, that the `fund`
  contribution is still actor-attributed, and that `project_budget` output is unchanged — Phase 7
  (DB-backed tests) and Phase 9 (live).
- The dev-actor funding path needs `_resolve_dev_actor` to eager-load `account` (otherwise
  `actor_is_internal` async-lazy-loads on a *linked* dev actor) — folded into **Phase 5**, where
  dev-actor↔account linking is introduced.

## Gate result

**Ruff clean, service imports, only `funding.py` touched → Phase 4 gate is GREEN.** Proceeding to
Phase 5 (API routes).
