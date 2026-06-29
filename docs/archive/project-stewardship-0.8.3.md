# Project Stewardship — `0.8.3` Account `@username` — Completion

> Implements the **account `@username`** release of
> `docs/executing/project-stewardship-and-collaboration.md` (proposal §4.2) via the
> `0.8.2` task block of `docs/executing/project-stewardship-implementation-plan.md` (tasks
> **T2.1–T2.9**). Gives every `Account` a unique, public, renameable `@handle` — the prerequisite
> for inviting an existing user by handle. The invitations + bell-inbox slice (ask **(C)**) is the
> next release and is **not** in this one.

**Status:** complete pending live verification. Backend `ruff` clean and the DB-free suite green
(**52 passed / 65 skipped**); frontend `typecheck` / `lint` / `build` all green (9/9 routes).
Model↔migration parity verified by compiling the `accounts` DDL against the Postgres dialect. **Not
run here:** the new DB-backed tests against a real Postgres, and the in-browser rename pass — both
need the deployed Supabase (or an explicitly-greenlit throwaway DB), so they are the post-deploy live
check (consistent with the no-local-DB policy).

**Version — a deliberate renumber.** The implementation plan calls this `0.8.2`, but the repo's
`0.8.2` slot already shipped as the **stewardship hardening** (sole-owner-demote guard + duplicate-
slug `409`, live in the code). Per that changelog entry's own note, `@username` is **`0.8.3`** and
invitations move to **`0.8.4`**. Confirmed with @phil before implementing. The release entry is in
`docs/changelog.md`; this doc is the implementation-scoped detail.

---

## Scope of change

**New files**
- `backend/app/core/usernames.py` — pure, DB-free handle normalization/generation helpers.
- `backend/alembic/versions/0008_account_username.py` — additive column + hand-authored backfill.
- `backend/tests/test_usernames.py` — DB-free util + schema + `PATCH /me` auth-gate tests.
- `backend/tests/test_accounts.py` — DB-backed provisioning / rename / resolver / PII tests.

**Modified**
- `backend/app/models/account.py` (+`username`, `uq_accounts_username` in `__table_args__`),
  `services/account.py` (+`generate_unique_username`, username on bootstrap,
  `resolve_account_by_identifier`), `api/deps.py` (auto-generate on first sign-in + two-race
  disambiguation), `api/routes/me.py` (+`PATCH /me`), `schemas/account.py` (+`username` on
  `AccountRead`/`AccountSummary`, +`AccountUpdate`), `schemas/project.py` (member-summary doc).
- `frontend/src/types/research.ts` (+`username`, `AccountUpdate`), `lib/api.ts` (+`updateMe`),
  `components/shell/auth-menu.tsx` (inline `@handle` editor),
  `components/workspace/collaborators-panel.tsx` (show `@handle`).

---

## Design guardrail (carried from the line): the handle is identity, not credit

`@username` lives on the **`Account`** (the principal, 0.7.0) — the same grain as project ownership,
membership, and funding attribution. It is a public *identity* attribute, not an intellectual-credit
role: renaming a handle records **no** `Contribution`/`Validation`/`FundingAllocation`. The `Account`
is a mutable identity row (like `Branch.status`), so a handle edit is a plain in-place mutation —
never a ledger event, never append-only guarded.

---

## What landed, where, and why

### 1. `core/usernames.py` — the pure handle vocabulary (T2.1)

DB-free, deterministic, unit-tested in isolation:

- `normalize(raw)` — lowercases, replaces runs of disallowed chars with `_`, collapses/trims
  underscores, pads short (`< 3` → zero-padded), truncates to 30. **No** randomness, **no**
  reserved-name logic — those layer on top. Output always matches `^[a-z0-9_]{3,30}$`.
- `base_from(email, display_name)` — email local-part → display name → `"user"`, **skipping reserved
  sources** so the generator only ever suffixes for *uniqueness*, never to dodge a reserved word.
- `generate_username_candidates(base)` — yields `base`, `base2`, `base3`, … (lazy, unbounded;
  `with_suffix` keeps each ≤ 30 chars).
- `is_valid_username`, `USERNAME_PATTERN`, `RESERVED_USERNAMES` — shared by the schema validator.

### 2. Model + named unique constraint (T2.2)

`accounts.username` `String(30)` `NOT NULL`. Uniqueness is declared as a **named**
`UniqueConstraint("username", name="uq_accounts_username")` in `__table_args__` (not column-level
`unique=True`, which auto-names) so the test harness's `create_all` builds exactly what migration
`0008` installs — the `uq_actors_one_human_per_account` discipline.

### 3. Provisioning + collision handling (T2.2)

Two insert paths now mint a handle:

- **`_resolve_or_provision`** (real first sign-in, `api/deps.py`): generates from
  `base_from(email, display_name)` and commits the `Account` + primary `Actor` as before. The key
  move — **the existing `IntegrityError`→rollback→re-read now disambiguates two races without parsing
  constraint names:** a re-read winner (`scalar_one_or_none`) means an `external_id` race → return
  the winner; **no** winner means a `username` collision with a *different* principal → regenerate
  and retry (bounded by `_PROVISION_RETRIES`; exhaustion → `503`, retryable).
- **`services/account.py::create_account`** (dev/test bootstrap behind `auth_dev_header_enabled`):
  mints a handle and retries on the unique race, so two bootstraps with the same display name get
  distinct handles.

`generate_unique_username(db, base)` pre-queries the handles sharing `base`'s prefix in one
round-trip (escaping the `_` LIKE-wildcard — over-matching would only ever add *real* taken handles,
but escaping keeps the query honest), unions in `RESERVED_USERNAMES`, and returns the first free
candidate. It is *advisory* — the caller's `INSERT` (guarded by `uq_accounts_username`) is the final
arbiter, which is why both insert paths still retry.

### 4. Schemas (T2.3)

`username` added to `AccountRead` (the gated `/me` read) and the **public** `AccountSummary` (a
public handle — safe to expose, and *required* for invite-by-handle). New `AccountUpdate`:
normalizes (trim/lowercase) **before** validating against `^[a-z0-9_]{3,30}$` and the reserved set
(both → `ValueError` → `422`). Rename does **not** auto-slug — input must already be a valid handle
(a space/hyphen is a `422`, not a silent rewrite); uniqueness is the route's `409`, not validated
here.

### 5. `PATCH /me` (T2.4)

`api/routes/me.py` gains `update_me(payload: AccountUpdate, actor, db)`:

- **Authorization is implicit** — the handle is written to `actor.account`, i.e. *this* caller's
  account, so a principal can never rename anyone else.
- A same-handle write short-circuits to a no-op `200` (no needless write, no spurious self-`409`).
- A `uq_accounts_username` violation → rollback → clean `409`; an account-less actor (a `system`/dev
  actor with no principal) → `403`.
- `expire_on_commit=False` keeps the eager-loaded `account` populated, so `MeRead` serializes the new
  handle + bumped `updated_at` without a relationship lazy-load.

### 6. Migration `0008_account_username` (T2.5)

Additive column + **hand-authored backfill** (like `0006`): add nullable → assign every existing
account a unique handle (deterministic `ORDER BY created_at, id`; a `taken` set seeded with the
reserved words + every handle minted so far, suffixing on collision) → `create_unique_constraint`
+ `alter_column NOT NULL`. The slug/dedupe logic is **re-inlined** in the migration rather than
imported from `app.core.usernames` — a migration must stay *frozen* (a later change to the app helper
must not retroactively alter a past migration), the same reason `0006` used only raw SQL. It need not
match the app byte-for-byte; it only has to mint *valid, unique* handles at backfill time. Ships
**with** the provisioning code (the `NOT NULL` would break the next sign-in if code lagged).

### 7. Frontend (T2.6 / T2.7)

- **Types/client**: `username` on `Account` / `AccountSummary` (so `Me` inherits it via
  `Actor & { account }`), new `AccountUpdate`; `updateMe({ username })` posting `PATCH /me` through
  the existing `patchInit` helper.
- **`auth-menu.tsx`**: the signed-in dropdown renders the `@handle` as a click-to-edit affordance —
  an `Input` + Save/Cancel driven by a `useMutation` over `updateMe`. On success it invalidates the
  `["me"]` query prefix (which `useActingIdentity` keys as `["me", credentialKey]`), so the new
  handle shows immediately; on error it strips the `NNN:` status prefix off the backend `detail`
  (e.g. *"That username is already taken"*). The editor state resets on sign-out.
- **`collaborators-panel.tsx`**: each member row now shows `display_name` + a muted `@handle`
  (the file's own `0.8.1` comment flagged this swap for the username release).

---

## Tests (T2.8)

- **DB-free** (`tests/test_usernames.py`, always runs): `normalize` table (slug/pad/truncate/
  non-ascii), the "output always matches the pattern" invariant, `base_from` precedence +
  reserved-source skipping, `with_suffix` length cap, sequential candidates, `is_valid_username`,
  `AccountUpdate` accept/normalize + reject (short/long/space/hyphen/reserved/empty), and the
  `PATCH /me` unauthenticated `401` gate (rejected by `ActingActor` before any DB access via
  `dbfree_client`).
- **DB-backed** (`tests/test_accounts.py`, skip without `TEST_DATABASE_URL`): bootstrap
  auto-generates a unique handle + suffixes on collision (`ada_lovelace` → `ada_lovelace2`); handle
  derives from the email local-part over a reserved display name; `PATCH /me` rename happy path
  (normalized + persisted), same-handle no-op, cross-account collision `409`, invalid/reserved
  `422`; `resolve_account_by_identifier` resolves by `@username` and (case-insensitive) email and
  returns `None` for misses; the public member-list `AccountSummary` exposes `username` but omits
  `email`/`roles`/`external_id`.

## Verification commands

```bash
cd backend && uv run ruff check . && uv run pytest          # 52 passed / 65 skipped (no DB)
cd frontend && npm run typecheck && npm run lint && npm run build   # all green, 9/9 routes
```

Model↔migration parity (no DB needed):

```bash
cd backend && uv run python -c "from sqlalchemy.schema import CreateTable; \
from sqlalchemy.dialects import postgresql; from app.models.account import Account; \
ddl=str(CreateTable(Account.__table__).compile(dialect=postgresql.dialect())); \
assert 'username VARCHAR(30) NOT NULL' in ddl and 'uq_accounts_username' in ddl"
```

## Follow-ups (not this slice)

- **`0.8.4`** — `ProjectInvitation` + invite-by-`@username`/email, accept/decline, the top-right
  bell inbox; the collaborators panel grows an invite form. `resolve_account_by_identifier` (shipped
  here) is its resolver.
- **Caveat carried forward (proposal §7):** `accounts.email` is **not** uniqueness-enforced, so
  email-based invite resolution treats a rare multi-match as ambiguous — the invite service is where
  that becomes a `409`. A follow-up could add a `lower(email)` unique constraint if we want
  unambiguous email findability.
- **Live (manual):** after `fly deploy`, confirm the `0008` backfill gave existing accounts a handle
  and that rename works on the live deploy; optionally run the DB-backed suite against a throwaway
  Postgres for a dedicated verification pass.
