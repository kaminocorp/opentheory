# External harness — prior art

> A short citation, not a copy. OpenWorld and OpenAir are architectural
> references. OpenTheory writes its own research-contributor persona and
> its own MCP inventory.

## What we took

From **Mission Systems OpenWorld** (private `missiongroupsystems/openworld`,
`apps/api/src/openworld_api/assistant/harness/`):

- Fail-closed Cordis composition: pin the SDK/runtime, strip
  shell / sandbox / pty / persistent-bash, assert the exact plugin
  inventory at boot.
- OpenRouter behind a gateway: provider allowlist, `allow_fallbacks: false`,
  `require_parameters: true`, `data_collection: deny` (built in `0.42.0`).
- A thin MCP plugin as the only domain door, plus a fixture MCP so
  Milestone 0 can probe without the product database.
- Runtime pin **`0.1.5rc1`**.

From **OpenAir**: the same idea that an external coding harness is not
the product — the product is the domain door and the ledger.

## What we must not copy

- Hospitality persona and venue voice
- SQL tools (`describe_schema`, `query`, `render_figure`)
- Reader DSN + RLS as the auth story (OT is JWT Actor + membership)
- Any private prompt text, tool schemas, or hospitality copy

## Mapping

| OpenWorld | OpenTheory |
| --- | --- |
| MCP `query` / `describe_schema` / `render_figure` | MCP `run_instrument`, `create_checkpoint`, list/context + budget |
| Reader DSN + RLS | JWT Actor + `ensure_is_member`; ledger chokepoints |
| Cordis strip coding tools | Same disabled set; OT names on inserts |
| OpenRouter gateway | Same pattern (`0.42.0`); session owner (`0.43.0`); fail-closed campaign child (`0.44.0`); daily token cap (`0.46.0`); daily-cap reservation (`0.47.0`); stale-hold release (`0.48.0`); built-in `AGENT_LOOP_ENABLED` stays dark |
| Append-only `assistant.message` | Append-only checkpoint ledger |
| Daily turn/request caps | `0.46.0` daily token cap (20_000 / UTC day, ledger-backed); `0.47.0` remaining-room hold so overlapping authorizes cannot both debit past it; `0.48.0` stale-hold release so a crash leftover does not pin the UTC day |

Launchpad Bubbles is **not** the reference for this line.
