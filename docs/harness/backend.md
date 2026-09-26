# External harness — backend skeleton

> **Status — `0.40.0` Milestone 0.** Package exists. FastAPI does not
> import it. Fly does not run it.

## Where it lives

```
backend/app/harness/
  composition.py          fail-closed inventory + VERSION pin
  opentheory.cordis.yml   Cordis patch (strip coding tools, insert OT MCP)
  fixture_mcp.py          stdio MCP, stub tools, no ledger
  probe.py                composition + fixture; live skip / refuse
```

Tests: `backend/tests/harness/`. No Postgres. No OpenRouter. No `dsh`.

The package is **not** mounted on `api/router.py` and is **not** imported
from `app.main`. Booting the API does not load Cordis and does not need
the SDK.

## What M0 will and will not do

| Will | Will not |
| --- | --- |
| Verify the authored patch against `DISABLED` / inserts / persona / MCP name | Apply the patch inside FastAPI |
| Serve a fixture MCP over stdio for later `dsh` wiring | Call `run_instrument` or `create_checkpoint` |
| Skip a live probe without a key or runtime | Enable `AGENT_LOOP_ENABLED` |
| Pin `0.1.5rc1` in code and docs | Install that pin in default CI |

## Commands

```bash
cd backend
uv run python -m app.harness              # composition + fixture; live skipped
uv run pytest tests/harness -q            # default CI shape
uv run python -m app.harness.fixture_mcp  # stdio MCP (used by Cordis later)
```

## Later slices

`0.41.0` adds a *live* MCP server that is still a thin client of the
existing routes/services. `0.42.0` adds a gateway module analogous to
OpenWorld's `gateway.py` — provider allowlist, no fallbacks, no data
collection — without flipping the built-in planner.

Do not put settlement, validation, or funding on this package.
