# External harness — actor attribution (`0.51.1` / `0.52.0`)

> **0.55.0.** OWNER-only agent session mint / rotate / revoke.
> Harness/MCP resolver verifies `typ=agent_session`. HTTP
> `ActingActor` refuses that bearer (`403`). MCP writes with
> that bearer author as the agent and snapshot
> `sponsored_by_actor_id` from the minting human.
> `authorize()` accepts the agent token (and still accepts a
> human JWT / flagged rostered-agent `DEV_ACTOR_ID`). Sit on
> shipped `0.54.0` (`7a1fa0c`, #50).
>
> **0.54.0.** `ensure_is_member` is type-aware: a rostered
> `type=agent` Actor passes research writes; an un-rostered /
> suspended / revoked agent is `403`. Token mint landed in
> `0.55.0`. Sit on shipped `0.53.0` (`2b2a135`, #49).
>
> **0.52.0.** The leftover spend-path gap is closed. Live MCP writes
> still attribute to the JWT-resolved **Actor** and still pass
> `ensure_is_member`. `HarnessSession.authorize()` now does the same
> membership check for the actor the session / turn is running for
> (`actor_env`, else `env`) *before* a hold or a provider call. A
> non-member or account-less actor is `TurnRefused`. `ComputeDebit`
> still has no `actor_id`; spend stays project-scoped and does not
> touch `FundingAllocation`. Sit on shipped `0.51.1` (`3eeeaf5`,
> #46). Does not light `AGENT_LOOP_ENABLED`. Does not enable the
> gateway or MCP child on Fly. **No schema, no migration.**
>
> **0.51.1 finding (writes).** No production-code gap on MCP writes.
> The shipped `0.41.0`–`0.51.0` contract already attributes research
> writes to the JWT-resolved **Actor**, not that member's
> **Account**, and not the built-in per-project `Research crew`
> agent. A non-member — including the account-less project agent —
> cannot mint. The 0.51.1 audit recorded that debit membership was
> the MCP door, not `authorize()`; `0.52.0` moves that gate to the
> spend chokepoint.

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
`create_checkpoint` writes a `Checkpoint`. Spend now also
refuses a non-member before a hold (`0.52.0`).

## Write paths

### 1. Live MCP `run_instrument` / `create_checkpoint`

| | |
| --- | --- |
| **Who is recorded as Actor** | The JWT-resolved Actor. Bearer → Account → that account's primary `human` Actor (`app/api/deps.py` `resolve_actor_from_bearer` / `_resolve_or_provision`). Local/test `OPENTHEORY_DEV_ACTOR_ID` may name any Actor, still behind `auth_dev_header_enabled`. |
| **Who is Account / owner** | The Account is the auth principal only. It is not written on `Checkpoint` or `Contribution`. |
| **Membership** | `ensure_is_member` before either write (`live_mcp.py` `_run_instrument`, `_create_checkpoint`). Gate is type-aware (`0.54.0`): humans need `ProjectMember`; agents need an ACTIVE roster row; `system` is `403`. An un-rostered `Research crew` (including account-less orphans) is `403`. Missing project is `404`. |
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
| **Membership** | `ensure_is_member` on `authorize()` (`0.52.0`). The actor the session / turn is running for is resolved from `actor_env` (the `supervise_turn` MCP credential) or, if unset, `env` (campaign / gateway process — operator-supplied JWT file / JWT / flagged `OPENTHEORY_DEV_ACTOR_ID`, same injection as `live_mcp`). Missing credential, non-member, or account-less actor is `TurnRefused` before any hold or provider call. `record_spend` does **not** re-check: a member removed mid-turn does not drop a debit for tokens that already moved; the next authorize refuses. Inbound HTTP auth on the gateway is still `OPENTHEORY_GATEWAY_TOKEN`. |
| **Chokepoint** | Membership + remaining-room hold on `authorize()`. `record_compute_debit` when `tokens_used > 0`. Hold / release go through `write_daily_cap_adjustment` (amount `0`). Neither path calls `create_checkpoint`. |

This is not a hole that lets a non-member mint research
provenance. A refused start cannot land a checkpoint either.
Remapping spend onto an Actor would need a new
`ComputeDebit.actor_id` column — a schema change this slice
refuses. The built-in loop attributes spend via `agent_run_id`,
which this path also does not have.

`supervise_turn` passes `actor_env` onto `HarnessSession` so the
library path and the session-owned gateway share the same
membership gate. After a successful completion it still
dispatches `live_mcp.invoke` with `actor_env` (writes stay on
that door). An outsider `actor_env` now refuses before the
model: no hold, no debit, no mint.

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
- **Debit without a member JWT on the gateway child.** Closed in
  `0.52.0` at `authorize()`. The operator still binds
  `OPENTHEORY_PROJECT_ID`. The actor the turn is running for must
  also be a current member (same credential injection as MCP). A
  process that only has the gateway token and a project id
  refuses (`actor required`) rather than spending.
- **Account-less `Research crew` cannot pass `ensure_is_member`.**
  Decision #3. 0.51.1 pins the write door; 0.52.0 pins the spend
  path. Not a regression.

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
- `supervise_turn` with an outsider `actor_env` refuses (`0.52.0`):
  no hold, no debit, no provider call, no mint. A current member
  is allowed. An account-less `Research crew` actor refuses. A
  collaborator removed mid-session cannot authorize again;
  `record_spend` after a successful authorize still bills.
