# External harness — MCP tool contracts

> **Status — `0.41.0` live door.** Stems are pinned. The fixture in
> `backend/app/harness/fixture_mcp.py` still **mints nothing** (M0
> probes). The live server is `backend/app/harness/live_mcp.py`.

The DeepSeek MCP client prefixes tools as `mcp__opentheory__<stem>`
(`serverName: opentheory`). Composition verifies the prefixed set.
Both servers speak the unprefixed stems on stdio; the runtime adds the
prefix.

## Inventory (fail-closed)

| Stem | Kind | M0 fixture | Live (`0.41.0`) |
| --- | --- | --- | --- |
| `run_instrument` | write (via chokepoint) | stub `undecided`, `minted: false` | `services.tool_runs.run_instrument` as the JWT Actor |
| `create_checkpoint` | write (chokepoint) | stub `checkpoint_id: null`, `minted: false` | `services.checkpoints.create_checkpoint` |
| `list_claims` | read | empty list | project (or thread) claims the actor may see |
| `get_thread_context` | read | empty open-claims | thread + open claims + grounding raise lines |
| `get_budget` | read | `available: null` | `project_budget.available` (`ComputeDebit`) |
| `echo_nonce` | probe only | echoes `OPENTHEORY_PROBE_NONCE` | same echo; not a domain write |

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
  project is missing). The fixture does not pretend otherwise; it simply
  does not hit the API.
- **Budget is `ComputeDebit`, not `FundingAllocation`.** The agent is a
  contributor and never a funder. A funded project with `available <= 0`
  refuses writes. Unfunded projects are not treated as exhausted.
  Standalone instrument runs do not debit (same as the human toolbench);
  gateway token metering is `0.42.0`.

## Auth injection (do not put the bearer on a tool argument)

Chosen pattern — recorded so a later session logger cannot quietly
regress it:

1. **Preferred.** Parent writes the member-scoped JWT to a `0600` file
   and passes **only** `OPENTHEORY_ACTOR_JWT_FILE` (a path) into the
   Cordis MCP `env` block. Session logs may record the path.
2. **Accepted, never logged.** `OPENTHEORY_ACTOR_JWT` for a process that
   is not going through session-logged Cordis config. Probe logs redact
   this key.
3. **Local / tests only.** `OPENTHEORY_DEV_ACTOR_ID` maps to the existing
   `X-Dev-Actor-Id` resolver, and only when `auth_dev_header_enabled` is
   on. Production (flag off) is `401`.

Resolution is the FastAPI `ActingActor` path: verified bearer → Account
→ primary `human` Actor. Do not invent a header that bypasses JWT in
production. Do not put the bearer on `tools/call` arguments — those
land in session JSONL.

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

## Live payloads (`0.41.0`)

Success (`run_instrument` after `calc.eval`):

```json
{
  "ok": true,
  "stub": false,
  "tool": "run_instrument",
  "instrument": "calc.eval",
  "status": "result",
  "minted": true,
  "checkpoint_id": "<uuid>"
}
```

Failure (401 / 403 / 422 / unknown instrument): `ok: false`,
`minted: false`, `checkpoint_id: null`. Not a `result`.

- `run_instrument` already records the blame tuple and the checkpoint.
  The MCP tool does not wrap that in a second checkpoint.
- `create_checkpoint` is for explicit research-state notes the instrument
  path does not cover. It is not a dump of the model transcript.
- Gateway metering (`0.42.0`) must debit `ComputeDebit` the same way the
  built-in planner does — or refuse to start. Do not skip metering.

## Adding a tool

1. Add the stem to `DOMAIN_TOOL_STEMS` or `PROBE_TOOL_STEMS`.
2. Implement it on the fixture (stub) **and** the live server, and
   document it here.
3. Composition tests must fail if either inventory drifts.
4. Do not add a tool that writes the ledger except through
   `run_instrument` / `create_checkpoint`.
5. Do not add coding tools. If the SDK grows a new default plugin, add
   it to `DISABLED` in the same slice that notices it.
