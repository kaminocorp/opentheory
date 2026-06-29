# `Account` owns `Actor` — phase completion log

Per-phase implementation notes for the design in
[`docs/executing/account-owns-actor.md`](../../executing/account-owns-actor.md), executed against
the plan in
[`docs/executing/account-owns-actor-implementation-plan.md`](../../executing/account-owns-actor-implementation-plan.md).

Each note records **what was done, where, how, and why**, plus the phase's acceptance-gate result.
This is a **destructive, ship-together release** (drops `actors.external_id`, `actors.roles`,
`funding_allocations.actor_id`), so between Phase 1 and Phases 4–5 the tree is in a *deliberate
intermediate state*: it imports/collects, but the funding path is runtime-broken until rewired. Do
not deploy a partial cut — the migration (Phase 6) and full code (through Phase 5) must ship
together at cutover (Phase 9).

| Phase | Title | Status | Note |
|---|---|---|---|
| 0 | Pre-flight & live data audit (GATE) | ✅ done | [phase-0.md](./phase-0.md) |
| 1 | Backend domain models | ✅ done | [phase-1.md](./phase-1.md) |
| 2 | Pydantic schemas | ✅ done | [phase-2.md](./phase-2.md) |
| 3 | Auth resolution + roles | ✅ done | [phase-3.md](./phase-3.md) |
| 4 | Funding service rewiring | ✅ done | [phase-4.md](./phase-4.md) |
| 5 | API routes (`/me`, account bootstrap) | ✅ done | [phase-5.md](./phase-5.md) |
| 6 | Alembic migration `0006_accounts` | ✅ done | [phase-6.md](./phase-6.md) |
| 7 | Backend tests | ✅ done | [phase-7.md](./phase-7.md) |
| 8 | Frontend (types + identity hook) | ✅ done | [phase-8.md](./phase-8.md) |
| 9 | Round-trip, live cutover, changelog | 🟦 code-complete; round-trip + cutover gated on greenlight | [phase-9.md](./phase-9.md) |

## Cross-phase findings to carry forward

- **Enum-label case (Phase 0).** This DB's named enums use the StrEnum **member names** as labels,
  so `actor_type` is `HUMAN`/`AGENT`/`SYSTEM` (uppercase). The proposal/plan audit + migration SQL
  use lowercase `type='human'` — **that errors against this DB.** Phase 6's raw-SQL backfills must
  use uppercase labels.
- **Empty live DB (Phase 0).** Currently **0 actors, 0 funding rows** — the Phase 6 backfill is a
  no-op against today's data (reconciliation target: 0 accounts created). Re-run the audit at
  cutover; auth is live, so rows can appear before then.
- **`AccountSummary` omits `email` (Phase 2, deviation).** The funding read endpoints are public;
  putting email in the nested funder summary would re-open the `0.6.1` PII-leak class. Email/roles
  stay on the gated `AccountRead` (`/me`, dev-gated `/accounts`). Flagged for sign-off if a public
  funder email is actually wanted.
- **`expire_on_commit=False` is load-bearing (Phase 3).** It keeps the provision path's in-memory
  `actor.account` populated post-commit (so no async lazy-load), which is why `db.refresh` was
  dropped on that path.
- **`_resolve_dev_actor` now eager-loads `account` (Phase 5, deviation).** The plan called it
  "unaffected," but A5.3's dev-actor↔account linking + the funding/`/me` reads of `actor.account`
  mean a bare `db.get` would async-lazy-load a *linked* dev actor (`MissingGreenlet`). Switched to
  `select(...).options(joinedload(Actor.account))`.
- **Phase 7 still owes `/accounts` wiring coverage.** `test_wiring.WRITE_PATHS` is a hardcoded list,
  so the new bootstrap route passes silently uncovered until A7.6 adds it (+ the no-acting-actor
  carve-out, like `/actors`).
- **The one-`human`-per-account index is model-declared now (Phase 6, deviation).** The plan kept it
  migration-only, but the test harness builds its schema via `Base.metadata.create_all`, not Alembic
  — so a migration-only index would be **absent in tests** and A7.5 would pass vacuously. It now
  lives in `Actor.__table_args__` (mirrored 1:1 by `0006`), so `create_all` and Alembic build the
  same constraint. Phase 7's "reject a second human" test is therefore actually enforceable.
- **Migration round-trip is a Phase 9 step (Phase 6).** `0006` is lint- and metadata-verified, but
  the `upgrade→downgrade` proof needs a throwaway Postgres + explicit greenlight (repo policy). The
  backfills move 0 rows on today's empty DB, so the round-trip must run regardless of row count to
  exercise the SQL at all.
- **Versioned `0.7.0` — opening *identity* slice (Phase 9).** Per the proposal's locked
  recommendation, this lands as the opening slice of `0.7.0` (Agent-Ready Execution Surface), not a
  `0.6.11` — it does **not** include agent execution, only the principal/provenance split that agent
  ownership + real money force. Changelog entry written accordingly.
- **Executing docs deliberately NOT moved to completions yet (Phase 9 / A9.5).** The proposal +
  implementation plan stay in `docs/executing/` until the **greenlit live cutover** — the
  executing→completions move is the repo's "shipped" signal, and the cutover (A9.2) is still pending.
  Moving them now would misreport an un-cut-over release. The per-phase notes here are the work
  record in the meantime.
- **Phase 9 round-trip + live cutover are the only steps gated on a human greenlight.** Everything
  else (code, schema, tests, frontend, changelog) is complete and green offline.
