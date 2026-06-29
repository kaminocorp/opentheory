# `Account` owns `Actor` — Phase 1 Completion (Backend domain models)

> Implements **Phase 1** of `docs/executing/account-owns-actor-implementation-plan.md`. Adds the
> `Account` ORM model and relocates the principal-level columns off `Actor` / `FundingAllocation`
> at the SQLAlchemy layer. **Metadata only** — no migration yet (that's Phase 6); the live schema
> is unchanged until cutover.

**Status:** ✅ **GATE GREEN.** `from app.models import *` + `configure_mappers()` succeeds; the
column sets are exactly as designed; `uv run ruff check .` passes.

> ⚠️ **Intermediate-state warning (by design).** This is a *ship-together* destructive change
> (plan §"Sequencing & deploy strategy"). After Phase 1 the **models** are converted but the
> **service/route layer still reads the old shape** (`services/funding.py` references
> `allocation.actor_id` / `actor.id`; `api/deps.py` reads `Actor.external_id`; `core/roles.py`
> reads `actor.roles`). Those are *function-body* attribute reads, so everything still **imports
> and collects** — but the funding and auth-provision code paths are **runtime-broken until
> Phases 3–4 land**. This is expected and matches the plan; the backend is only whole again at the
> end of the release (Phases 4–5), verified in Phases 7/9. Do not deploy a partial cut.

---

## What landed, where, and why

### A1.1 — new `backend/app/models/account.py`

The `Account` principal. Columns: `external_id` (`String(255)`, **unique**, nullable — the JWT
`sub`, moved off `actors`), `display_name` (not null), `email` (nullable, promoted out of
`actor_metadata`), `roles` (`ARRAY(String)`, not null, `server_default "'{}'"` — moved off
`actors`), `account_metadata` (`JSON`), plus `id`/`created_at`/`updated_at` from the mixins.
Relationships: `actors` (1→N) and `funding_allocations` (1→N).

- **Import choice:** `ARRAY` is imported from `sqlalchemy.dialects.postgresql` (not the generic
  `sqlalchemy.ARRAY` in the proposal's sketch) to match `actor.py`'s existing `roles` definition
  **byte-for-byte** — the column is *moving*, so keeping the identical PG `text[]` type means the
  Phase 6 migration is a clean relocate, not a type change.
- **Not append-only guarded** — `Account` is a mutable identity row (like `Branch.status` and the
  old `actors.roles`). `models/append_only.py` was deliberately **not** touched (see A1.5).

### A1.2 — `backend/app/models/actor.py`

- **Removed** `external_id` and `roles` columns (both moved to `Account`).
- **Added** `account_id: Mapped[UUID | None]` → FK `accounts.id` `ondelete="SET NULL"`, nullable
  (`system` and dev-bootstrap actors are account-less).
- **Added** `account = relationship("Account", back_populates="actors")`.
- **Removed** the `funding_allocations` relationship (funding now hangs off `Account`).
- **Import cleanup:** dropped the now-unused `text` and `ARRAY` imports; added `ForeignKey`,
  `UUID`, and the PG `UUID` alias. (This is why ruff stays clean — no orphan imports.)
- **No plain index on `actors.account_id`** (deliberate): the Phase 6 partial unique index
  `uq_actors_one_human_per_account ON actors(account_id) WHERE type='human'` doubles as the lookup
  index for the auth resolve query (which filters `type='HUMAN'`), so a second btree would be
  redundant. This matches the migration sketch (step 2 adds the column with no index; step 6 adds
  the partial unique index).

### A1.3 — `backend/app/models/funding.py`

- `actor_id` → **`account_id`** (FK `accounts.id`, `ondelete="SET NULL"`, `index=True` — kept the
  index because there is no covering index here, unlike `actors`).
- `actor` relationship → **`account`** (`back_populates="funding_allocations"`).
- The append-only guard still applies (the model is unchanged in that respect; only the FK target
  moved). The `fund` Contribution attribution is **not** here — it stays actor-attributed in the
  service (Phase 4).

### A1.4 — `backend/app/models/__init__.py`

Added `from app.models.account import Account` and `"Account"` to `__all__`. **Critical for
autogenerate:** Alembic's `env.py` does `from app.models import *`, so a model missing from
`__all__` is silently invisible to migration generation (CLAUDE.md). Verified `accounts` is now
discoverable.

### A1.5 — `models/append_only.py` confirmed unchanged

`_APPEND_ONLY_MODELS = (Checkpoint, CheckpointRef, FundingAllocation, Validation)` — `FundingAllocation`
remains guarded (the FK target changed, not its append-only nature), and `Account` is correctly
**absent** (mutable identity row).

---

## Gate verification (reproduced, not asserted)

```
$ uv run python -c "from app.models import *; from sqlalchemy.orm import configure_mappers; configure_mappers(); ..."
models import + mappers configure OK
Account cols: account_metadata, created_at, display_name, email, external_id, id, roles, updated_at
Actor cols  : account_id, actor_metadata, created_at, display_name, id, type, updated_at
Funding cols: account_id, amount, created_at, currency, id, kind, notes, payment_reference, project_id, source, status, updated_at
$ uv run ruff check .
All checks passed!
```

- `configure_mappers()` (not just `import *`) was run on purpose: it eagerly resolves the
  string-based `relationship()` targets and `back_populates` pairings, so the removal of
  `Actor.funding_allocations` and the new `Account ↔ Actor` / `Account ↔ FundingAllocation` links
  are validated **now**, not at first query.
- Column sets confirm: `Actor` lost `external_id`/`roles` and gained `account_id`; `Account` has
  `external_id`/`email`/`roles`; `funding_allocations.actor_id` is now `account_id`.

## Deferred to later phases (not done here, on purpose)

- The **migration** (`0006_accounts.py`) — Phase 6. Until it runs, the live DB still has the old
  columns; these model edits would mismatch a live query, which is why the migration + new code
  must deploy together (Phase 9).
- The runtime fixes that consume the new shape: `core/roles.py` + `api/deps.py` (Phase 3),
  `services/funding.py` (Phase 4), schemas (Phase 2), routes (Phase 5).

## Gate result

**Models import, mappers configure, ruff clean → Phase 1 gate is GREEN.** Cleared to proceed to
Phase 2 (Pydantic schemas).
