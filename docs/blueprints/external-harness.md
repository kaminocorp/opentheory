# External harness actor path

> **What is (`0.47.0`).** Milestone 0 composition + fixture, the live
> MCP door (`live_mcp.py`), the fail-closed OpenRouter gateway, a
> session owner (`HarnessSession`) plus the odd-perfect reference
> campaign, a fail-closed campaign composition that cannot start the
> unmetered gateway proxy, a daily token cap counted from today's
> `harness_session_turn` `ComputeDebit` rows (default 20_000 / UTC
> day; survives a process restart), and a remaining-room hold so two
> overlapping authorizes cannot both debit past that cap. Fly
> enablement is not shipped. If this blueprint disagrees with
> `backend/app/harness/`, the code wins.

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
  gateway, turn supervision, `HarnessSession` owner, odd-perfect
  reference campaign (the authored `llm-pi-ai` child), probe
- JWT-file injection (`OPENTHEORY_ACTOR_JWT_FILE`) so the bearer never
  enters session / probe logs
- Optional `[harness]` extra for `deepseek-harness-sdk==0.1.5rc1`
- Tests that run in default CI without a key or a `dsh` binary; ledger
  tests skip without `TEST_DATABASE_URL`

The FastAPI app does not import this package. Fly does not run it.
`AGENT_LOOP_ENABLED` is untouched (default `false`).

## What does not exist yet

- Perpetual ops dashboard
- Any new Alembic revision
- Fly enablement of the gateway or MCP child
- A live `dsh` loop in production (`AGENT_LOOP_ENABLED` stays false)

## Capability tree

The authored Cordis patch strips coding tools (sandbox, pty, persistent
shell, DeepSeek-native LLM extras) and inserts exactly two plugins:
OpenRouter-via-env (`llm-pi-ai`) and the OpenTheory MCP client. The
persona is a research contributor. Composition fails closed on drift
and on an unmetered gateway child: `llm-pi-ai` must launch
`python -m app.harness.campaign` and pass `OPENTHEORY_PROJECT_ID` as
an operator-supplied env name (same pattern as
`OPENTHEORY_ACTOR_JWT_FILE`). A composition that launches
`app.harness.gateway`, or that sets
`OPENTHEORY_HARNESS_UNMETERED_PROBE`, is not the campaign composition.
Turn supervision re-verifies the patch before every turn.

## Settlement

No settlement outside instruments. A harness turn that cannot call
`run_instrument` / `create_checkpoint` cannot mint a checkpoint. The
M0 fixture still returns `minted: false` on purpose. The live door
returns `minted: true` only after the chokepoint commits.

`ComputeDebit` remains the compute-spend ledger (contributor, not
funder). `FundingAllocation` stays money. `Validation` stays assessment.
The external path must not conflate those tables. A funded project with
`available <= 0` refuses live writes and session-owned gateway turns.
Unfunded projects are not treated as exhausted. Standalone instrument
runs do not debit — same as humans. Token metering is the session
owner: `HarnessSession` bound on `create_gateway_app` (or
`OPENTHEORY_PROJECT_ID`) authorizes before the completion and writes a
`ComputeDebit` (no `AgentRun`; notes `harness_session_turn`) through
`record_compute_debit` when tokens moved. The campaign composition
cannot start that child unbound. An attempted completion that then
failed still debits if tokens moved. A refused start writes nothing.
`supervise_turn` composes the same owner; it is not a second writer.
Turn index is process-local (a restart starts at 0). The daily token
cap is not: `authorize()` sums today's `ComputeDebit` rows whose notes
start with `harness_session_turn` and refuses before the model when
that sum has already hit `OPENTHEORY_HARNESS_DAILY_TOKEN_CAP`
(default **20_000** tokens per UTC day). A refused daily-cap start
mints nothing and does not call OpenRouter. `0.47.0` takes the
project row `FOR UPDATE` and appends a remaining-room hold on that
same ledger so two overlapping authorizes cannot both pass and both
debit past the cap. Release is a new credit row after the model call.

## Relationship to the built-in planner

The in-process loop (`app/agent/`, `AGENT_LOOP_ENABLED`) is a different
owner of the session. This blueprint does not replace it and does not
light it. Two planners must not be enabled by one flag.
