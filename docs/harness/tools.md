# External harness — MCP tool contracts

> **Status — `0.40.0` Milestone 0.** Stems and stub payloads are pinned.
> Live JWT binding is `0.41.0`. The fixture in
> `backend/app/harness/fixture_mcp.py` implements these names and **mints
> nothing**.

The DeepSeek MCP client prefixes tools as `mcp__opentheory__<stem>`
(`serverName: opentheory`). Composition verifies the prefixed set.
The fixture speaks the unprefixed stems on stdio; the runtime adds the
prefix.

## Inventory (fail-closed)

| Stem | Kind | M0 fixture | Live (`0.41.0`) |
| --- | --- | --- | --- |
| `run_instrument` | write (via chokepoint) | stub `undecided`, `minted: false` | `POST …/instruments/{name}/run` as the JWT Actor |
| `create_checkpoint` | write (chokepoint) | stub `checkpoint_id: null`, `minted: false` | `create_checkpoint` — same service humans use |
| `list_claims` | read | empty list | project claims the actor may see |
| `get_thread_context` | read | empty open-claims | thread + open claims + grounding raise lines |
| `get_budget` | read | `available: null` | `project_budget.available` (`ComputeDebit`) |
| `echo_nonce` | probe only | echoes `OPENTHEORY_PROBE_NONCE` | keep for composition probes; not a domain write |

No shell. No filesystem. No web fetch. No SQL. No subagents. No
`describe_schema` / `query` / `render_figure`. Those are OpenWorld
hospitality tools and must not appear in this inventory.

## Honesty rules (live and fixture)

- **Writes land only through existing chokepoints.** The MCP handler is
  another client of `run_instrument` / `create_checkpoint`, not a second
  writer.
- **Exceptions mint nothing.** A transport error, 401, 403, or 422 is not
  a `result`.
- **Instruments still return only `result | refuted | undecided`.**
- **Reads do not write.** `list_claims` / `get_thread_context` / `get_budget`
  are derived. They do not call `create_checkpoint`.
- **Membership is authorization.** A non-member is `403` (or `404` if the
  project is missing) — same as the human API. The fixture does not
  pretend otherwise; it simply does not hit the API.
- **Budget is `ComputeDebit`, not `FundingAllocation`.** The agent is a
  contributor and never a funder.

## Fixture payloads (M0)

`run_instrument`:

```json
{
  "ok": true,
  "stub": true,
  "tool": "run_instrument",
  "instrument": "<name or null>",
  "status": "undecided",
  "detail": "m0_fixture_does_not_touch_the_ledger",
  "minted": false
}
```

`create_checkpoint`:

```json
{
  "ok": true,
  "stub": true,
  "tool": "create_checkpoint",
  "summary": "<summary or null>",
  "detail": "m0_fixture_does_not_touch_the_ledger",
  "minted": false,
  "checkpoint_id": null
}
```

A test that sees `minted: true` or a real checkpoint id from this module
is a bug.

## Live binding notes (not in 0.40.0)

- Auth: verified Supabase bearer → `Account` → primary `human` or a
  dedicated `agent` Actor owned by that account. Do not invent a header
  that bypasses JWT in production.
- Every write: authenticate → `ensure_is_member` → service.
- `run_instrument` already records the blame tuple and the checkpoint.
  The MCP tool should not wrap that in a second checkpoint.
- `create_checkpoint` is for explicit research-state notes the instrument
  path does not cover. It is not a dump of the model transcript.
- Gateway metering (`0.42.0`) must debit `ComputeDebit` the same way the
  built-in planner does — or refuse to start. Do not skip metering.

## Adding a tool

1. Add the stem to `DOMAIN_TOOL_STEMS` or `PROBE_TOOL_STEMS`.
2. Implement it on the fixture (stub) **and** document it here.
3. Composition tests must fail if the fixture inventory drifts.
4. Do not add a tool that writes the ledger except through
   `run_instrument` / `create_checkpoint`.
5. Do not add coding tools. If the SDK grows a new default plugin, add
   it to `DISABLED` in the same slice that notices it.
