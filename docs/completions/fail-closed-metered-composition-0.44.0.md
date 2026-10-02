# 0.44.0 — Fail-closed metered harness composition

**Goal.** Close the hole `0.43.0` left open: metering sat on
`create_gateway_app` only when a `HarnessSession` was bound, but the
composition `dsh` would actually boot still launched the bare
`python -m app.harness.gateway` child. Without a project id that child
is an unmetered probe proxy. A later enablement could spend OpenRouter
with no ceiling and still look like "the harness." Do not light
`AGENT_LOOP_ENABLED`. Prefer no schema / no migration. Default CI stays
green without `OPENROUTER_API_KEY` or a `dsh` binary.

**Shape.** Tighten `composition.verify` and the authored
`opentheory.cordis.yml`. Point `llm-pi-ai` at
`python -m app.harness.campaign` (refuses when unbound) and pass
`OPENTHEORY_PROJECT_ID` as an operator-supplied env name — the same
pattern as `OPENTHEORY_ACTOR_JWT_FILE`. An explicit unmetered probe may
remain behind `OPENTHEORY_HARNESS_UNMETERED_PROBE`; `verify()` treats
that flag as not the campaign composition. **No schema, no migration.**
Sits on shipped `0.43.0` (`51368da`, #36).

## What shipped

- **Campaign child is the composition child.** `llm-pi-ai` command /
  args launch `app.harness.campaign`. `verify()` rejects
  `app.harness.gateway` there.
- **Project binding is an env name.** Both the `llm-pi-ai` and
  `opentheory-mcp` env blocks pass `OPENTHEORY_PROJECT_ID: !!js
  process.env.OPENTHEORY_PROJECT_ID`. A missing key or a literal UUID
  is composition drift. JWT file stays path interpolation only; a
  bearer / OpenRouter key / gateway token in Cordis env is rejected.
- **Process refuse.** `python -m app.harness.campaign` exits unbound.
  `python -m app.harness.gateway` exits unbound unless
  `OPENTHEORY_HARNESS_UNMETERED_PROBE` is set. In-process tests may
  still construct an unbound `create_gateway_app`.
- **Unmetered probe is not the campaign.** The flag on the authored
  patch is `CompositionError`. The live OpenRouter probe
  (`OPENTHEORY_HARNESS_LIVE`) still uses `GatewayClient` directly and
  still skips without a key.

## What did not change

- `create_checkpoint` remains the only Checkpoint writer.
- Append-only guards, membership, instruments, built-in campaigns,
  orchestrator.
- `AGENT_LOOP_ENABLED` default `false`. Fly `[env]` still has no
  secrets. The gateway / MCP child is **not** enabled on Fly.
- Funder ≠ contributor ≠ validator. Account ≠ Actor.
- Unfunded ≠ exhausted. Debit only when `tokens_used > 0`.
- No Alembic revision. No frontend. Live MCP inventory unchanged.
- No campaign table. Turn index stays process-local.

## Honest caveats

- A green default pytest is not a live OpenRouter / `dsh` session.
- Turn index is process-local. A restarted child starts at turn 0.
  Counting existing `ComputeDebit` rows would conflate concurrent runs
  on the same project and would not record a debit-less refuse, so it
  is left documented rather than faked.
- `OPENTHEORY_HARNESS_UNMETERED_PROBE` still starts an unmetered HTTP
  child. That is a probe, and `verify()` will not accept it as the
  campaign composition.
- Daily caps / ops dashboard / Fly enablement are later.

## Tests

- On-disk patch points `llm-pi-ai` at `app.harness.campaign` and
  interpolates `OPENTHEORY_PROJECT_ID` / `OPENTHEORY_ACTOR_JWT_FILE`.
- Missing project binding, literal UUID, bare gateway module,
  unmetered-probe flag, and JWT bearer in Cordis env are rejected.
- Gateway / campaign process helpers refuse unbound; the probe flag
  allows the gateway process only.
- Existing session-owner / extra-body / FastAPI-ignores-harness /
  fly.toml-no-secrets tests stay.

## Verification

- `ruff check .` clean.
- Default pytest (no `TEST_DATABASE_URL`): **804 passed, 245 skipped**.
  +9 vs shipped `0.43.0` (795) — composition child, env-name binding,
  process refuse. Skip count unchanged (ledger suite).
- Ledger suite not run in this environment (`TEST_DATABASE_URL` unset).
  Session-owner debit / exhaust tests from `0.43.0` were not changed.
  Lean / Mathlib stay off. Frontend untouched.

## Unverified

- A live OpenRouter call with a real key in this environment.
- A full `dsh` session against the session-owned HTTP child.
- Fly enablement of the harness child.
