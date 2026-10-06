# 0.51.1 — Harness actor-attribution audit

**Goal.** Investigate whether every external-harness ledger write is
attributed to the correct Actor (the JWT-resolved member, not the
human Account that holds the JWT, and not a non-member), and whether
the MCP door / `supervise_turn` refuse a non-member before
`run_instrument` / `create_checkpoint` and before a debit. If a real
gap: ship `0.52.0`. If none: record the audit as `0.51.1`. Do not
light `AGENT_LOOP_ENABLED`. Do not enable the gateway or MCP child
on Fly. **No schema, no migration.** Sits on shipped `0.51.0`
(`fd9316d`, #45).

**Shape.** Docs-only plus Postgres regressions for guarantees that
were untested. No production code change.

## Finding

No production-code gap. Full write-path table:
`docs/harness/attribution.md`.

- **MCP writes** attribute to the JWT-resolved **Actor** (bearer →
  Account → primary `human` Actor, or flagged
  `OPENTHEORY_DEV_ACTOR_ID`). `ensure_is_member` runs first.
  `Checkpoint.author_id` / `Contribution.actor_id` are that Actor.
  The Account is not the contributor. The built-in per-project
  `Research crew` agent is account-less, is not a `ProjectMember`
  (Decision #3), and is `403` on this door.
- **`create_checkpoint`** remains the only Checkpoint writer.
- **`ComputeDebit`** has no `actor_id`. Spend is project-scoped.
  `FundingAllocation` (funder) is unchanged. Debit only when
  `tokens_used > 0`. Hold rows unchanged.
- **Debit membership** is the MCP door, not `authorize()`. The
  gateway / campaign child is project-bound
  (`OPENTHEORY_PROJECT_ID`); the member JWT lives on the MCP child.
  An outsider `actor_env` on `supervise_turn` can still record
  spend and still cannot mint.

Remapping writes onto `Research crew` would `403` at membership,
bypass the gate, or need a schema change. Adding
`ComputeDebit.actor_id` is a schema change this slice refuses.

## What shipped

- `docs/harness/attribution.md` — the audit.
- Blueprint / harness copy no longer claims the session *is*
  `Actor(type=agent)`.
- Changelog, this completion note, roadmap banner updated in place
  (on shipped `0.51.0`, `fd9316d`, #45).
- Postgres regressions: account-less project agent `403` on both
  write stems; member write sets author + contribution to the human
  Actor and does not mint `Research crew`; debit leaves
  `FundingAllocation` unchanged and `ComputeDebit` has no
  `actor_id`; outsider `actor_env` on `supervise_turn` debits and
  does not mint.

## What did not change

- Production harness / service / model code.
- Append-only guards. Account ≠ Actor. Funder ≠ contributor ≠
  validator.
- `0.47`–`0.51` serialization / TTL / deadline / clamp / hold
  occupancy. Debit only when `tokens_used > 0`. Hold/release
  amount `0`.
- Five tabs. `AGENT_LOOP_ENABLED` default `false`. Fly `[env]`
  still has no secrets. FastAPI still does not import
  `app.harness`.
- No Alembic revision.

## Tests

- DB-gated: account-less project agent cannot write; member
  `run_instrument` / `create_checkpoint` author and contribution
  are the JWT / dev human Actor; no `Research crew` row on a
  member write; gateway debit does not touch
  `FundingAllocation`; `supervise_turn` outsider `actor_env`
  records spend and mints nothing.
- Existing member / non-member / debit-only-when-tokens-moved
  suites stay.

## Verification

- `ruff check .` clean.
- Default pytest (no `TEST_DATABASE_URL`): **854 passed, 275 skipped**.
  +2 skipped vs shipped `0.51.0` (273) — the new ledger regressions.
- With `TEST_DATABASE_URL`: **1125 passed, 4 skipped**. Harness
  suite **136 passed**. Lean / Mathlib stay off.
- Frontend untouched: typecheck / lint / build clean; **64 tests**.

## Unverified

- Live OpenRouter / `dsh` round-trip (still dark).
- Fly enablement of the harness child.
