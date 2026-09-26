# External DeepSeek Harness — implementation plan

> **Status — `0.42.0` Milestone 2 is this slice** (OpenRouter gateway +
> turn supervision), sitting on shipped `0.41.0` live MCP and `0.40.0`
> composition. Not a product loop. Not enabled on Fly. Does not light
> `AGENT_LOOP_ENABLED`.

The external agent adapter lives **outside** the built-in OpenRouter planner
(`0.12.x`–`0.32.0`). DeepSeek Harness SDK + an OpenRouter gateway own the
session. OpenTheory exposes a **thin MCP plugin** as the only domain door.
Ledger writes stay on the existing chokepoints: `run_instrument` and
`create_checkpoint`. There is no side door and no settlement outside
instruments.

Architectural prior art: Mission Systems OpenWorld (Cordis composition +
OpenRouter gateway + fail-closed tool strip) and OpenAir. Mapping and
citations live in `docs/harness/prior-art.md`. Do not copy hospitality
persona or SQL tools.

## Why this is a separate path

The shipped thin agent loop is an in-process FastAPI `BackgroundTask` that
calls OpenRouter, then `run_instrument`, behind `AGENT_LOOP_ENABLED`. That
loop stays dark. The external harness is a different process: a pinned
runtime with a composed capability tree, talking to OpenTheory only through
MCP. Same `Actor`, same membership, same `ComputeDebit` — different
ownership of the session.

Milestone 0 pinned the composition so a later binding cannot quietly grow
a shell. Milestone 1 (`0.41.0`) binds the live APIs through that door.
Milestone 2 (`0.42.0`) puts OpenRouter behind a fail-closed gateway and
meters token spend.

## Milestones

| Slice | What ships | What must stay out |
| --- | --- | --- |
| **0 — `0.40.0`** | Docs, `opentheory.cordis.yml`, composition verify, fixture MCP (`echo_nonce` + stub domain tools), probe that skips without a key / SDK | Live ledger writes; gateway; Fly enablement; `AGENT_LOOP_ENABLED` |
| **1 — `0.41.0`** | Live MCP binding: JWT Actor + `ensure_is_member` + real `run_instrument` / `create_checkpoint` + claim/thread/budget reads | Gateway supervision; campaigns; a second settlement path |
| **2 — `0.42.0` (this)** | OpenRouter gateway + turn supervision (provider allowlist, `allow_fallbacks: false`, `require_parameters: true`, `data_collection: deny`); `ComputeDebit` for LLM tokens | Lighting the built-in planner; daily caps; Fly enablement |
| **3 — later** | Reference campaign (odd perfect numbers) on the external path | Auto-validate / auto-fund / auto-merge |
| **4 — later** | Perpetual ops dashboard; daily turn/request caps | Lean REPL / LeanDojo (separate line) |

Each slice stays small and deployable. A slice that cannot run in default CI
without `OPENROUTER_API_KEY` is not done.

## Fail-closed composition (load-bearing)

`backend/app/harness/composition.py` is the chokepoint for the *capability
tree*, the way `create_checkpoint` is the chokepoint for ledger writes:

- Runtime / SDK pin: **`0.1.5rc1`**
- Exact disabled set: sandbox, sandbox-policy, subprocess, pty,
  terminal-*, persistent-*, and the DeepSeek-native LLM extras
- Exact insert set: `llm-pi-ai` (OpenRouter via env) + `opentheory-mcp`
- Exact MCP stems: `run_instrument`, `create_checkpoint`, `list_claims`,
  `get_thread_context`, `get_budget`, plus M0 `echo_nonce`
- Research-contributor persona — no hospitality / SQL voice

Drift raises `CompositionError`. Tests mutate the patch and expect reject.
Turn supervision re-runs `verify()` before every turn.

## Optional `[harness]` extra

Default `uv sync --group dev` (CI) must not need the DeepSeek SDK or a
`dsh` binary. The pin is documented; install via
`uv sync --extra harness` when a wheel exists for the host. See
`docs/harness/compatibility.md`.

## Probe

`python -m app.harness` always verifies composition + fixture.
A live OpenRouter round-trip is opt-in (`OPENTHEORY_HARNESS_LIVE=1`) and
runs one fail-closed gateway completion when a key is present. Missing
key / unset flag skip cleanly. The live *MCP* door is
`python -m app.harness.live_mcp` (`0.41.0`). The HTTP gateway child is
`python -m app.harness.gateway` (`0.42.0`).

## Invariants this line must not break

- Append-only ledger; `create_checkpoint` is the only Checkpoint writer
- Instruments return `result | refuted | undecided`; exceptions mint nothing
- Account ≠ Actor; funder ≠ contributor ≠ validator
- JWT Actor + membership + `ComputeDebit` — same API humans use
- Built-in `AGENT_LOOP_ENABLED` stays dark; this path does not flip it
- Secrets never in `fly.toml [env]`
