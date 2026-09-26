# External harness actor path

> **What is (`0.41.0`).** Milestone 0 composition + fixture, plus the
> live MCP door (`live_mcp.py`) bound to JWT Actor + membership + the
> existing chokepoints. Gateway / Fly enablement are not shipped. If this
> blueprint disagrees with `backend/app/harness/`, the code wins.

## The rule

Humans and agents use the **same** primitives. An external DeepSeek
Harness session is an `Actor` (`type=agent`). It authenticates, passes
membership, and writes the ledger only through `run_instrument` and
`create_checkpoint`. There is no side door and no settlement outside
instruments.

This is the same design rule as `docs/blueprints/primitives.md` and
`docs/blueprints/conceptual-model.md`. The external runtime does not
earn a parallel data model.

## What exists now

- `docs/harness/` — plan, compatibility, tool contracts, prior-art note
- `backend/app/harness/` — composition verify, `opentheory.cordis.yml`,
  fixture MCP (M0 probes), live MCP door, probe (OpenRouter skip)
- JWT-file injection (`OPENTHEORY_ACTOR_JWT_FILE`) so the bearer never
  enters session / probe logs
- Optional `[harness]` extra for `deepseek-harness-sdk==0.1.5rc1`
- Tests that run in default CI without a key or a `dsh` binary; ledger
  tests skip without `TEST_DATABASE_URL`

The FastAPI app does not import this package. Fly does not run it.
`AGENT_LOOP_ENABLED` is untouched (default `false`).

## What does not exist yet

- Gateway + turn supervision (`0.42.0`)
- A reference campaign on this path
- Perpetual ops dashboard
- Any new Alembic revision

## Capability tree

The authored Cordis patch strips coding tools (sandbox, pty, persistent
shell, DeepSeek-native LLM extras) and inserts exactly two plugins:
OpenRouter-via-env (`llm-pi-ai`) and the OpenTheory MCP client. The
persona is a research contributor. Composition fails closed on drift.

## Settlement

No settlement outside instruments. A harness turn that cannot call
`run_instrument` / `create_checkpoint` cannot mint a checkpoint. The
M0 fixture still returns `minted: false` on purpose. The live door
returns `minted: true` only after the chokepoint commits.

`ComputeDebit` remains the compute-spend ledger (contributor, not
funder). `FundingAllocation` stays money. `Validation` stays assessment.
The external path must not conflate those tables. A funded project with
`available <= 0` refuses live writes. Standalone instrument runs do not
debit — same as humans. Token metering is the gateway slice.

## Relationship to the built-in planner

The in-process loop (`app/agent/`, `AGENT_LOOP_ENABLED`) is a different
owner of the session. This blueprint does not replace it and does not
light it. Two planners must not be enabled by one flag.
