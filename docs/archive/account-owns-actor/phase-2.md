# `Account` owns `Actor` — Phase 2 Completion (Pydantic schemas)

> Implements **Phase 2** of `docs/executing/account-owns-actor-implementation-plan.md`. Adds the
> `Account` request/response schemas and relocates the moved fields out of the `Actor` schemas and
> the funding read. **Schema layer only** — no behavior change here (services/routes consume these
> in Phases 4–5).

**Status:** ✅ **GATE GREEN.** All schemas import with no circular dependency; `ActorRead` no
longer carries `external_id`/`roles`; `uv run ruff check .` passes.

> ⚠️ **Intermediate-state warning (unchanged from Phase 1).** `services/funding.py::_to_read`
> still constructs `FundingRead(actor_id=…, actor=…)` — kwargs that **no longer exist** on
> `FundingRead` after this phase — so funding reads raise at runtime until Phase 4 rewires them.
> Import/collect still succeed (the broken call is in a function body). Ship-together release.

---

## 🔐 Deviation from the proposal (deliberate, security-driven): `AccountSummary` omits `email`

The proposal specifies `AccountSummary (id, display_name, email)` and nests it in `FundingRead`.
**I dropped `email`** — `AccountSummary` is `{ id, display_name }`. Reason:

- All three funding **read** endpoints are **public** (no `ActingActor`):
  `GET /projects/{id}/funding`, `GET /funding/{id}`, `GET /projects/{id}/budget`
  (`api/routes/funding.py`).
- Today's nested `ActorSummary` carries **no email** (`id, display_name, type` only —
  `schemas/checkpoint.py`), precisely so the public funding history leaks no PII.
- An `AccountSummary` *with* email in a public `FundingRead` would re-open the anonymous
  email-harvest class that `0.6.1` closed and `0.6.8` regression-tested — while the proposal itself
  claims "the PII gate is preserved." So the conceptually-sound reading (the one the review
  repeatedly chose) is: keep email **off** the public funder summary.

Email/roles/`external_id` remain on the **gated** `AccountRead`, surfaced only via authenticated
`/me` (your own principal) and the dev-gated `/accounts` (Phase 5). **If a funder's email on the
public funding history is actually wanted, that's a one-line add to `AccountSummary` + a decision to
either accept the exposure or gate the funding reads — flagging for sign-off rather than silently
choosing the leak.**

---

## What landed, where, and why

### A2.1 — new `backend/app/schemas/account.py`

- **`AccountBase`** — `display_name` (1–200), `external_id?` (≤255), `email?` (≤255),
  `roles: list[str] = []`.
- **`AccountCreate(AccountBase)`** — adds `account_metadata`. The dev/test bootstrap that inherits
  the seed fields removed from `ActorCreate` (Decision #8 — tests build an internal funder
  explicitly, no seeding).
- **`AccountRead(AccountBase)`** — `+ id, created_at, updated_at`, `from_attributes=True`. **Carries
  the PII** (external_id/email/roles), so only gated endpoints may return it (documented in the
  docstring).
- **`AccountSummary`** — `{ id, display_name }`, `from_attributes=True`. The privacy-safe funder
  display (see deviation above).

### A2.2 — `backend/app/schemas/actor.py`

- **`ActorBase`** — removed `external_id` (was here, inherited by both create+read).
- **`ActorCreate`** — removed `roles`; added optional `account_id` (link a dev actor to a bootstrap
  account). Net fields: `type, display_name, actor_metadata, account_id`.
- **`ActorRead`** — removed `roles`; added `account_id: UUID | None`. Net fields:
  `type, display_name, actor_metadata, id, account_id, created_at, updated_at`.
- **`MeRead(ActorRead)`** — new; adds `account: AccountRead | None`. Chose the **subclass-wrapper**
  the plan recommended (`...actor fields + account`) so `ActorRead` stays the plain entity and
  `/me` owns the nested view. `from_attributes` is inherited, so `MeRead.model_validate(actor)` maps
  the eager-loaded `actor.account` relationship straight onto the nested `AccountRead`.

### A2.3 — `backend/app/schemas/funding.py`

- Import swap: `from app.schemas.checkpoint import ActorSummary` → `from app.schemas.account import
  AccountSummary` (the old import is now unused; left in, ruff would have flagged it).
- `FundingRead`: `actor_id → account_id`, `actor: ActorSummary | None → account: AccountSummary |
  None`. `FundingCreate` unchanged (the client never names the funder — it's resolved from the
  acting actor's account in the service).

---

## Gate verification (reproduced, not asserted)

```
ActorRead fields : type, display_name, actor_metadata, id, account_id, created_at, updated_at
MeRead fields    : (ActorRead…) + account
AccountRead      : display_name, external_id, email, roles, id, created_at, updated_at
AccountSummary   : id, display_name
FundingRead      : id, project_id, account_id, account, amount, currency, kind, source, status, notes, created_at, updated_at
$ uv run ruff check .
All checks passed!
```

- No circular import (`schemas/actor` and `schemas/funding` both import `schemas/account`, which
  imports nothing from them).
- The only `external_id`/`roles` strings left in `schemas/actor.py` are doc-comments, not fields.

## Deferred to later phases

- `services/funding.py` consuming `account_id`/`AccountSummary` (Phase 4) — currently still builds
  the old `actor_*` kwargs (runtime-broken until then).
- `routes/me.py` returning `MeRead`, and the `POST /accounts` / `ActorCreate.account_id` wiring
  (Phase 5).

## Gate result

**Schemas import, fields correct, ruff clean → Phase 2 gate is GREEN.** Cleared to proceed to
Phase 3 (auth resolution + roles).
