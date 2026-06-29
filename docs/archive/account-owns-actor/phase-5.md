# `Account` owns `Actor` — Phase 5 Completion (API routes: `/me`, account bootstrap)

> Implements **Phase 5** of `docs/executing/account-owns-actor-implementation-plan.md`. Exposes the
> `Account` through the API: `/me` returns the nested account, and a dev-gated `/accounts` bootstrap
> lets tests build an internal funder without seeding (Decision #8). With this, the **backend
> read/write surface is account-complete** — every non-migration backend phase (1–5) is done.

**Status:** ✅ **GATE GREEN.** `uv run ruff check .` passes; the app + full OpenAPI schema build;
`/accounts` (POST + GET) is mounted and `/me` serializes `MeRead`; DB-free suite **9 passed / 47
skipped** (== baseline, no regression).

> ⚠️ **Still intermediate.** No migration yet (Phase 6), so the live schema lacks `accounts`; the
> DB-backed tests still encode the pre-change shape (Phase 7). Backend code is whole; the *release*
> isn't until 6–9.

---

## What landed, where, and why

### A5.1 — `routes/me.py` returns `MeRead`

`response_model=ActorRead` → **`MeRead`** (the actor fields + nested `account: AccountRead | None`).
The account is already eager-loaded by `_resolve_or_provision` (JWT path) / set in memory (provision
path) / eager-loaded by the patched `_resolve_dev_actor` (dev path), so serialization never triggers
an async lazy-load. `/me` is authenticated, so the full `AccountRead` (email/roles) is only ever the
caller's **own** principal. The handler still just `return actor` — FastAPI maps it via
`from_attributes`.

### A5.2 — dev-gated account bootstrap (`POST`/`GET /accounts`)

- **`services/account.py`** (new) — `create_account` (`Account(**payload.model_dump())`, single
  commit, refresh) and `list_accounts`, mirroring `services/actors.py`.
- **`routes/accounts.py`** (new) — `POST /accounts` and `GET /accounts`, **both dev-gated** (`404`
  unless `auth_dev_header_enabled`), mirroring the `actors.py` guard. The gate is load-bearing:
  `AccountRead` carries `external_id` + the verified email + `roles` — the exact `0.6.1`
  email-harvest PII class, which *moved here with those fields*. So the PII gate is preserved, just
  relocated from `/actors` to `/accounts`.
- **`api/router.py`** — `accounts` added to the import tuple and mounted at `prefix="/accounts"`,
  `tags=["accounts"]`, next to `actors`.

### A5.3 — `actors` accept an `account_id`; PII comment corrected; dev-resolver eager-loads

- **`services/actors.py::create_actor`** — no logic change needed: `payload.model_dump()` already
  carries the optional `account_id` (added to `ActorCreate` in Phase 2), and `Actor(**dump)` sets it.
  Added a comment explaining the linkage (a dev actor linked to a bootstrap internal `Account` is
  what makes `actor_is_internal` true on the dev funding path) and that `external_id`/`roles` are no
  longer actor fields.
- **`routes/actors.py` `GET /actors` comment** — corrected: `ActorRead` no longer has `external_id`
  (moved to the Account), but `actor_metadata` *still* holds the verified email (set at JIT
  provisioning), so the dev-gate is still justified — now on the email in `actor_metadata`, with the
  principal's `external_id`/`roles` gated on `GET /accounts`.
- **`api/deps.py::_resolve_dev_actor`** — changed `db.get(Actor, id)` →
  `select(Actor).options(joinedload(Actor.account)).where(Actor.id == id)`. **Deviation from the
  plan**, which called this resolver "unaffected": A5.3 introduces dev-actor↔account linking, and the
  funding gate + `/me` then read `actor.account`. A bare `db.get` leaves `account` unloaded, so a
  *linked* dev actor would async-lazy-load → `MissingGreenlet`. Eager-loading fixes it; an
  account-less dev actor (`account_id IS NULL`) short-circuits to `None` with no query, so the change
  is safe for the common case too. (`joinedload` added to the existing `sqlalchemy.orm` import.)

---

## Gate verification (reproduced, not asserted)

```
$ uv run ruff check .                          → All checks passed!
$ uv run python -c "create_app(); app.openapi()"
  account routes: ['/api/v1/accounts', '/api/v1/accounts']   (POST + GET)
  me response_model: ['MeRead']
  OpenAPI schema builds: True
$ uv run pytest -q                              → 9 passed, 47 skipped   (== baseline)
```

## Owed to Phase 7 (characterized, not silently skipped)

- **`test_wiring.py` does not yet cover `/accounts`.** Its `WRITE_PATHS` is a **hardcoded list**, so
  the new route neither breaks nor is exercised by the wiring tests. Phase 7 (A7.6) must add
  `/accounts` to the relevant assertions and the bootstrap-route exception (like the existing
  `test_actor_create_takes_no_acting_actor` carve-out for `/actors`).
- DB-backed proof that `/me` returns the nested account, that a bootstrapped internal `Account` +
  linked dev actor can fund (native), and that `GET /accounts` is gated — Phase 7 + Phase 9.

## Gate result

**Ruff clean, OpenAPI builds, `/accounts` mounted, `/me` → `MeRead`, DB-free at baseline → Phase 5
gate is GREEN.** Backend code (Phases 1–5) is account-complete; remaining: Phase 6 (migration),
Phase 7 (tests), Phase 8 (frontend), Phase 9 (cutover).
