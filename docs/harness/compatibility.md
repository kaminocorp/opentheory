# External harness — compatibility

> **Status — `0.41.0` live MCP door.** Pin is unchanged. Live *OpenRouter*
> probe is still **pending** (`0.42.0`). Default CI does not install the
> SDK and does not need `OPENROUTER_API_KEY`.

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
tests, the fixture MCP, and the live MCP unit suite stay green. Do not add
the SDK to the default dependency set just to go green.

## Environment

| Variable | Role | Required in default CI? |
| --- | --- | --- |
| `OPENTHEORY_HARNESS_LIVE` | Opt-in live OpenRouter probe (`1` / `true`) | no — unset skips |
| `OPENROUTER_API_KEY` | Built-in planner + fallback live-probe token | no |
| `OPENTHEORY_GATEWAY_TOKEN` | Gateway token for the harness provider | no |
| `OPENTHEORY_GATEWAY_URL` | Gateway base URL | no |
| `OPENTHEORY_MODEL` | Model id (OpenRouter alias) | no |
| `OPENTHEORY_MCP_PYTHON` / `OPENTHEORY_MCP_SCRIPT` | Fixture or live MCP stdio command | no |
| `OPENTHEORY_PROBE_NONCE` / `OPENTHEORY_PROBE_LOG` | Probe echo + optional log | no |
| `OPENTHEORY_ACTOR_JWT_FILE` | Path to a `0600` file holding the member JWT | no — live writes need one of the three |
| `OPENTHEORY_ACTOR_JWT` | Bearer in-process (never put in Cordis `env`) | no |
| `OPENTHEORY_DEV_ACTOR_ID` | Local/test actor id (flag-gated) | no |
| `AGENT_LOOP_ENABLED` | Built-in in-process planner | **must stay false** |

Do not put gateway tokens or raw JWTs in `fly.toml [env]`. Do not flip
`AGENT_LOOP_ENABLED` as a substitute for the external path.

## JWT injection (closed in `0.41.0`)

The live plugin is a stdio child. A bearer on a tool argument, or in the
authored Cordis `env: OPENTHEORY_ACTOR_JWT: !!js process.env.…` block,
would leak into session / probe logs.

**Chosen pattern:** pass only `OPENTHEORY_ACTOR_JWT_FILE` through Cordis.
The parent writes the token to a file the child reads. Probe logs run
every JSON-RPC message through `app.harness.auth.redact`, which replaces
`OPENTHEORY_ACTOR_JWT`, `OPENTHEORY_ACTOR_JWT_FILE`,
`OPENTHEORY_DEV_ACTOR_ID`, `authorization`, `bearer`, `token`, and `jwt`
values with `***`.

`OPENTHEORY_DEV_ACTOR_ID` is the same local/test path as
`X-Dev-Actor-Id`. It is `401` when `auth_dev_header_enabled` is off.

## Live OpenRouter probe

**Pending (`0.42.0`).** `0.40.0` skip reasons still hold:

- flag unset → skip
- no `OPENROUTER_API_KEY` / `OPENTHEORY_GATEWAY_TOKEN` → skip
- no `dsh` binary and no `deepseek-harness-sdk` import → skip
- flag + token + runtime present → **refuse** (`not implemented in 0.40.0`)

A green default pytest is not a live OpenRouter proof. The live *MCP*
door (this slice) is covered by `tests/harness/test_live_mcp*.py` and
does not need a model key.

## Open questions (do not pretend they are closed)

1. **Wheel availability on CI Linux.** `0.1.5rc1` may not publish a usable
   manylinux wheel. That is why the extra is optional.
2. **`dsh` binary distribution.** PATH vs. SDK import — probe accepts either.
3. ~~**JWT injection into MCP stdio.**~~ ✅ closed in `0.41.0` (file path
   + redaction; see above).
4. **Gateway token vs. raw OpenRouter key.** OpenWorld used a gateway in
   front of OpenRouter (`allow_fallbacks: false`, `require_parameters: true`,
   `data_collection: deny`). OT should do the same in `0.42.0`.
5. **Session persistence.** sdk-minimal keeps JSONL sessions. Whether OT
   wants that on disk, or only the ledger, is a later ops question. The
   ledger remains the source of truth either way.

## What this does *not* claim

- The SDK is installed in CI or on Fly.
- A live model call succeeded.
- The built-in agent loop is on.
- A DeepSeek harness *turn* reached `run_instrument` (the live MCP
  process did, under pytest / stdio).
