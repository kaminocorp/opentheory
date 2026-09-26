# External harness — backend skeleton

> **Status — `0.42.0` gateway + turn supervision.** Package exists.
> FastAPI does not import it. Fly does not run it.

## Where it lives

```
backend/app/harness/
  composition.py          fail-closed inventory + VERSION pin
  opentheory.cordis.yml   Cordis patch (strip coding tools, insert OT MCP)
  fixture_mcp.py          stdio MCP, stub tools, no ledger (M0 probes)
  live_mcp.py             live door: JWT + membership + chokepoints
  auth.py                 JWT-file / JWT-env / flagged dev-actor; redaction
  protocol.py             shared stdio JSON-RPC framing
  gateway.py              fail-closed OpenRouter client + HTTP proxy
  turns.py                bounded turns + ComputeDebit
  probe.py                composition + fixture; opt-in live OpenRouter
```

Tests: `backend/tests/harness/`. Default suite: no OpenRouter, no `dsh`.
Ledger tests in `test_live_mcp_ledger.py` / `test_turns_ledger.py` skip
without `TEST_DATABASE_URL` (CI Postgres runs them).

The package is **not** mounted on `api/router.py` and is **not** imported
from `app.main`. Booting the API does not load Cordis, does not start the
gateway, and does not need the SDK.

## What 0.42.0 will and will not do

| Will | Will not |
| --- | --- |
| Talk to OpenRouter only, with a provider allowlist | Call `api.deepseek.com` |
| Force `allow_fallbacks: false`, `require_parameters: true`, `data_collection: deny` | Honor a client `provider` block that re-opens fallbacks |
| Bound turns; refuse on composition drift | Light `AGENT_LOOP_ENABLED` |
| Debit `ComputeDebit` for LLM tokens that moved | Debit a standalone instrument run (same as humans) |
| Dispatch optional MCP after a successful completion | Mint a Checkpoint itself |
| Skip the live probe without a key | Require `dsh` / the `[harness]` extra in default CI |

## Commands

```bash
cd backend
uv run python -m app.harness              # composition + fixture; live OpenRouter skipped
uv run python -m app.harness.live_mcp     # live stdio MCP (needs DB + credentials)
uv run python -m app.harness.fixture_mcp  # stub stdio MCP (M0 probes)
uv run python -m app.harness.gateway      # fail-closed OpenAI-compatible proxy
uv run pytest tests/harness -q            # default CI shape
```

Point Cordis `OPENTHEORY_MCP_SCRIPT` at the live module when you want
the door; leave it on the fixture for composition probes. Point
`OPENTHEORY_GATEWAY_URL` at the gateway child. The child holds
`OPENTHEORY_GATEWAY_TOKEN`; the gateway holds `OPENROUTER_API_KEY`.
Neither belongs in `fly.toml [env]`.

## Later slices

A reference campaign and an ops dashboard are later. Daily turn/request
caps are later. This slice owns token `ComputeDebit` metering for
supervised turns.

Do not put settlement, validation, or funding on this package.
