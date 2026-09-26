# External harness — compatibility

> **Status — `0.42.0` OpenRouter gateway + turn supervision.** Pin is
> unchanged. Live OpenRouter probe is implemented behind
> `OPENTHEORY_HARNESS_LIVE`. Default CI does not install the SDK and
> does not need `OPENROUTER_API_KEY`.

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
tests, the fixture MCP, the live MCP unit suite, and the gateway / turn
suite stay green. Do not add the SDK to the default dependency set just
to go green.

## Environment

| Variable | Role | Required in default CI? |
| --- | --- | --- |
| `OPENTHEORY_HARNESS_LIVE` | Opt-in live OpenRouter probe (`1` / `true`) | no — unset skips |
| `OPENROUTER_API_KEY` | Upstream OpenRouter key (gateway + built-in planner) | no |
| `OPENTHEORY_GATEWAY_TOKEN` | Inbound token the harness child sends to the gateway | no |
| `OPENTHEORY_GATEWAY_URL` | Gateway base URL (`/v1/chat/completions`) | no |
| `OPENTHEORY_GATEWAY_PROVIDERS` | Comma-separated OpenRouter `provider.only` (default `DeepSeek`) | no |
| `OPENTHEORY_MODEL` | Model id (must be in the OT catalog + allowlist) | no |
| `OPENTHEORY_HARNESS_MAX_TURNS` | Supervised-turn cap (default 4) | no |
| `OPENTHEORY_MCP_PYTHON` / `OPENTHEORY_MCP_SCRIPT` | Fixture or live MCP stdio command | no |
| `OPENTHEORY_PROBE_NONCE` / `OPENTHEORY_PROBE_LOG` | Probe echo + optional log | no |
| `OPENTHEORY_ACTOR_JWT_FILE` | Path to a `0600` file holding the member JWT | no — live writes need one of the three |
| `OPENTHEORY_ACTOR_JWT` | Bearer in-process (never put in Cordis `env`) | no |
| `OPENTHEORY_DEV_ACTOR_ID` | Local/test actor id (flag-gated) | no |
| `AGENT_LOOP_ENABLED` | Built-in in-process planner | **must stay false** |

Do not put gateway tokens, OpenRouter keys, or raw JWTs in
`fly.toml [env]`. Do not flip `AGENT_LOOP_ENABLED` as a substitute for
the external path.

## JWT injection (closed in `0.41.0`)

The live plugin is a stdio child. A bearer on a tool argument, or in the
authored Cordis `env: OPENTHEORY_ACTOR_JWT: !!js process.env.…` block,
would leak into session / probe logs.

**Chosen pattern:** pass only `OPENTHEORY_ACTOR_JWT_FILE` through Cordis.
The parent writes the token to a file the child reads. Probe logs run
every JSON-RPC message through `app.harness.auth.redact`, which replaces
`OPENTHEORY_ACTOR_JWT`, `OPENTHEORY_ACTOR_JWT_FILE`,
`OPENTHEORY_DEV_ACTOR_ID`, `OPENTHEORY_GATEWAY_TOKEN`,
`OPENROUTER_API_KEY`, `authorization`, `bearer`, `token`, and `jwt`
values with `***`.

`OPENTHEORY_DEV_ACTOR_ID` is the same local/test path as
`X-Dev-Actor-Id`. It is `401` when `auth_dev_header_enabled` is off.

## Live OpenRouter probe

Implemented in `0.42.0`. Skip reasons:

- flag unset → skip
- no `OPENROUTER_API_KEY` / `OPENTHEORY_GATEWAY_TOKEN` → skip
- flag + token → one fail-closed gateway completion (tests inject
  `httpx.MockTransport`; a real key hits OpenRouter)

`dsh` / the SDK extra are **not** required for this probe — the gateway
is OpenTheory code. A full DeepSeek Harness session still needs the
optional extra; that is not this slice.

A green default pytest is not a live OpenRouter proof. The live *MCP*
door is covered by `tests/harness/test_live_mcp*.py` and does not need
a model key. Turn metering is covered by `test_turns*.py`.

## Fail-closed gateway

OpenWorld used a gateway in front of OpenRouter. OT does the same:

- `provider.only` allowlist (default `DeepSeek`)
- `allow_fallbacks: false`
- `require_parameters: true`
- `data_collection: deny`
- Upstream host must be `openrouter.ai`. `api.deepseek.com` is refused.
- A client `provider` block is overwritten, never honored.

The HTTP surface (`python -m app.harness.gateway`) authenticates the
child with `OPENTHEORY_GATEWAY_TOKEN` and forwards with
`OPENROUTER_API_KEY`. Two secrets, one job: the child never holds the
upstream key.

## Open questions (do not pretend they are closed)

1. **Wheel availability on CI Linux.** `0.1.5rc1` may not publish a usable
   manylinux wheel. That is why the extra is optional.
2. **`dsh` binary distribution.** PATH vs. SDK import — still optional.
3. ~~**JWT injection into MCP stdio.**~~ ✅ closed in `0.41.0` (file path
   + redaction).
4. ~~**Gateway token vs. raw OpenRouter key.**~~ ✅ closed in `0.42.0`
   (fail-closed gateway; child holds `OPENTHEORY_GATEWAY_TOKEN` only).
5. **Session persistence.** sdk-minimal keeps JSONL sessions. Whether OT
   wants that on disk, or only the ledger, is a later ops question. The
   ledger remains the source of truth either way.

## What this does *not* claim

- The SDK is installed in CI or on Fly.
- A live model call succeeded in default CI (it is skipped without a key).
- The built-in agent loop is on.
- Daily turn/request caps or an ops dashboard.
