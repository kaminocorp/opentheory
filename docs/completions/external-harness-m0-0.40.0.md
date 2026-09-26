# 0.40.0 — External DeepSeek Harness Milestone 0

**Goal.** Ship the first slice of the external agent adapter: docs, a
fail-closed Cordis composition, and Milestone-0 probe scaffolding.
Modeled on Mission Systems OpenWorld (not Launchpad Bubbles; OpenAir is
prior art). No live ledger binding. No Fly enablement. No
`AGENT_LOOP_ENABLED` flip.

**Shape.** Backend package `app/harness/` plus `docs/harness/` and a
blueprint. Fixture MCP stubs `run_instrument` / `create_checkpoint` and
the read helpers so default CI can assert inventory without
`OPENROUTER_API_KEY` or the DeepSeek SDK. **No schema, no migration.**
Sits on shipped `0.39.0` (`00b20bc`, #31) / current `main` `921cdd1`.

## What shipped

- **`docs/harness/`** — implementation plan (milestones 0→N),
  compatibility (pin `0.1.5rc1`, live probe pending), MCP tool
  contracts, backend note, prior-art citation (OpenWorld / OpenAir;
  no hospitality copy).
- **`docs/blueprints/external-harness.md`** — humans and agents stay on
  the same primitives; no side door.
- **Fail-closed composition** — `opentheory.cordis.yml` +
  `composition.py` (disabled coding tools, exact inserts, research
  persona, `serverName: opentheory`).
- **Fixture MCP** — stdio JSON-RPC; `echo_nonce` plus stub domain
  tools that return `minted: false`.
- **Probe** — always verifies composition + fixture; live OpenRouter
  is opt-in and **not implemented** (skip / refuse, never a fake pass).
- **Optional `[harness]` extra** — pin documented; default `uv sync`
  does not install the SDK.

## What did not change

- `create_checkpoint` remains the only Checkpoint writer.
- Append-only guards, membership, instruments, campaigns, orchestrator.
- `AGENT_LOOP_ENABLED` default `false`. Fly `[env]` untouched.
- Funder ≠ contributor ≠ validator. Account ≠ Actor.
- No Alembic revision. No frontend.

## Honest caveats

- Live MCP binding, gateway, and a reference campaign are later slices
  (`0.41+`). A green pytest is not a live model call.
- The SDK extra may not resolve on every Linux. That is why it is
  optional.
- The Cordis YAML loader understands the subset we author (no PyYAML
  in the default dep set). Unexpected YAML is `CompositionError`.

## Tests

- On-disk patch verifies; disabled / insert / persona / version /
  unknown-plugin drift reject.
- Fixture inventory matches `TOOL_STEMS`; stubs mint nothing; unknown
  `query` raises; stdio `tools/list` returns the exact set.
- Probe skips without flag / key / runtime; opt-in with a runtime
  still refuses (`not implemented in 0.40.0`).

## Verification

Recorded after the local agent-VM run (see the PR / changelog body).

## Unverified

- Live OpenRouter / `dsh` round-trip (no key, no binary in this
  environment; not in scope).
- JWT injection into a live MCP stdio (`0.41.0`).
