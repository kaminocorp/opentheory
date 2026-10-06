# External DeepSeek Harness — implementation plan

> **Status — `0.51.0` guards 0.50 serialization and hold TTL**
> on shipped `0.50.0` (turn-room clamp), sitting on
> `0.49.1` (Overview eyeball) / `0.49.0` (ops dashboard),
> `0.48.0` orphan-hold release, `0.47.0` remaining-room hold,
> `0.46.0` daily token cap, `0.45.0` `source.pin`, `0.44.0`
> fail-closed composition, `0.43.0` session owner, `0.42.0`
> gateway, `0.41.0` live MCP, and `0.40.0` composition. Not a
> product loop. Not enabled on Fly. Does not light
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
| **2 — `0.42.0`** | OpenRouter gateway + turn supervision (provider allowlist, `allow_fallbacks: false`, `require_parameters: true`, `data_collection: deny`); `ComputeDebit` for LLM tokens | Lighting the built-in planner; daily caps; Fly enablement |
| **3 — `0.43.0`** | Session owner (`HarnessSession`) on the gateway path a campaign actually runs; odd-perfect reference campaign (human question / roster / budget; instrument-only) | Auto-validate / auto-fund / auto-merge; Fly enablement; `AGENT_LOOP_ENABLED` |
| **3b — `0.44.0`** | Fail-closed campaign composition: `llm-pi-ai` launches `app.harness.campaign`; `verify()` rejects the bare unmetered proxy; `OPENTHEORY_PROJECT_ID` is an env name | Fly enablement; `AGENT_LOOP_ENABLED`; a campaign table; lighting the built-in planner |
| **4a — `0.46.0`** | Daily token cap on the session-owned path: today's `harness_session_turn` `ComputeDebit` sum (default 20_000 / UTC day) refuses before the model; survives a process restart | Ops dashboard; Fly enablement; `AGENT_LOOP_ENABLED`; a campaign table |
| **4a leftover — `0.47.0`** | Remaining-room hold under a project-row lock so two overlapping authorizes cannot both debit past the cap | Ops dashboard; Fly enablement; `AGENT_LOOP_ENABLED`; a campaign table |
| **4a leftover — `0.48.0`** | Release an unmatched hold older than the TTL on the next authorize so a crash leftover does not pin the UTC day; two live overlapping turns still cannot both debit past the cap | Ops dashboard; Fly enablement; `AGENT_LOOP_ENABLED`; a campaign table |
| **4b — `0.49.0`** | Perpetual ops dashboard: read-only pot / daily-cap / hold / enablement snapshot | Fly enablement; `AGENT_LOOP_ENABLED`; a refusals table; Lean REPL / LeanDojo |
| **4b leftover — `0.49.1`** | Overview browser walk of the shipped bay; money-precision honesty (`$0.0004` stays `$0.0004`) | Fly enablement; `AGENT_LOOP_ENABLED`; a refusals table; Lean REPL / LeanDojo |
| **4a leftover — `0.50.0`** | Turn-room clamp: `max_tokens` bounded to remaining daily / pot room (completion rate when funded; `pot_room=none` when not); below-floor refuse; provider overshoot recorded as truth | Fly enablement; `AGENT_LOOP_ENABLED`; a refusals table; a schema change |
| **4a leftover — `0.51.0` (this)** | Serialization guard: 0.50 already occupies remaining daily room so there is no pot race; regression for overlapping authorize; hold TTL must strictly exceed provider timeout + margin | Fly enablement; `AGENT_LOOP_ENABLED`; a refusals table; a schema change |

Each slice stays small and deployable. A slice that cannot run in default CI
without `OPENROUTER_API_KEY` is not done.

## Fail-closed composition (load-bearing)

`backend/app/harness/composition.py` is the chokepoint for the *capability
tree*, the way `create_checkpoint` is the chokepoint for ledger writes:

- Runtime / SDK pin: **`0.1.5rc1`**
- Exact disabled set: sandbox, sandbox-policy, subprocess, pty,
  terminal-*, persistent-*, and the DeepSeek-native LLM extras
- Exact insert set: `llm-pi-ai` (OpenRouter via env; session-owned
  campaign child) + `opentheory-mcp`
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
`python -m app.harness.live_mcp` (`0.41.0`). The campaign composition
child is `python -m app.harness.campaign` (`0.44.0`); it refuses when
unbound. `python -m app.harness.gateway` is an explicit unmetered
probe (`OPENTHEORY_HARNESS_UNMETERED_PROBE`) and is not what `verify()`
accepts.

## Invariants this line must not break

- Append-only ledger; `create_checkpoint` is the only Checkpoint writer
- Instruments return `result | refuted | undecided`; exceptions mint nothing
- Account ≠ Actor; funder ≠ contributor ≠ validator
- JWT Actor + membership + `ComputeDebit` — same API humans use
- Built-in `AGENT_LOOP_ENABLED` stays dark; this path does not flip it
- Secrets never in `fly.toml [env]`
