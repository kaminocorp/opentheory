# 0.42.0 — OpenRouter gateway + turn supervision

**Goal.** Wire the external DeepSeek Harness path to OpenRouter through
a fail-closed gateway and bounded turn supervision, with `ComputeDebit`
for token spend. Do not light `AGENT_LOOP_ENABLED`. Prefer no schema /
no migration. Default CI stays green without `OPENROUTER_API_KEY` or a
`dsh` binary.

**Shape.** New `backend/app/harness/gateway.py` + `turns.py`. Probe
live path implemented behind `OPENTHEORY_HARNESS_LIVE`. FastAPI still
does not import the package. **No schema, no migration.** Sits on
shipped `0.41.0` (`06cfeab`, #34).

## What shipped

- **Fail-closed gateway** — OpenRouter only. Provider allowlist
  (default `DeepSeek`). Every body overwrites `provider` to
  `allow_fallbacks: false`, `require_parameters: true`,
  `data_collection: deny`. `api.deepseek.com` is refused. HTTP child
  authenticates with `OPENTHEORY_GATEWAY_TOKEN` and forwards with
  `OPENROUTER_API_KEY`.
- **Turn supervision** — composition re-verify, turn cap (default 4),
  funded-pot exhaust refuse *before* the LLM call. Optional live MCP
  dispatch after a successful completion. Exceptions mint nothing.
- **ComputeDebit** — `record_compute_debit` for tokens that moved
  (success or attempted). No `AgentRun` row. Notes
  `harness_gateway_turn`. A refused start writes nothing. Standalone
  instrument runs still do not debit.
- **Probe** — opt-in live OpenRouter completion. Skip without flag or
  key. Does not require `dsh`.

## What did not change

- `create_checkpoint` remains the only Checkpoint writer.
- Append-only guards, membership, instruments, campaigns, orchestrator.
- `AGENT_LOOP_ENABLED` default `false`. Fly `[env]` still has no secrets.
- Funder ≠ contributor ≠ validator. Account ≠ Actor.
- No Alembic revision. No frontend. Live MCP inventory unchanged.

## Honest caveats

- A green default pytest is not a live OpenRouter call (skipped without
  a key). The ledger suite proves debit + MCP landing against a mocked
  gateway.
- The HTTP gateway does not infer `project_id` from a bare dsh child.
  Metering happens when a turn is supervised with a project.
- The SDK extra may still not resolve on every Linux.
- Daily caps / ops dashboard / a reference campaign are later.

## Tests

- Fail-closed payload knobs; client `provider` overwrite; raw DeepSeek
  host refused; catalog / allowlist model rejects; missing key raises
  before any request; HTTP child requires the gateway token.
- `fly.toml [env]` contains no OpenRouter / gateway / JWT secrets and
  does not set `AGENT_LOOP_ENABLED`. FastAPI boot path still ignores
  `app.harness`.
- Composition drift and turn-cap refuse before the LLM call.
- Probe skips without flag / key; opt-in with a mock transport is a
  real fail-closed completion; missing `dsh` is not a skip.
- DB-backed: successful turn debits and lands `calc.eval` through the
  live door; attempted turn debits and mints nothing; exhausted funded
  pot refuses with no new debit and no checkpoint.

## Verification

- `ruff check .` clean.
- Default pytest (no `TEST_DATABASE_URL`): **779 passed, 240 skipped**.
  +23 vs shipped `0.41.0` (756) — gateway knobs, turn-cap / composition
  refuse, probe skip/opt-in. +3 skipped (ledger suite).
- With `TEST_DATABASE_URL`: **1015 passed, 4 skipped** — +26 vs `0.41.0`
  (989). Lean / Mathlib stay off. Frontend untouched.

## Unverified

- A live OpenRouter call with a real key in this environment.
- A full `dsh` session against the HTTP gateway child.
- Fly enablement of the harness child.
