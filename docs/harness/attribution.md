# External harness — actor attribution audit (`0.51.1`)

> **Finding.** No production-code gap. The shipped `0.41.0`–`0.51.0`
> contract already attributes research writes to the JWT-resolved
> **Actor** (the member who authorized the door), not to that
> member's **Account**, and not to the built-in per-project
> `Research crew` agent. A non-member — including the account-less
> project agent — cannot write. `ComputeDebit` has no `actor_id`
> column; spend is project-scoped and does not touch
> `FundingAllocation`. Sit on shipped `0.51.0` (`fd9316d`, #45).
> Does not light `AGENT_LOOP_ENABLED`. Does not enable the gateway
> or MCP child on Fly. **No schema, no migration.**

This note is the audit. If it disagrees with `backend/app/harness/`,
the code wins.

## What was asked

On the external-harness path (live MCP door, `run_instrument` /
`create_checkpoint`, `HarnessSession`, `supervise_turn`, gateway,
`ComputeDebit` writes): is every ledger write attributed to the
correct Actor — and does the door refuse a non-member before a
write or a debit?

Invariants in play: an Account is not an Actor; funder /
contributor / validator stay on separate tables; only
`create_checkpoint` writes a `Checkpoint`.

## Write paths

### 1. Live MCP `run_instrument` / `create_checkpoint`

| | |
| --- | --- |
| **Who is recorded as Actor** | The JWT-resolved Actor. Bearer → Account → that account's primary `human` Actor (`app/api/deps.py` `resolve_actor_from_bearer` / `_resolve_or_provision`). Local/test `OPENTHEORY_DEV_ACTOR_ID` may name any Actor, still behind `auth_dev_header_enabled`. |
| **Who is Account / owner** | The Account is the auth principal only. It is not written on `Checkpoint` or `Contribution`. |
| **Membership** | `ensure_is_member` before either write (`live_mcp.py` `_run_instrument`, `_create_checkpoint`). Gate is **account** membership (`ProjectMember.account_id`). Account-less Actors (system, dev-bootstrap, the per-project `Research crew` agent) are `403`. Missing project is `404`. |
| **Chokepoint** | `services.tool_runs.run_instrument` → `create_checkpoint`, or `services.checkpoints.create_checkpoint` directly. `author_id = actor.id`. `Contribution.actor_id = actor.id`. The handler does not mint a `Checkpoint` itself. |

A human Account does **not** appear as the contributor. The
contributor is that Account's primary human **Actor**. The same
person may also be the funder (`FundingAllocation.account_id`) —
roles stay on different tables.

The per-project `Actor(type=agent, display_name="Research crew")`
(`services/agent_actors.py`, Decision #3) is **not** the live-MCP
identity. It is account-less and is not a `ProjectMember`. The
built-in loop (`AGENT_LOOP_ENABLED`, dark) uses it after a
commissioning human already passed the route gate. Putting it on
this door would `403` at `ensure_is_member`, or would require
bypassing membership, or a schema change. The campaign child
explicitly does not mint an Actor (`campaign.py` `open_session`).

### 2. `HarnessSession` / gateway / `supervise_turn` debit

| | |
| --- | --- |
| **Who is recorded as Actor** | Nobody. `ComputeDebit` has no `actor_id` (schema since `0.19.0`). `record_compute_debit` takes `project_id` + tokens + model + notes. Harness rows use notes `harness_session_turn` and leave `agent_run_id` null (no `AgentRun` on this path). Hold / release rows are amount `0` and are not pot spend. |
| **Who is Account / owner** | The project's funded pot. `FundingAllocation.account_id` (the funder) is not read or written. Spend is `project_budget.spent` = Σ `ComputeDebit.amount`. |
| **Membership** | Not checked on `authorize` / `record_spend`. The campaign / gateway child is **project-bound** (`OPENTHEORY_PROJECT_ID`). The member JWT lives on the **MCP** child (`OPENTHEORY_ACTOR_JWT_FILE`). Those are separate processes. Inbound HTTP auth on the gateway is `OPENTHEORY_GATEWAY_TOKEN`, not a member JWT. |
| **Chokepoint** | `record_compute_debit` when `tokens_used > 0`. Hold / release go through `write_daily_cap_adjustment` (amount `0`). Neither path calls `create_checkpoint`. |

This is not a hole that lets a non-member mint research
provenance. A debit without a member JWT cannot land a
checkpoint. Remapping spend onto an Actor would need a new
`ComputeDebit.actor_id` column — a schema change this slice
refuses. The built-in loop attributes spend via `agent_run_id`,
which this path also does not have.

`supervise_turn` composes the same owner, then (only after a
successful completion) dispatches `live_mcp.invoke` with
`actor_env`. Membership is enforced on that MCP call, not on the
debit. An outsider `actor_env` still records project-scoped spend
when tokens moved and still cannot mint.

## What is not a gap

- **JWT human Actor as author of MCP writes.** That is the
  `0.41.0` contract (`tools.md`: "as the JWT Actor"; `auth.py`:
  same `ActingActor` path humans use). The harness is another
  client of the human APIs, authenticated as a member.
- **Blueprint wording "type=agent".** `external-harness.md` and
  `conceptual-model.md` previously said the session *is* an
  `Actor(type=agent)`. The code resolves a JWT to the Account's
  primary **human** Actor. Code wins; those sentences are
  tightened in `0.51.1`. Humans and agents still share the same
  primitives — there is no parallel data model.
- **Debit without a member JWT on the gateway child.**
  Architectural split, not an unattributed contributor. The
  operator binds `OPENTHEORY_PROJECT_ID`. The process already
  holds DB credentials. Membership stays on the domain door.
- **Account-less `Research crew` cannot pass `ensure_is_member`.**
  Decision #3. Not a regression; a 0.51.1 test now pins it.

## What would have been a real gap (not found)

- A path that writes `Contribution.actor_id` or
  `Checkpoint.author_id` from an Account id.
- A path that mints a `Checkpoint` outside `create_checkpoint`.
- A non-member (or account-less agent) that can
  `run_instrument` / `create_checkpoint`.
- A debit that writes or rewrites `FundingAllocation` (agent as
  funder).
- A schema change to hang an actor on `ComputeDebit`.

## Tests that pin this

Already shipped (`0.41.0`+): member `calc.eval` contribution is
the JWT / dev Actor; non-member human is `403`; bad JWT is `401`;
`agent_run_id` is null on harness spend; debit only when
`tokens_used > 0`.

Added in `0.51.1`:

- Account-less project agent is `403` on both write stems; nothing
  minted.
- Member write sets `Checkpoint.author_id` and
  `Contribution.actor_id` to that human Actor; no `Research crew`
  row is created.
- Gateway / `supervise_turn` debit leaves `FundingAllocation`
  rows (funder, amount) unchanged.
- `supervise_turn` with an outsider `actor_env` still debits when
  tokens moved and still does not mint.
