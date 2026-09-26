# External harness actor path

> **What is (`0.42.0`).** Milestone 0 composition + fixture, the live
> MCP door (`live_mcp.py`), and the fail-closed OpenRouter gateway +
> turn supervision. Fly enablement is not shipped. If this blueprint
> disagrees with `backend/app/harness/`, the code wins.

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
  fixture MCP (M0 probes), live MCP door, fail-closed OpenRouter
  gateway, turn supervision, probe
- JWT-file injection (`OPENTHEORY_ACTOR_JWT_FILE`) so the bearer never
  enters session / probe logs
- Optional `[harness]` extra for `deepseek-harness-sdk==0.1.5rc1`
- Tests that run in default CI without a key or a `dsh` binary; ledger
  tests skip without `TEST_DATABASE_URL`

The FastAPI app does not import this package. Fly does not run it.
`AGENT_LOOP_ENABLED` is untouched (default `false`).

## What does not exist yet

- A reference campaign on this path
- Perpetual ops dashboard / daily caps
- Any new Alembic revision
- Fly enablement of the gateway or MCP child

## Capability tree

The authored Cordis patch strips coding tools (sandbox, pty, persistent
shell, DeepSeek-native LLM extras) and inserts exactly two plugins:
OpenRouter-via-env (`llm-pi-ai`) and the OpenTheory MCP client. The
persona is a research contributor. Composition fails closed on drift.
Turn supervision re-verifies the patch before every turn.

## Settlement

No settlement outside instruments. A harness turn that cannot call
`run_instrument` / `create_checkpoint` cannot mint a checkpoint. The
M0 fixture still returns `minted: false` on purpose. The live door
returns `minted: true` only after the chokepoint commits.

`ComputeDebit` remains the compute-spend ledger (contributor, not
funder). `FundingAllocation` stays money. `Validation` stays assessment.
The external path must not conflate those tables. A funded project with
`available <= 0` refuses live writes and supervised turns. Unfunded
projects are not treated as exhausted. Standalone instrument runs do
not debit — same as humans. Token metering is the gateway: each
supervised turn that spent tokens writes a `ComputeDebit` (no
`AgentRun`; notes `harness_gateway_turn`) through
`record_compute_debit`. An attempted completion that then failed still
debits if tokens moved. A refused start writes nothing.

## Relationship to the built-in planner

The in-process loop (`app/agent/`, `AGENT_LOOP_ENABLED`) is a different
owner of the session. This blueprint does not replace it and does not
light it. Two planners must not be enabled by one flag.
