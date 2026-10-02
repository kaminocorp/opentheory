# External harness — backend skeleton

> **Status — `0.44.0` fail-closed metered composition.** Package
> exists. FastAPI does not import it. Fly does not run it.

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
  session.py              HarnessSession — turn cap, exhaust, debit
  campaign.py             odd-perfect reference campaign (instrument-only)
  turns.py                library helper; composes HarnessSession
  probe.py                composition + fixture; opt-in live OpenRouter
```

Tests: `backend/tests/harness/`. Default suite: no OpenRouter, no `dsh`.
Ledger tests in `test_live_mcp_ledger.py` / `test_turns_ledger.py` /
`test_session_ledger.py` skip without `TEST_DATABASE_URL` (CI Postgres
runs them).

The package is **not** mounted on `api/router.py` and is **not** imported
from `app.main`. Booting the API does not load Cordis, does not start the
gateway, and does not need the SDK.

## What 0.44.0 will and will not do

| Will | Will not |
| --- | --- |
| Fail closed if the composition launches the bare unmetered proxy | Treat an unmetered probe as the campaign composition |
| Pass `OPENTHEORY_PROJECT_ID` as an env name (like the JWT file) | Put a project UUID or secret in `opentheory.cordis.yml` |
| Point `llm-pi-ai` at `python -m app.harness.campaign` | Start `python -m app.harness.gateway` without an explicit probe flag |
| Keep `HarnessSession` metering / turn cap / exhaust | Add a campaign table or a second Checkpoint writer |
| Skip the live probe without a key | Require `dsh` / the `[harness]` extra in default CI |
| Keep FastAPI from importing the package | Enable the gateway / MCP child on Fly or light `AGENT_LOOP_ENABLED` |

## Commands

```bash
cd backend
uv run python -m app.harness              # composition + fixture; live OpenRouter skipped
uv run python -m app.harness.live_mcp     # live stdio MCP (needs DB + credentials)
uv run python -m app.harness.fixture_mcp  # stub stdio MCP (M0 probes)
uv run python -m app.harness.campaign     # session-owned child; refuses when unbound
uv run python -m app.harness.gateway      # unmetered probe only with OPENTHEORY_HARNESS_UNMETERED_PROBE=1
uv run pytest tests/harness -q            # default CI shape
```

Point Cordis `OPENTHEORY_MCP_SCRIPT` at the live module when you want
the door; leave it on the fixture for composition probes. Point
`OPENTHEORY_GATEWAY_URL` at the campaign child. Supply
`OPENTHEORY_PROJECT_ID` and `OPENTHEORY_GATEWAY_PYTHON` as names in
the environment — never as literals in the Cordis file. The child
holds `OPENTHEORY_GATEWAY_TOKEN`; the gateway holds
`OPENROUTER_API_KEY`. Neither belongs in `fly.toml [env]`.

## Later slices

An ops dashboard and daily turn/request caps are later. This slice
closes the unmetered-composition hole: the path a campaign actually
runs cannot start without a session owner.

Do not put settlement, validation, or funding on this package.
