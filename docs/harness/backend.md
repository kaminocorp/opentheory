# External harness — backend skeleton

> **Status — `0.43.0` session owner + reference campaign.** Package
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

## What 0.43.0 will and will not do

| Will | Will not |
| --- | --- |
| Bind a `HarnessSession` to a human-created project | Reuse `ResearchCampaign` or light `AGENT_LOOP_ENABLED` |
| Apply turn cap + funded-pot exhaust on `create_gateway_app` | Treat unfunded as exhausted |
| Debit `ComputeDebit` when `tokens_used > 0` | Debit a standalone instrument run (same as humans) |
| Ship an odd-perfect reference campaign (instrument-only) | Auto-validate / auto-fund / auto-merge |
| Drop extra-body `models` / `route` / `transforms` | Honor a client block that re-opens routing |
| Skip the live probe without a key | Require `dsh` / the `[harness]` extra in default CI |
| Keep FastAPI from importing the package | Enable the gateway child on Fly |

## Commands

```bash
cd backend
uv run python -m app.harness              # composition + fixture; live OpenRouter skipped
uv run python -m app.harness.live_mcp     # live stdio MCP (needs DB + credentials)
uv run python -m app.harness.fixture_mcp  # stub stdio MCP (M0 probes)
uv run python -m app.harness.gateway      # fail-closed proxy (metered if OPENTHEORY_PROJECT_ID)
uv run python -m app.harness.campaign     # reference spec; metered child only when project-bound
uv run pytest tests/harness -q            # default CI shape
```

Point Cordis `OPENTHEORY_MCP_SCRIPT` at the live module when you want
the door; leave it on the fixture for composition probes. Point
`OPENTHEORY_GATEWAY_URL` at the gateway child. The child holds
`OPENTHEORY_GATEWAY_TOKEN`; the gateway holds `OPENROUTER_API_KEY`.
Neither belongs in `fly.toml [env]`.

## Later slices

An ops dashboard and daily turn/request caps are later. This slice
owns the session: token `ComputeDebit` metering for the gateway path
a campaign actually runs.

Do not put settlement, validation, or funding on this package.
