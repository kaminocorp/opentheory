# External harness — compatibility

> **Status — `0.40.0` Milestone 0.** Pin is documented. Live probe is
> **pending**. Default CI does not install the SDK and does not need
> `OPENROUTER_API_KEY`.

## Pin

| Piece | Pin | Notes |
| --- | --- | --- |
| DeepSeek Harness SDK / runtime | **`0.1.5rc1`** | Same pin OpenWorld used for its fail-closed Cordis tree |
| Cordis profile | `sdk-minimal` + `opentheory.cordis.yml` | Patch is verified by `app.harness.composition` |
| MCP client plugin | `@deepseek-ai/dsh-mcp-client` | `serverName: opentheory`, stdio, no reconnect |
| LLM provider plugin | `@deepseek-ai/dsh-llm-pi-ai` | OpenRouter via `OPENTHEORY_GATEWAY_*` |
| Default CI extra | none | `[harness]` is optional |

`VERSION` in `backend/app/harness/composition.py` is the source of truth
for the pin. Changing it is a release decision, not a drive-by.

## Optional extra

```toml
[project.optional-dependencies]
harness = ["deepseek-harness-sdk==0.1.5rc1"]
```

Install only when you intend to boot the runtime:

```bash
cd backend && uv sync --extra harness
```

If the wheel is missing for CI Linux, leave the extra uninstalled. Composition
tests and the fixture MCP stay green. Do not add the SDK to the default
dependency set just to go green.

## Environment (not required for 0.40.0 CI)

| Variable | Role | Required in default CI? |
| --- | --- | --- |
| `OPENTHEORY_HARNESS_LIVE` | Opt-in live probe (`1` / `true`) | no — unset skips |
| `OPENROUTER_API_KEY` | Built-in planner + fallback live-probe token | no |
| `OPENTHEORY_GATEWAY_TOKEN` | Gateway token for the harness provider | no |
| `OPENTHEORY_GATEWAY_URL` | Gateway base URL | no |
| `OPENTHEORY_MODEL` | Model id (OpenRouter alias) | no |
| `OPENTHEORY_MCP_PYTHON` / `OPENTHEORY_MCP_SCRIPT` | Fixture / live MCP stdio command | no |
| `OPENTHEORY_PROBE_NONCE` / `OPENTHEORY_PROBE_LOG` | Probe echo + optional log | no |
| `AGENT_LOOP_ENABLED` | Built-in in-process planner | **must stay false** |

Do not put gateway tokens in `fly.toml [env]`. Do not flip
`AGENT_LOOP_ENABLED` as a substitute for the external path.

## Live probe

**Pending.** `0.40.0` implements skip reasons only:

- flag unset → skip
- no `OPENROUTER_API_KEY` / `OPENTHEORY_GATEWAY_TOKEN` → skip
- no `dsh` binary and no `deepseek-harness-sdk` import → skip
- flag + token + runtime present → **refuse** (`not implemented in 0.40.0`)

A green default pytest is not a live OpenRouter proof. Record a real
round-trip only after `0.41` / `0.42` bind MCP + gateway.

## Open questions (do not pretend they are closed)

1. **Wheel availability on CI Linux.** `0.1.5rc1` may not publish a usable
   manylinux wheel. That is why the extra is optional.
2. **`dsh` binary distribution.** PATH vs. SDK import — probe accepts either.
3. **JWT injection into MCP stdio.** How the live plugin receives a
   member-scoped bearer without leaking it into session logs (`0.41.0`).
4. **Gateway token vs. raw OpenRouter key.** OpenWorld used a gateway in
   front of OpenRouter (`allow_fallbacks: false`, `require_parameters: true`,
   `data_collection: deny`). OT should do the same in `0.42.0`; M0 only
   names the env vars.
5. **Session persistence.** sdk-minimal keeps JSONL sessions. Whether OT
   wants that on disk, or only the ledger, is a later ops question. The
   ledger remains the source of truth either way.

## What this does *not* claim

- The SDK is installed in CI or on Fly.
- A live model call succeeded.
- The built-in agent loop is on.
- `run_instrument` / `create_checkpoint` were reached from a harness turn.
