# 0.41.0 — Live OpenTheory MCP domain door

**Goal.** Bind the Milestone-0 MCP stems to the live ledger. A member-scoped
JWT Actor (or the flagged local `X-Dev-Actor-Id` equivalent) plus
`ensure_is_member` reaches the existing `run_instrument` /
`create_checkpoint` chokepoints. Claim / thread / budget reads reuse the
API's read models. Keep the fixture MCP for M0 probe tests. Do not light
`AGENT_LOOP_ENABLED`. Prefer no schema / no migration.

**Shape.** New `backend/app/harness/live_mcp.py` + `auth.py`. FastAPI still
does not import the package. The fixture in `fixture_mcp.py` stays stubs
(`minted: false`). **No schema, no migration.** Sits on shipped `0.40.0`
(`901b3de`, #33).

## What shipped

- **Live MCP server** — stdio JSON-RPC, same stems as M0. Domain tools call
  existing services. Unknown tools are rejected. Exceptions mint nothing.
- **Auth injection** — preferred `OPENTHEORY_ACTOR_JWT_FILE` (path only in
  Cordis env). Raw `OPENTHEORY_ACTOR_JWT` is accepted but never logged.
  `OPENTHEORY_DEV_ACTOR_ID` is the existing local/test escape hatch and is
  `401` when `auth_dev_header_enabled` is off. Probe logs redact secret keys.
- **Writes** — `run_instrument` → `services.tool_runs.run_instrument` →
  `create_checkpoint`. Explicit notes go through
  `services.checkpoints.create_checkpoint`. Membership first. A funded
  project with `available <= 0` refuses (`project budget exhausted`) and
  mints nothing. Unfunded projects are not treated as exhausted.
- **Reads** — `list_claims` / `get_thread_context` / `get_budget` compose
  existing claim, thread, grounding, and `project_budget` reads. Membership
  gated. Mints nothing.
- **Fixture kept** — M0 probe tests still speak to stub tools.

## What did not change

- `create_checkpoint` remains the only Checkpoint writer.
- Append-only guards, membership, instruments, campaigns, orchestrator.
- `AGENT_LOOP_ENABLED` default `false`. Fly `[env]` untouched.
- Funder ≠ contributor ≠ validator. Account ≠ Actor.
- No Alembic revision. No frontend. No OpenRouter gateway.

## Honest caveats

- Standalone instrument runs still do not debit `ComputeDebit` — same as the
  human toolbench. Gateway token metering is `0.42.0`.
- A green default pytest is not a live DeepSeek / OpenRouter round-trip.
- The SDK extra may still not resolve on every Linux.
- Cordis session JSONL may record the JWT *file path*. The bearer itself
  must stay out of that file.

## Tests

- Live inventory matches `TOOL_STEMS`; FastAPI boot path does not import
  `app.harness`; unknown `query` raises; stdio `tools/list` is exact.
- JWT file wins; secret keys redact from probe payloads.
- DB-backed: member `calc.eval` lands a `tool_run` checkpoint; non-member
  and bad JWT mint nothing; instrument failure mints nothing; reads are
  membership-gated; exhausted funded pot refuses.

## Verification

- `ruff check .` clean.
- Default pytest (no `TEST_DATABASE_URL`): **756 passed, 237 skipped**.
  +12 vs shipped `0.40.0` (744) — live auth + inventory. +10 skipped
  (ledger suite).
- With `TEST_DATABASE_URL`: **989 passed, 4 skipped** — +22 vs `0.40.0`
  (967). Lean / Mathlib stay off. Frontend untouched.

## Unverified

- Live OpenRouter / `dsh` round-trip (still `0.42.0`).
- Fly enablement of the harness child.
