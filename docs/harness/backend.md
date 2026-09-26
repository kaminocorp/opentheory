# External harness — backend skeleton

> **Status — `0.41.0` live door.** Package exists. FastAPI does not
> import it. Fly does not run it.

## Where it lives

```
backend/app/harness/
  composition.py          fail-closed inventory + VERSION pin
  opentheory.cordis.yml   Cordis patch (strip coding tools, insert OT MCP)
  fixture_mcp.py          stdio MCP, stub tools, no ledger (M0 probes)
  live_mcp.py             live door: JWT + membership + chokepoints
  auth.py                 JWT-file / JWT-env / flagged dev-actor; redaction
  protocol.py             shared stdio JSON-RPC framing
  probe.py                composition + fixture; live OpenRouter skip / refuse
```

Tests: `backend/tests/harness/`. Default suite: no OpenRouter, no `dsh`.
Ledger tests in `test_live_mcp_ledger.py` skip without `TEST_DATABASE_URL`
(CI Postgres runs them).

The package is **not** mounted on `api/router.py` and is **not** imported
from `app.main`. Booting the API does not load Cordis and does not need
the SDK.

## What 0.41.0 will and will not do

| Will | Will not |
| --- | --- |
| Resolve a JWT Actor (or flagged dev-actor) and `ensure_is_member` | Apply the Cordis patch inside FastAPI |
| Call `run_instrument` / `create_checkpoint` | Mint a Checkpoint itself |
| Serve claim / thread / budget reads | Enable `AGENT_LOOP_ENABLED` |
| Keep the fixture MCP for M0 probes | Install the SDK pin in default CI |
| Refuse writes when a funded pot is exhausted | Debit `ComputeDebit` for a lone instrument run |

## Commands

```bash
cd backend
uv run python -m app.harness              # composition + fixture; live OpenRouter skipped
uv run python -m app.harness.live_mcp     # live stdio MCP (needs DB + credentials)
uv run python -m app.harness.fixture_mcp  # stub stdio MCP (M0 probes)
uv run pytest tests/harness -q            # default CI shape
```

Point Cordis `OPENTHEORY_MCP_SCRIPT` at the live module when you want
the door; leave it on the fixture for composition probes.

## Later slices

`0.42.0` adds a gateway module analogous to OpenWorld's `gateway.py` —
provider allowlist, no fallbacks, no data collection — without flipping
the built-in planner. That slice owns token `ComputeDebit` metering.

Do not put settlement, validation, or funding on this package.
