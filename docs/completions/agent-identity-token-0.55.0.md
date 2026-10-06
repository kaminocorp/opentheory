# 0.55.0 — Agent session token

**Goal.** Land slice C (agent token) of the approved
agent-actor identity design: OWNER-only mint / rotate / revoke,
the resolver, and the `authorize()` session-token swap. Stay
dark: no Fly, no `AGENT_LOOP_ENABLED`, no Crew UI, no debit
`actor_id`. No live Supabase apply (no migration — 0022 already
has `agent_session_tokens`). Sits on shipped `0.54.0`
(`7a1fa0c`, #50).

**Shape.** Service + route + resolver behaviour on the existing
0022 schema. No new table, no new column, no Alembic revision.

## What shipped

- OWNER-only `POST …/agents/{actor_id}/tokens` (mint),
  `…/tokens/{jti}/rotate`, `…/tokens/{jti}/revoke`.
  `ensure_can_manage(require_owner=True)`. ADMIN / agent /
  outsider are `403`. Inactive roster is `403`.
- Default TTL 30 days. Optional `ttl_seconds` shorter than
  `OPENTHEORY_AGENT_SESSION_MAX_TTL_SECONDS` (default
  `2592000`). Longer is `422`. No self-renew.
- Compact JWT returned **once**. SHA-256 stored on
  `token_hash`. Claims: `iss=opentheory`, `aud=harness`,
  `typ=agent_session`, `sub` / `proj` / `jti` / `mby` / `mba`,
  `iat` / `exp`. Signed with `AGENT_SESSION_JWT_SECRET`
  (settings; never `fly.toml [env]`).
- Missing secret fails closed: mint/rotate `503`; a
  `typ=agent_session` bearer is `401` and never falls through
  to the Supabase verifier.
- Resolver (`deps.py` + `harness/auth.py`): verify signature,
  typ, claims, hash lookup, `expires_at`, `revoked_at`, ACTIVE
  roster, stamp `last_used_at`. Returns the **agent** Actor.
  `OPENTHEORY_AGENT_JWT_FILE` aliases the existing file path.
- MCP writes with an agent token: `author_id` = agent,
  `sponsored_by_actor_id` = minting human (`create_checkpoint`
  trusted arg; never a client field). Human writes stay
  unsponsored. No second Contribution for the sponsor.
- `authorize()` accepts the agent session token and refuses
  when `proj` ≠ `HarnessSession.project_id`. Human JWT /
  flagged `OPENTHEORY_DEV_ACTOR_ID` (including a rostered
  agent) still pass via type-aware `ensure_is_member` so the
  0.52.0 pins and local harness stay. `record_spend` does not
  re-check (mid-turn debit-when-tokens-moved).
- `GET /me` refuses an agent session (`401`) — it stays the
  human Account + primary human Actor.

## What did not change

- `record_compute_debit(actor_id=)` / hold-release amount /
  `harness_session_turn` prefix / `hold_id` (slice D).
- Crew UI mint reveal / blame `sponsor: BlameActor` (slice E).
- Per-agent cap enforcement (slice F).
- `agent_definitions` (slice G).
- FastAPI does not import `app.harness`. `fly.toml [env]` has
  no secrets. Nothing enabled on Fly. Five tabs.
- No migration. 0022 is still not applied to live Supabase.

## Tests

- OWNER mint: claims, 30-day default, hash at rest, once.
- Shorter TTL; over-max `422`; missing secret `503`.
- ADMIN / outsider / agent / inactive roster cannot mint.
- Rotate revokes old; old compact JWT fails resolve and
  `authorize()`.
- Revoke → next resolve `401`.
- Resolver never returns a human; wrong key / expired / hash
  mismatch / missing secret → `401`; `last_used_at` stamped.
- Agent-token checkpoint: author = agent, sponsor = owner,
  Contribution.actor_id = agent. Human checkpoint has no
  sponsor.
- Authorize on matching project; token for A on B refuses.
- `GET /me` + fund/validate with agent token `401`/`403`.
- Flagged rostered-agent `DEV_ACTOR_ID` still authorizes.
- `OPENTHEORY_AGENT_JWT_FILE` resolves.

## Verification

- `ruff check .` clean.
- With `TEST_DATABASE_URL`: **1173 passed, 4 skipped**. +17 vs
  `0.54.0` (1156) — mint/rotate/revoke, resolver, MCP sponsor,
  authorize swap, `/me` + fund/validate refuse. Lean / Mathlib
  stay off.
- Frontend untouched.

## Unverified

- Live MCP child speaking as an agent on Fly (not enabled).
- Per-agent cap enforcement (slice F).
- Crew roster bay (slice E).
- Debit `actor_id` on `record_spend` (slice D).
