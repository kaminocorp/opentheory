# Design: first-class agent Actor identity

> **Status — Approved 2026-10-06; implementation in slices.**
> Slice A (schema) shipped as `0.53.0` (`2b2a135`, #49).
> Slice B (membership gate) shipped as `0.54.0` (`7a1fa0c`, #50).
> Slice C (agent session token) is this branch as `0.55.0`.
> Slices D–G are not started. Precursor: shipped `0.52.0`
> (PR #48) puts a human-member gate on
> `HarnessSession.authorize()`; this slice swaps that gate
> onto the agent session token (human Console JWT unchanged).
> If this doc disagrees with `backend/app/` on this branch,
> the code is what exists here and this file is the approved
> change.
>
> Does not light `AGENT_LOOP_ENABLED`. Does not enable the gateway
> or MCP child on Fly. FastAPI still must not import `app.harness`.
> Five UI tabs only (Research, Instruments, Crew, Funding, Overview).

Owner end vision: humans set the research question, choose which
agents to deploy (the roster), and set the budget. Agents then
research autonomously — no human in the loop during exploration or
proof. The ledger must credit the **agent that did the work**, and
still name the **human/account that deployed and funded it**.

This proposal is the identity, auth, attribution, and spend design
that makes that vision structurally true. It is not a product loop
and it is not a Fly enablement.

---

## 1. Problem

### What the ledger records today

`0.51.1` (`docs/harness/attribution.md`) audited the live door and
found no production-code gap against the **shipped** contract:

| Path | Who is recorded | Membership |
| --- | --- | --- |
| Live MCP `run_instrument` / `create_checkpoint` | JWT → Account → that account's primary `human` Actor (`app/api/deps.py` `resolve_actor_from_bearer`; `app/harness/auth.py` `resolve_mcp_actor`). `Checkpoint.author_id` and `Contribution.actor_id` are that human. | `ensure_is_member` (`app/services/project_members.py`) keys on **`ProjectMember.account_id`**. Account-less Actors — `system`, dev-bootstrap, the per-project `Research crew` agent — are `403`. |
| `HarnessSession.authorize` / `record_spend` / `supervise_turn` | Nobody. `ComputeDebit` has no `actor_id` (schema since `0.19.0`, migration `0015`). Notes `harness_session_turn`. `agent_run_id` null. | **`0.51.1`:** not checked. **`0.52.0` (PR #48):** `authorize()` resolves the JWT-file / JWT / flagged-dev actor (`actor_env`, else `env` — same injection as `live_mcp`) and calls `ensure_is_member` *before* any hold or provider call. A missing credential, a non-member, or an account-less actor (including `Research crew`) is `TurnRefused`. `record_spend` does **not** re-check — tokens that moved after a successful authorize are billed; the next authorize fails closed. The credential is still the human member's **Supabase access JWT** (~1h expiry). |

That is the `0.41.0` contract: the harness is another client of the
human APIs, authenticated as a member. The Account is not the
contributor. The built-in `Actor(type=agent, display_name="Research
crew")` (`app/services/agent_actors.py`, Decision #3) is
account-less, is not a `ProjectMember`, and is deliberately `403`
on this door. The dark in-process loop (`AGENT_LOOP_ENABLED`)
attributes to that agent only *after* a commissioning human already
passed the route gate (`AgentRun.triggered_by_actor_id` +
`agent_actor_id`).

`0.51.1` was correct to refuse remapping, a schema change, or a
membership bypass. Those would have been a hole, not a feature.

`0.52.0` closed the leftover debit-path membership gap **as a
human-member check**. It is the precursor this design composes
with: the roster slice keeps the `authorize()`-before-hold
shape and swaps the principal from "JWT-resolved human member"
to "rostered agent Actor." It also inherits `0.52.0`'s known
limitation and fixes it — see §3.

### Why that contract breaks the end vision

The shipped contract is **on-behalf-of-the-operator**:

1. **Blame lies.** A validator reading
   `GET /projects/{id}/claims/{claim_id}/blame` (`0.36.0`,
   `BlameActor`) sees the human who put a JWT in a `0600` file, not
   the model/runtime that proposed the claim, ran `calc.eval`, or
   wrote the checkpoint. Intellectual credit and "who typed the
   password" are the same row. The end vision needs them apart —
   the agent produced; the human deployed.
2. **The agent cannot be a member.** `ensure_is_member` requires
   `actor.account_id` and a `ProjectMember` for that account.
   Decision #3 made the project agent account-less so it would
   *not* be a governance principal. Putting today's `Research crew`
   on the live door without a schema change is either a `403` or a
   gate bypass. There is no legal way for an agent to write.
3. **There is no roster.** `ProjectMember` is unique on
   `(project_id, account_id)` (`uq_project_member`) and its roles
   are `OWNER` / `ADMIN` (`ProjectRole`). The 0.8.1 docstring
   guessed that "an agent actor owned by an admin account later
   inherits the same edit capability through the same API". That
   guess is wrong for the end vision: choosing *which* agents to
   deploy is a per-actor, per-project decision. Account inheritance
   would let every agent owned by the owner act as the owner.
4. **One agent per project is law.** `uq_actors_one_agent_per_project`
   (migration `0013`, declared on `Actor.__table_args__`) is a
   partial unique index on `actor_metadata->>'project_id'` where
   `type = 'AGENT'`. A roster of two named agents cannot exist.
5. **Spend has no actor.** Gateway / `supervise_turn` debit is
   project-scoped. `0.52.0` now refuses a non-member *start*, but
   the debit row still has no `actor_id`. The pot is attributed
   to a funder `Account` (`FundingAllocation.account_id`); the
   contributor who burned tokens is missing. The end vision's
   "humans set the budget; agents spend it" needs the spender
   named without making the agent a funder.
6. **Accountability is implicit.** When the human JWT is the
   author, "who deployed this" is overloaded onto authorship. The
   moment authorship moves to the agent, that implicit pointer
   vanishes unless we record the sponsor separately.
7. **A long-running gateway dies with the human JWT.** `0.52.0`
   binds `authorize()` to a Supabase access token (~1h). Weeks of
   autonomous research cannot be that token's lifetime, and
   refreshing it is a human in the loop. The agent session token
   in §3 is what removes that limit.

The product failure mode of leaving this as-is: a year of
autonomous exploration that, on the ledger, looks like one human
typed every checkpoint. Validators cannot tell model from operator.
The Crew tab's "Research crew" bay assigns OpenRouter models to
roles (`project.agent_models`) but those roles are not Actors and
cannot be blamed.

---

## 2. Identity model

### What an agent is (and is not)

An agent is an `Actor` of `type=agent`. Not an `Account`. Not a
parallel data model. Same `create_checkpoint` chokepoint, same
`Contribution` / `Validation` / `FundingAllocation` separation,
same append-only guards. That rule from
`docs/blueprints/primitives.md` stays.

An `Account` remains the auth principal (Supabase `sub`, email,
`roles`, funding). A human login still owns exactly one primary
`human` Actor (`uq_actors_one_human_per_account`). An account may
own many `agent` Actors. `system` / dev-bootstrap Actors stay
account-less.

### Ownership (who deploys / sponsors)

A harness-deployed agent Actor is **owned by the deploying
Account**: `actors.account_id` is that Account. Ownership is
sponsorship, not membership and not authorship.

- The sponsor Account is the principal that holds the payment
  method and the project `OWNER` / `ADMIN` seat.
- The sponsor's primary `human` Actor is the person who clicked
  Deploy (or minted the session token).
- `FundingAllocation.account_id` stays the funder. Owning an
  agent does not fund. Deploying an agent does not mint a
  `fund` contribution.

Legacy Decision #3 rows (`Research crew`, `account_id IS NULL`)
are migrated onto the project owner's Account (see §6). New
harness agents are never minted account-less.

`system` Actors stay account-less and stay off the roster.

### How an agent becomes a member (the roster)

**Membership is not inherited from the sponsor Account.**

`ProjectMember` stays human-account governance: unique
`(project_id, account_id)`, roles `OWNER` / `ADMIN`, one owner
(`uq_project_one_owner`), invitations (`ProjectInvitation`).
`ensure_can_manage` continues to key on that table. An agent
whose `account_id` is the project owner must **not** pass
`ensure_can_manage` — otherwise Decision #3's "authored identity,
not a governance principal" collapses the moment we attach an
account.

The roster is a **new** table, `project_agent_members` (§6). One
row is "this agent Actor is deployed on this project." It is
access control, not credit — the same sentence `ProjectMember`
already uses. It never touches `Contribution` / `Validation` /
`FundingAllocation`.

`ensure_is_member` becomes type-aware:

| Acting `Actor.type` | Gate |
| --- | --- |
| `human` | unchanged: `account_id` + `ProjectMember` for that account. Account-less human → `403`. |
| `agent` | `project_agent_members` row for `(project_id, actor.id)` with `status = active`. Sponsor-account membership is **not** consulted. |
| `system` | `403` (no roster, no account). |

`ensure_can_manage` rejects `type=agent` before the account
lookup. Agents cannot invite, change roles, PATCH the project,
assign `agent_models`, or transfer ownership.

Research writes that today use `ensure_is_member` and must **not**
be agent-callable even after the gate is type-aware (funder /
contributor / validator stay separate; the orchestrator already
never self-validates):

- `POST /projects/{id}/funding` (and any `FundingAllocation` write)
- `POST /projects/{id}/validations` (and any `Validation` write)
- invitation create / accept / revoke
- member role / remove

Those routes compose with a new `ensure_is_human_member` (or an
`actor_type=human` assertion in the existing helpers). MCP
inventory does not grow a validate / fund stem.

### Role / permission scope

`ProjectRole` stays `OWNER` / `ADMIN`. Do not put `AGENT` on that
enum — those labels are governance, and `uq_project_one_owner`
is written against `role = 'OWNER'`.

Roster role is a separate enum, `ProjectAgentRole`, v1 value
`researcher` only. Meaning:

| May | Must not |
| --- | --- |
| `run_instrument`, `create_checkpoint` (**MCP / harness only** — an agent session on the human HTTP API is `403`) | `ensure_can_manage` actions |
| `list_claims`, `get_thread_context`, `get_budget` | mint `FundingAllocation` |
| debit the project pot via the session-owned gateway, once rostered and token-bound | mint `Validation` |
| | mint a session token for itself or for a human |
| | impersonate a human Actor |

`ProjectAgentRole` is `researcher` only, **deliberately, forever.**
There is no room on this enum for a later `validator` agent.
Contributor and validator stay on separate tables and separate
Actors; an agent that assessed its own checkpoints would
conflate those roles. A human member writes `Validation`. MCP
never grows a validate stem.

### Lifecycle

`project_agent_members` is mutable identity/governance (like
`ProjectMember` and `Account`) — **not** append-only. Do not
register it in `models/append_only.py`.

| Action | Who | Effect |
| --- | --- | --- |
| **Add (deploy)** | Human `OWNER` / `ADMIN` via `ensure_can_manage` | Mint (or reuse) an `Actor(type=agent)` owned by the acting account; insert roster row `status=active`, `deployed_by_account_id=acting account`, `responsible_account_id=acting account`. One transaction. Re-adding an `(project, actor)` pair is a `409`, not a second row (`uq_project_agent_member`). |
| **Suspend** | Same | `status=suspended`. In-place. Live tokens for that pair get `revoked_at` in the same transaction. Subsequent MCP writes and `authorize()` / `record_spend` identity-load refuse. Existing checkpoints, contributions, and debits are untouched. |
| **Resume** | Human `OWNER` only (`ensure_can_manage(require_owner=True)`) | Only `SUSPENDED` is resumable (what OWNER-transfer produces). `status=active`. Sets `responsible_account_id` to the acting owner's Account (who is now on the hook). Does **not** rewrite `Actor.account_id` or `deployed_by_account_id`. Does not un-revoke tokens; the owner mints a new one. `ACTIVE` → `409` already active. `REVOKED` is terminal → `409` deploy a new agent (`0.54.0` review). |
| **Revoke** | `OWNER` / `ADMIN` | `status=revoked`. Active session tokens for that `(project, actor)` get `revoked_at`. The Actor row stays (provenance). The roster row stays and remains **visible on Crew**, marked revoked. `REVOKED` is terminal — resume refuses; deploy a **new** Actor (`0.54.0` review; the unique pair still blocks a second insert of the same Actor). |
| **Mint token** | Human `OWNER` only | See §3. ADMIN may deploy / suspend / revoke; ADMIN may not mint. |
| **Rotate token** | Human `OWNER` only | Mint new, revoke old, return the new compact JWT once. Optional and explicit. |

Deleting an Actor is out of scope. `ON DELETE` on ledger FKs is
already `SET NULL`; we do not need a new delete path.

Mid-turn revoke and ownership transfer are specified under §3
and §2 "Ownership transfer."

### Relation to the existing `Research crew` Actor

**Reuse and migrate. Do not retire the row. Do not mint a second
default agent for a project that already has one.**

Decision #3's row is already the author on any dark-loop
checkpoint (`tests/agent/test_orchestrator.py` asserts
`checkpoint.author_id == agent_actor_id`). Retiring it would
orphan that provenance. Bypassing membership to "just use it on
MCP" was correctly rejected in `0.51.1`.

Migration (§6):

1. Keep the row. Set `account_id` to the project's current
   `OWNER` Account. If the project or owner is missing, leave
   `account_id` null and do **not** roster it.
2. Insert a `project_agent_members` row `(project, actor,
   deployed_by=owner, status=active, role=researcher)`.
3. Drop `uq_actors_one_agent_per_project` so a project may have
   many agents.
4. Keep a narrower partial unique index so the dark loop's
   `get_or_create_project_agent_actor` cannot fork the default
   slot: `uq_actors_one_research_crew_per_project` on
   `(actor_metadata->>'project_id') WHERE type = 'AGENT' AND
   display_name = 'Research crew'`.
5. Keep `display_name = "Research crew"` (**decided**). The
   Crew tab's existing "Research crew" bay
   (`ResearchCrewPanel`) stays the **model-assignment** surface
   for the four dark-loop roles (`project.agent_models`). The new
   bay is the **roster**. Do not collapse them — one is
   config, one is identity.

`get_or_create_project_agent_actor` keeps its flush-not-commit
discipline. After the schema slice it must (a) find the existing
Research-crew Actor, (b) ensure a roster row exists, (c) not
invent a second display-name. The dark loop still does not run
(`AGENT_LOOP_ENABLED` stays false), but **when it someday
lights it must also require a roster row** — one gate for all
agent authorship. A commissioning human passing the route is
not enough.

Named harness agents (`display_name` ≠ `"Research crew"`) are
unconstrained at the Actor-metadata index; uniqueness is the
roster `(project_id, actor_id)`.

### Project scope

An agent Actor is **project-scoped**. Deploying "DeepSeek
researcher" on project A and on project B mints two Actors. Both
may be owned by the same Account. `actor_metadata.project_id`
stays the convenience key (and the Research-crew unique index).
Cross-project use is a roster miss, not a metadata convention.

Rejected: one account-global agent Actor rostered onto many
projects. Blame would then show the same identity across
unrelated questions, and a stolen token's `sub` would be
meaningful on every project the account can reach unless every
verifier re-checks the roster (we will check anyway; scoping the
Actor still shrinks blast radius).

### Cross-project track record (definition seam)

Project-scoped Actors are the write identity. A human choosing
the roster still needs to see **one agent's history** across
projects — checkpoints authored, validations *received* (a
human validated that Actor's work), spend. That rollup is a
**read join**, not a second Actor and not a merge.

**Not in slice one. Not in v1.** Do **not** add
`actors.agent_definition_id` until the catalog slice. A
nullable column with no FK target is noise; adding a nullable
column later, in the same revision as `agent_definitions`, is
cheap. The catalog lands **after the first multi-agent
campaign** (slice G).

Future `agent_definitions` (catalog slice):

| Column | Type | Notes |
| --- | --- | --- |
| `id` | UUID PK | what `actors.agent_definition_id` will point at |
| `account_id` | UUID FK `accounts` SET NULL | the human Account that owns this *kind* of agent |
| `family_id` | UUID | stable across versions of the same kind |
| `version` | INTEGER | monotonic per `family_id` |
| `display_name` | VARCHAR(200) | catalog name ("DeepSeek researcher") |
| `config_fingerprint` | TEXT | hash of model id + harness SDK pin + Cordis inventory + persona hash |
| `config` | JSON | the fingerprint inputs, for display |
| `created_at` / `updated_at` | timestamptz | mutable catalog row (not append-only) |

Unique `(family_id, version)`. Index on `account_id`,
`family_id`.

**Rollup (read-only).**

```text
agent_definitions (family)
    └── agent_definitions (version)     -- one fingerprint
            └── actors                  -- one per project deploy
                    ├── checkpoints.author_id
                    ├── contributions.actor_id
                    └── compute_debits.actor_id
```

A Crew / catalog view for one family is `JOIN actors ON
actors.agent_definition_id IN (versions of family)` then Σ
checkpoints, incoming `Validation` rows that target those
checkpoints, and billed `ComputeDebit` (amount > 0). The
query never `UPDATE`s an Actor, never collapses two project
Actors into one UUID, and never rewrites `author_id`. Blame
on a claim still shows the **project** Actor that wrote the
checkpoint. The definition is a grouping key, not an
identity.

**Config-change semantics.**

| Change | What happens |
| --- | --- |
| Cosmetic catalog rename, notes, display copy that do **not** change `config_fingerprint` | Same definition row / same version. Existing Actors keep the pointer. |
| Model id, harness pin, Cordis inventory, or persona hash changes | **New version** of the same `family_id` (new `agent_definitions` row, `version += 1`). |
| Deploy / upgrade that new version onto a project | **New project-scoped Actor** pointing at the new version. The previous Actor on that project is revoked (visible, marked revoked), not edited, not merged. Its checkpoints stay its own. |

Same-Actor retarget (`UPDATE actors SET agent_definition_id`)
is rejected: it would make one author UUID span two
fingerprints with no snapshot on the checkpoint, and it is
the merge we just forbade in another coat. Upgrade is a new
roster slot in the same family.

Until slice G, every agent Actor has no definition pointer
and no cross-project rollup. That is honest — there is no
catalog yet. Slice G adds the table **and**
`actors.agent_definition_id` (nullable FK) together.

### Ownership transfer

`set_member_role` already transfers `OWNER` in one transaction
(demote prior owner to `ADMIN`, then promote; `ensure_can_manage`
holds the project row `FOR UPDATE`). This design adds a
composing step in that same transaction — the helper
`db.add`s and does not commit.

**Rule.** When a project's OWNER changes:

1. **Do not rewrite `Actor.account_id`.** That column is who
   originally sponsored the identity. Rewriting it on transfer
   forges provenance (the outgoing owner *did* deploy it).
2. **Do not rewrite `deployed_by_account_id`.** Same reason —
   it is "who put this row on the roster," analogous to
   `ProjectMember.invited_by_account_id`.
3. **Suspend and revoke tokens** for (a) the project's
   migrated `Research crew` Actor and (b) every roster row
   whose **`responsible_account_id`** is the outgoing owner
   (at first deploy this equals `deployed_by_account_id`;
   after a later resume it is whoever last took
   responsibility).    Agents an ADMIN deployed, and whose
   responsible account is not the outgoing owner, stay
   active (**decided**) — that ADMIN did not lose the
   project.
4. The new owner **explicitly resumes** each agent they want
   running. Resume (OWNER only) sets
   `responsible_account_id` to the new owner's Account and
   leaves `Actor.account_id` / `deployed_by_account_id`
   untouched. The new owner then mints a token (OWNER only).
   Auto-resume is rejected: choosing the roster is the new
   owner's job.

`responsible_account_id` is the live "who is on the hook
now." Using it — not `deployed_by_account_id` — as the
transfer trigger is what makes a *second* transfer correct:
after Alice deploys, Bob takes ownership and resumes, Carol
taking ownership must suspend those agents too. Keying only
on `deployed_by` would leave Bob's resumed agents running
under Carol with Alice still listed as deployer and nobody
suspended.

**In-flight turns.** Same shape as `0.52.0` mid-session
member removal and as §3 mid-turn revoke. A completion that
already passed `authorize()` may still hit the provider.
`record_spend` still writes when `tokens_used > 0` (debit
when tokens moved; do not leave the pot uncharged) and
stamps the agent `actor_id`. The matching hold release is
still amount `0`, `harness_session_turn` prefix, `hold_id`
paired. The next `authorize()` and the next MCP write load
`agent_session_tokens` by `jti`, see `revoked_at` and/or
roster `suspended`, and refuse. We do not UPDATE the hold
row. We do not kill an in-flight OpenRouter request.

Rejected variants:

- Auto-rewrite `Actor.account_id` to the new owner — the
  sponsor becomes a lie.
- Auto-resume under the new owner — the incoming owner did
  not choose the roster or the budget those agents will burn.
- Leave tokens live until expiry — a 30-day token would keep
  the outgoing owner's agents writing after they lost the
  project. Revoke is the control; expiry is the backstop.

---

## 3. Authentication

### What exists

MCP injection (`docs/harness/tools.md`, `app/harness/auth.py`):

1. Preferred: `OPENTHEORY_ACTOR_JWT_FILE` → `0600` file →
   `resolve_actor_from_bearer` → Account → primary **human** Actor.
2. Accepted: `OPENTHEORY_ACTOR_JWT` (never in Cordis `env`).
3. Local/test: `OPENTHEORY_DEV_ACTOR_ID` when
   `auth_dev_header_enabled` is on.

Gateway inbound auth is `OPENTHEORY_GATEWAY_TOKEN`. The campaign
child does not hold a member JWT. FastAPI `ActingActor` is the
same human path. A client cannot set `author_id` (`CheckpointCreate`
takes summary/content/refs; `author_id` comes from the acting
actor in `create_checkpoint`).

### Recommendation: scoped agent session token

Minted by a human **`OWNER` only**
(`ensure_can_manage(require_owner=True)`). ADMIN may deploy and
suspend; ADMIN may not mint or rotate. Bound to
**project + agent Actor + expiry + jti**. Injected through the
existing file path (`OPENTHEORY_ACTOR_JWT_FILE`). Verified by
OpenTheory, not by Supabase.

This is a second bearer *kind*, not a second injection channel.
Probe redaction (`SECRET_ENV_KEYS`, `redact`) is unchanged — the
file path may be logged; the contents must not.

#### Lifetime (30-day default; revoke is the control)

The end vision is weeks of autonomous research with no human
in the loop. A 12-hour token would force the owner to re-mint
twice a day and puts a human on the critical path. A ~1h
Supabase access JWT is worse — that is the `0.52.0` gateway
limitation this token removes.

| Rule | Value |
| --- | --- |
| Default `expires_at` | **30 days** from mint |
| Max TTL | Configurable via settings / env (`OPENTHEORY_AGENT_SESSION_MAX_TTL_SECONDS`, default `2592000`). **Not** in `fly.toml [env]`. A mint may request shorter, never longer. |
| Control | **Revoke**, not expiry. Every MCP write, every `authorize()`, and every `record_spend()` loads `agent_session_tokens` by `jti` and checks `revoked_at IS NULL` plus roster `status = active` in the DB. Expiry (`expires_at > now()`) is a backstop for a row nobody revoked. |
| Token revoke | `POST …/tokens/{jti}/revoke` (OWNER). Takes effect on the **next** MCP write / `authorize()`. |
| Roster suspend / revoke | Sets `revoked_at` on every live token for that `(project, actor)` in the same transaction. Same next-call effect. |
| Rotate | Optional, OWNER-only, explicit: mint new, revoke old, return the new compact JWT once. The operator replaces the `0600` file. |
| Self-renew | **Forbidden.** The agent has no mint / rotate / refresh stem. A stolen agent token cannot extend itself. |

`record_spend` loads the same `jti` row so spend is stamped
with the agent and so a revoked token is visible. It does
**not** refuse a debit when `tokens_used > 0` after this
turn's `authorize()` already passed — that is the `0.52.0`
mid-turn rule (do not leave the pot uncharged). The refuse
lands on the next `authorize()` / MCP write.

#### Why this also fixes `0.52.0`

`0.52.0` (PR #48) correctly put `ensure_is_member` on
`HarnessSession.authorize()` using the JWT-resolved **human**
member. The gateway child's member credential is a Supabase
access JWT (~1h expiry). A long-running campaign child would
start refusing after that hour even though the human is still
a member — there is no refresh in the child, and building one
would put a human session in a weeks-long process. The roster
slice **swaps that gate** from "human `ProjectMember`" to
"rostered agent + agent session token." The 30-day,
DB-revocable token is what makes the long run possible
without a human in the loop.

#### Token payload (OT-issued JWT)

```text
iss = "opentheory"
aud = "harness"
typ = "agent_session"          # literal; never "human"
sub = <agent actor UUID>
proj = <project UUID>
jti = <agent_session_tokens.id>
mby = <minted_by_account UUID>
mba = <minted_by_human_actor UUID>
iat, exp
```

Signed with a new server secret `AGENT_SESSION_JWT_SECRET` (or
`settings.agent_session_jwt_secret`). **Not** the Supabase JWT
secret. **Not** in `fly.toml [env]`. Hash of the compact JWT
(SHA-256) is stored on `agent_session_tokens.token_hash`; the
bearer is shown once at mint and then only exists in the `0600`
file.

Resolver algorithm, order matters. **HTTP `ActingActor` /
`resolve_actor_from_bearer` refuse `typ=agent_session`**
(`403` "agent sessions are only valid on the harness") and
never fall through to the Supabase verifier. Acceptance is
**only** `resolve_mcp_actor` / `authorize()`:

1. Read the bearer (file / env — not the Console
   `Authorization` header).
2. If it verifies as `typ=agent_session` with our secret: load
   `agent_session_tokens` by `jti`, require
   `revoked_at IS NULL`, `expires_at > now()`,
   `token_hash` matches, `actor_id = sub`, `project_id = proj`,
   actor `type=agent`, roster `status=active` for that pair.
   A bound `proj` that differs from the requested project is
   `403` (defense in depth on `ensure_is_member`).
   Return **that agent Actor**. Never the minting human.
3. Else existing Supabase / dev-id path. That path returns a
   **human** (or a flagged dev Actor). It must refuse a token
   whose `typ` is `agent_session` even if someone copies the
   bytes into the Supabase verifier — the issuers differ.

A human Supabase JWT **cannot** carry an agent claim we honor.
`author_id` stays "the resolved Actor", never a client field.

Gateway / `HarnessSession`: bind `actor_id` at session start from
the same file (new env name `OPENTHEORY_AGENT_JWT_FILE` may alias
the same path; do not put the bearer on a tool argument).
`authorize()` and `record_spend()` load the token by `jti`,
require roster `active` and `revoked_at IS NULL`, and refuse a
*start* when the token is revoked or the bound `project_id` ≠
`OPENTHEORY_PROJECT_ID`. This **replaces** the `0.52.0` human
`ensure_is_member` call on `authorize()` — same fail-closed
shape, different principal. `OPENTHEORY_GATEWAY_TOKEN` remains
the HTTP process secret; it is no longer sufficient by itself
to debit once this slice is on. Unbound / unmetered probe
(`OPENTHEORY_HARNESS_UNMETERED_PROBE`) is unchanged and still
not the campaign composition.

`write_daily_cap_adjustment` and `record_compute_debit` stay in
`app.services` / `app.harness.session`. FastAPI continues to read
the meter through `app.services.harness_meter` — no
`app.harness` import.

Dev: `OPENTHEORY_DEV_ACTOR_ID` may name a rostered agent when the
flag is on. Production flag-off remains `401`. Tests that today
assert account-less Research crew is `403` stay; a new test
rosters it and expects the agent as author.

### Rejected auth alternative: JWT on-behalf-of with an agent claim

A Supabase human JWT plus `act` / `on_behalf_of` / custom claim
naming the agent.

Why reject:

- The MCP child then holds a credential that is also a valid
  human login. Theft is theft of the operator, not of one
  deployment.
- `resolve_actor_from_bearer` today *drops* unknown claims and
  returns the primary human. A forgotten code path authors as the
  human again (silent regression to today's lie) or, worse,
  honors a client-supplied claim without a roster check
  (confused deputy).
- Revoke-one-agent means waiting for the human JWT to expire, or
  building a second revoke list anyway — at which point we have
  invented the session table without isolating the secret.
- The human can set the claim to any agent they can name. That
  *is* impersonation unless mint is a server-side row, which is
  the token table.

### Threat model

| Threat | Mitigation |
| --- | --- |
| **Token theft** | `0600` file; never on `tools/call` args; `redact` unchanged; hash-at-rest; `jti` revoke; no self-renew. Blast radius is **one project + one agent until the owner revokes** (or suspends / revokes the roster row, or rotates). Expiry (default 30 days, max via settings) is a backstop, not the kill switch — every MCP write and every `authorize()` re-reads `revoked_at` + roster status. Detection is the Crew / Overview **spend-by-agent** readout (`ComputeDebit.actor_id`): unexpected tokens on that agent is the signal to revoke. |
| **Cross-project use** | `proj` claim + roster row + `HarnessSession.project_id` must agree. A token for A presented on B is `401`/`403` before a write or a debit. Actor is project-scoped, so `sub` is meaningless on B even before the roster check. |
| **An agent minting as a human** | Only the project **OWNER** mints or rotates. Agent routes cannot call the mint service. Resolver never returns a `human` Actor from `typ=agent_session`. `CheckpointCreate` has no `author_id`. |
| **A human impersonating an agent** | A human JWT resolves to the primary human. There is no `X-On-Behalf-Of` and no client `author_id`. A human who wants work credited to an agent deploys it and mints a token — the agent, not the human, then authors. A human running instruments themselves is still the author (correct). |
| **Revoked / suspended agent mid-turn** | Every MCP write re-resolves (roster + `revoked_at`). `authorize()` re-checks before the model. An in-flight completion that already passed `authorize()` may still hit the provider (tokens may move). `record_spend` **still writes** when `tokens_used > 0` — debit-when-tokens-moved is load-bearing — with `actor_id` set. The matching hold release is still amount `0`, notes prefix `harness_session_turn`, `hold_id` paired. The next `authorize()` and the next MCP write refuse. We do not UPDATE the hold row. |
| **Gateway token without agent identity** | After the spend slice: `authorize()` / `record_spend()` without a resolvable rostered agent refuse. Today's "outsider `actor_env` still debits" pin is **deliberately inverted** for the new path. The process still holds DB credentials; membership is now a domain check on that path, not only on MCP. |
| **Secret confusion** | Agent-session secret ≠ Supabase JWT secret ≠ `OPENTHEORY_GATEWAY_TOKEN` ≠ `OPENROUTER_API_KEY`. None in `fly.toml [env]`. |
| **Replay of a leaked compact JWT after rotate** | Hash match + `jti`. Rotate = revoke row + new mint. Old bytes fail hash or `revoked_at`. |

Hold TTL, remaining-room occupancy, turn-room clamp, and
"unfunded is not exhausted" are unchanged. A revoke does not
rewrite today's `harness_session_turn` sum.

---

## 4. Attribution

### Who authored the work

On a write that resolved an agent Actor:

- `Checkpoint.author_id` = agent Actor id
- `Contribution.actor_id` = agent Actor id
- `create_checkpoint` remains the only Checkpoint writer. MCP
  handlers do not mint. `run_instrument` still composes with the
  chokepoint.

On a write that resolved a human Actor (Console, human JWT on
MCP, flagged dev human): unchanged. `sponsored_by_actor_id` is
null — the author *is* the accountable human.

### Who deployed / sponsored, without stealing credit

Two records, two jobs:

1. **Governance (mutable):**
   `project_agent_members.deployed_by_account_id` — who put the
   agent on the roster. Analogous to
   `ProjectMember.invited_by_account_id`.
2. **Ledger snapshot (append-only, new column):**
   `checkpoints.sponsored_by_actor_id` (nullable FK `actors`,
   `ON DELETE SET NULL`) — the human Actor who minted the
   session token that authorized this write. Trusted service
   argument to `create_checkpoint`, never a client field.
   Copied from `agent_session_tokens.minted_by_actor_id` at
   resolve time.

Do **not** write a second `Contribution` for the sponsor. That
would give the deployer intellectual credit for the agent's
claim — the funder/contributor conflation in another coat.
`Contribution` stays "who did the work."

Do **not** put the sponsor Account on the checkpoint. Research
provenance stays on `Actor`. The Account is reachable via
`Actor.account_id` when a UI needs a handle.

Precedent: `AgentRun` already splits `triggered_by_actor_id`
(commissioning human) from `agent_actor_id` (author). Harness
has no `AgentRun` and this proposal does not add one — the
session owner stays `HarnessSession` + the ledger. The
checkpoint column is the harness equivalent of that split, on
the primitive validators already read.

Historical MCP writes authored by a human JWT stay as they are.
We do not UPDATE `author_id` (append-only). We do not invent a
sponsor for them (`sponsored_by_actor_id` stays null). The
`0.51.1` rows remain "human ran the door."

### What validators see

`BlameActor` already has `id`, `display_name`, `type`. After
this change a harness-landed step shows `type=agent` and the
agent's display name. Add optional `sponsor: BlameActor | None`
on `BlameStep` (and the matching field on `CheckpointRead` /
`ActorSummary` consumers that show a single commit).

- Author = who produced.
- Sponsor = who deployed the session.
- Validator = whoever wrote the `Validation` row (a human
  member; there is no agent validator role).
- Funder = `FundingAllocation.account_id`, unchanged.

Overview / Crew can join roster + sponsor + Σ `ComputeDebit`
where `actor_id` matches, without minting anything.

---

## 5. Spend

### `ComputeDebit.actor_id`

Add nullable `actor_id UUID REFERENCES actors(id) ON DELETE SET NULL`.
Index `ix_compute_debits_actor_id`. Do **not** make it NOT NULL
— historical rows and hold/release rows that predate the column
have no honest actor.

`record_compute_debit` grows `actor_id: UUID | None = None`.
`write_daily_cap_adjustment` grows the same. Hold/release rows
remain `amount = 0`, `rate_per_1k = 0`, notes starting with the
literal `harness_session_turn` prefix, `hold_id=` pairing
(`hold_notes` / `RELEASE_NOTES` in `app/services/harness_meter.py`).
Do not change the prefix, the marks (`daily_cap_hold`,
`daily_cap_release`), or the occupancy rule (hold occupies the
whole remaining daily room). Putting `actor_id` on a hold is
allowed and useful for ops; it is not pot spend.

Debit only when `tokens_used > 0` for billed spend. Hold/release
are the existing amount-0 exception and stay that.

`FundingAllocation` is not read or written on this path. The
agent is a contributor. Native funding stays `internal` +
human. Unfunded is not exhausted (`project_budget.funded == 0`
is not `available <= 0`).

### Backfill

| Existing row | `actor_id` after backfill |
| --- | --- |
| `agent_run_id IS NOT NULL` and that `AgentRun.agent_actor_id` is set | that agent (dark-loop spend; honest) |
| `agent_run_id IS NOT NULL` but `agent_actor_id` is null | null (pass failed before resolve) |
| `notes` like `harness_session_turn%` (spend, hold, release) | **null** — we do not invent an agent for pre-identity gateway rows |
| anything else | null |

No `UPDATE` of `amount`, `tokens_used`, or `notes`. Reversible:
`UPDATE compute_debits SET actor_id = NULL` then drop the
column.

### Membership on `authorize` / `record_spend`

This **replaces** the `0.52.0` human `ensure_is_member` call.
Same place (`authorize()` before any hold or provider call),
different principal (rostered agent + agent session token).
Both `authorize()` and `record_spend()` load `agent_session_tokens`
by `jti` and read roster status:

1. Resolve the bound agent (agent token / flagged dev id).
2. Require roster `active` on `HarnessSession.project_id` and
   `revoked_at IS NULL`.
3. Then existing composition / turn-cap / daily-cap / pot /
   floor / hold lock.

A missing or revoked identity refuses **before** the model and
writes nothing. A completion that spent tokens after a mid-turn
revoke still records the debit (§3 / `0.52.0` mid-turn rule).

`supervise_turn`'s outsider-`actor_env`-still-debits pin is
replaced: `actor_env` must resolve to the bound rostered agent
(or the session's bound actor is used and `actor_env` cannot
override it). Pick one in implementation and test both; this
doc's default is **session bind wins, `actor_env` cannot
override**. That closes the confused-deputy hole the audit
documented as "not a provenance hole" — it becomes one the
moment spend carries an `actor_id`.

### Per-agent budget caps vs the project pot

**The project pot remains the only money.**
`FundingAllocation` stays funder-only. `project_budget.spent` is
still Σ `ComputeDebit.amount` (holds are 0). Concurrent
occupancy and the daily token cap stay **project-scoped**
(`harness_session_turn` prefix, one remaining-room hold, second
overlapping authorize refused). **Decided: one shared project
daily cap. No per-agent split** — splitting would re-open the
race `0.47`–`0.51` closed.

Optional per-agent ceilings live on the roster row, not on
funding:

- `token_budget_cap INT NULL` — additional refuse-before-model
  when this agent's Σ `tokens_used` on billed
  `harness_session_turn` spend (amount > 0, this `actor_id`)
  has reached the cap. Null = no per-agent token ceiling.
- `usd_budget_cap NUMERIC(12,6) NULL` — same against Σ
  `amount`. Null = none.

v1 **stores** the columns. Enforcement is a **later** slice
(§9 slice F), so identity + the `0.52.0` gate-swap do not
change daily-cap occupancy math in the same release. Default
null means "project pot + project daily cap only," which is
today's shape plus an actor stamp. Slice F enforces and
exposes the caps on Crew.

Rejected: a `FundingAllocation` per agent, a reserved slice
carved out of the pot as a second funding row, or treating an
agent cap of 0 as "exhausted" on an unfunded project.

### Built-in loop

`AGENT_LOOP_ENABLED` stays false. When a future slice lights it,
the dark loop **must require a roster row** for the agent
Actor it authors as — one gate for all agent authorship, same
as the harness. A commissioning human passing the HTTP route
is not enough. `record_compute_debit` should pass
`actor_id=AgentRun.agent_actor_id` so the column is honest on
both planners. That is not this proposal's enablement.

---

## 6. Schema

Slice one's exact inventory (enums, tables, columns, indexes,
data migrations vs later) is listed in §9. Head revision
today is `0021_concurrent_campaign_cycles`. The
implementation slice that first touches schema is the next
Alembic revision (likely `0022`). `create_all` and Alembic stay
in lockstep: every new constraint is declared on the model
`__table_args__` **and** in the migration (0006 / 0013
discipline). New models are exported from
`app/models/__init__.py` so `env.py`'s `from app.models import *`
sees them.

Enums use `StrEnum` member **names** as Postgres labels
(`'ACTIVE'`, `'RESEARCHER'`, `'HUMAN'`).

### 6.1 New enum types

```text
project_agent_role
  RESEARCHER

project_agent_status
  ACTIVE
  SUSPENDED
  REVOKED
```

No change to `project_role`, `actor_type`, `funding_*`,
`compute_debit_*`.

### 6.2 New table `project_agent_members`

Mutable. Not append-only.

| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| `id` | UUID PK | no | `IdMixin` |
| `project_id` | UUID FK `projects.id` ON DELETE CASCADE | no | indexed |
| `actor_id` | UUID FK `actors.id` ON DELETE CASCADE | no | indexed; service requires `actors.type = 'AGENT'` |
| `deployed_by_account_id` | UUID FK `accounts.id` ON DELETE SET NULL | yes | who put it on the roster (historical; never rewritten on transfer) |
| `responsible_account_id` | UUID FK `accounts.id` ON DELETE SET NULL | yes | who is on the hook now; equals deployer at insert; set to the new OWNER on resume |
| `role` | `project_agent_role` | no | `RESEARCHER` only; no validator value, ever |
| `status` | `project_agent_status` | no | default `ACTIVE` |
| `token_budget_cap` | INTEGER | yes | null = no per-agent token cap |
| `usd_budget_cap` | NUMERIC(12,6) | yes | null = no per-agent USD cap |
| `created_at` / `updated_at` | timestamptz | no | `TimestampMixin` |

Constraints / indexes:

- `uq_project_agent_member` UNIQUE `(project_id, actor_id)`
- `ix_project_agent_members_project_status` on
  `(project_id, status)`
- `ix_project_agent_members_actor_id` on `(actor_id)` (the FK
  index is enough if named)
- `ix_project_agent_members_responsible` on
  `(project_id, responsible_account_id)` (OWNER-transfer
  lookup)

No unique on `(project_id, deployed_by_account_id)` — one
account deploys many agents.

### 6.3 New table `agent_session_tokens`

Mutable (revoke in place). Not append-only. Not a ledger
primitive.

| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| `id` | UUID PK | no | also JWT `jti` |
| `project_id` | UUID FK `projects.id` ON DELETE CASCADE | no | |
| `actor_id` | UUID FK `actors.id` ON DELETE CASCADE | no | agent |
| `minted_by_account_id` | UUID FK `accounts.id` ON DELETE SET NULL | yes | |
| `minted_by_actor_id` | UUID FK `actors.id` ON DELETE SET NULL | yes | human Actor who minted |
| `token_hash` | BYTEA | no | SHA-256 of compact JWT; unique |
| `expires_at` | timestamptz | no | default mint = now + 30 days; capped by settings max TTL |
| `revoked_at` | timestamptz | yes | null = live; the control (expiry is the backstop) |
| `last_used_at` | timestamptz | yes | optional; not load-bearing |
| `created_at` / `updated_at` | timestamptz | no | |

Constraints / indexes:

- `uq_agent_session_tokens_hash` UNIQUE `(token_hash)`
- `ix_agent_session_tokens_lookup` on
  `(actor_id, project_id, revoked_at, expires_at)`
- `ix_agent_session_tokens_project_id` on `(project_id)`

### 6.4 Column adds

**`checkpoints.sponsored_by_actor_id`**

- UUID, nullable, FK `actors.id` ON DELETE SET NULL
- Index `ix_checkpoints_sponsored_by_actor_id`
- Append-only table: `ADD COLUMN` only. No backfill that
  rewrites `author_id`. Existing rows stay `NULL`.
- ORM `before_update` still forbids later edits; the column is
  set at INSERT by `create_checkpoint`.

**`compute_debits.actor_id`**

- UUID, nullable, FK `actors.id` ON DELETE SET NULL
- Index `ix_compute_debits_actor_id`
- Append-only table: `ADD COLUMN` + a one-shot Core `UPDATE`
  for the AgentRun backfill in the same migration (bulk Core
  bypasses ORM guards by design; that is the documented caveat
  in `models/append_only.py`). Do not ORM-update debit rows.

**Not in slice one:** `actors.agent_definition_id`. Lands
with `agent_definitions` in slice G.

### 6.5 Index surgery on `actors`

Drop:

```text
uq_actors_one_agent_per_project
  UNIQUE (actor_metadata ->> 'project_id')
  WHERE type = 'AGENT'
```

Create:

```text
uq_actors_one_research_crew_per_project
  UNIQUE (actor_metadata ->> 'project_id')
  WHERE type = 'AGENT' AND display_name = 'Research crew'
```

Keep `uq_actors_one_human_per_account`. `account_id` stays
nullable (system / unmigrated orphans).

Service-level (not a CHECK across tables): new agents minted by
the deploy helper require `account_id IS NOT NULL` and
`actor_metadata.project_id = roster.project_id`.

### 6.6 What we do not add

- No `accounts` row per agent.
- No `actor_id` on `project_members` (see §8).
- No `Contribution.sponsored_by_actor_id` (redundant with the
  checkpoint; would tempt a second credit row).
- No `FundingAllocation` change.
- No `AgentRun` on the harness path.
- No refusals table.
- No campaign table.
- No `agent_definitions` table and no
  `actors.agent_definition_id` until slice G.
- No `ProjectAgentRole.validator`.

### 6.7 Migration + backfill plan (reversible, live-safe)

Supabase Postgres. Additive first. Avoid long exclusive locks
on `checkpoints` / `compute_debits` (those are the large
append-only tables).

**Upgrade (one revision, several steps, each lock-friendly):**

1. `CREATE TYPE` the two enums (`checkfirst`).
2. `CREATE TABLE project_agent_members` + constraints.
3. `CREATE TABLE agent_session_tokens` + constraints.
4. `ADD COLUMN` `checkpoints.sponsored_by_actor_id` NULL + FK
   + index. PG 11+ additive nullable column is metadata-only.
5. `ADD COLUMN` `compute_debits.actor_id` NULL + FK + index.
6. Backfill Research crew (set-based, no row loop in Python if
   it can be avoided):

   ```sql
   UPDATE actors AS a
   SET account_id = pm.account_id
   FROM project_members pm
   WHERE a.type = 'AGENT'
     AND a.display_name = 'Research crew'
     AND a.account_id IS NULL
     AND pm.project_id = (a.actor_metadata->>'project_id')::uuid
     AND pm.role = 'OWNER';
   ```

   Then insert roster rows for those actors (INSERT…SELECT
   from actors ⨝ projects, skip if project id missing or
   invalid UUID). Set `deployed_by_account_id` **and**
   `responsible_account_id` to the owner Account.
   `ON CONFLICT DO NOTHING` on `uq_project_agent_member`.
7. Backfill debit actors from the dark loop:

   ```sql
   UPDATE compute_debits AS d
   SET actor_id = r.agent_actor_id
   FROM agent_runs r
   WHERE d.agent_run_id = r.id
     AND d.actor_id IS NULL
     AND r.agent_actor_id IS NOT NULL;
   ```

   Leave all `harness_session_turn` rows null.
8. `DROP INDEX uq_actors_one_agent_per_project`.
9. `CREATE UNIQUE INDEX uq_actors_one_research_crew_per_project …`.
   If two Research-crew rows already share a project_id
   (should be impossible under the old index), the create
   fails closed — fix data before retry; do not DISTINCT-on
   guess.

Steps 1–5 are rollback-safe by drop. Steps 6–7 are
reconstructible (crew account_id from owner; debit actor from
`agent_runs`). Steps 8–9 are the only structural tightening;
downgrade recreates the old index only if the new multi-agent
rows are gone (downgrade **refuses** if a project has two
`type=agent` actors — fail closed rather than silently
deleting).

**Downgrade:**

1. Refuse if `COUNT(*) > 1` agents sharing a
   `actor_metadata.project_id`.
2. Drop `uq_actors_one_research_crew_per_project`; recreate
   `uq_actors_one_agent_per_project`.
3. `UPDATE compute_debits SET actor_id = NULL`.
4. Drop column `compute_debits.actor_id`.
5. Drop column `checkpoints.sponsored_by_actor_id`.
6. Drop `agent_session_tokens`, `project_agent_members`, enums.
7. Optionally `UPDATE actors SET account_id = NULL WHERE type =
   'AGENT' AND display_name = 'Research crew'` to restore
   Decision #3 account-lessness.

No ORM `UPDATE` of `Checkpoint` / `ComputeDebit` / `Contribution`
/ `Validation` / `FundingAllocation` / `Tag` after insert, except
the one-shot Core backfill of the new nullable debit column.

**Live safety:** run in a low-traffic window if `compute_debits`
is large; the AgentRun backfill is indexed on `agent_run_id`
(`uq_compute_debits_one_per_agent_run` / `ix_…`). The crew
UPDATE touches few rows (one agent per project that ever ran a
pass). Concurrent writes keep working: new checkpoints insert
without a sponsor; new harness debits insert without `actor_id`
until the service slice deploys. **Schema-on, behavior-off** is
the first release slice.

---

## 7. API, MCP, UI, read paths

### 7.1 Product API (FastAPI, not `app.harness`)

All writes: `ActingActor` then `ensure_can_manage` (deploy /
suspend / revoke) or `ensure_can_manage(require_owner=True)`
(mint / rotate / resume) or the type-aware `ensure_is_member`
(research). Dark behind the existing auth; no Fly flag.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/projects/{id}/agents` | Roster list (id, display_name, status, role, deployed_by handle, responsible handle, caps, created_at). **Members only** (`ensure_is_member`). Includes revoked rows, marked revoked. Never email, never token hash. |
| `POST` | `/projects/{id}/agents` | Deploy (`OWNER` / `ADMIN`). Body: `display_name`, optional caps, optional `reuse_research_crew: true` to roster the migrated default without minting. 409 on unique conflict. |
| `PATCH` | `/projects/{id}/agents/{actor_id}` | Suspend / revoke (`OWNER` / `ADMIN`); resume (`OWNER` only — sets `responsible_account_id`). Revoke / suspend fans out `revoked_at` on live tokens in the same transaction. |
| `POST` | `/projects/{id}/agents/{actor_id}/tokens` | **OWNER only.** Mint. Default `expires_at` = now + 30 days, capped by settings max TTL. Optional `ttl_seconds` shorter than the max. Returns the compact JWT **once** + `expires_at` + `jti`. 403 if roster not `active`. |
| `POST` | `/projects/{id}/agents/{actor_id}/tokens/{jti}/rotate` | **OWNER only.** Mint new, revoke old, return the new compact JWT once. |
| `POST` | `/projects/{id}/agents/{actor_id}/tokens/{jti}/revoke` | **OWNER only.** Revoke one token. Takes effect on the next MCP write / `authorize()`. |

No `author_id` on `CheckpointCreate`. `create_checkpoint` grows
an optional trusted `sponsored_by` argument from the resolver,
not from the payload.

`GET /me` stays the human Account + primary human Actor.

### 7.2 MCP / harness

- Stems unchanged: `run_instrument`, `create_checkpoint`,
  `list_claims`, `get_thread_context`, `get_budget`,
  `echo_nonce`. No validate / fund / mint-token stem.
- `resolve_mcp_actor` learns the agent-session kind (§3).
- `_run_instrument` / `_create_checkpoint` keep
  `ensure_is_member` then the chokepoint; the actor they pass
  is now the agent when the file holds an agent token.
- Composition pin `0.1.5rc1` unchanged. `verify()` still
  rejects an unmetered gateway child.
- `HarnessSession` stores `actor_id`. `authorize` /
  `record_spend` load `agent_session_tokens` by `jti` (this
  **replaces** the `0.52.0` human `ensure_is_member` on
  `authorize()`). `write_daily_cap_adjustment` passes
  `actor_id` through. Notes prefix and `hold_id` format
  unchanged.
- `OPENTHEORY_ACTOR_JWT_FILE` holds the **agent** session
  token on the production campaign + MCP children, not the
  operator's Supabase JWT (that ~1h token is the `0.52.0`
  limitation this removes).

### 7.3 UI — Crew tab only

`PROJECT_TAB_IDS` stays
`research | instruments | crew | funding | overview`.

Crew today (`project-workspace.tsx`): two-column grid,
`ResearchCrewPanel` (role → OpenRouter model) +
`Collaborators` (human members / invitations). Add a **Deployed
agents** bay on that tab — same page, no new route, no sixth
tab. Natural place: full-width above the two-column grid, or a
third bay under Research crew (identity next to model config).

The bay shows the full roster including **revoked** agents
(marked revoked — not filtered out), status, responsible
handle, optional spend Σ, and Deploy / Suspend / Revoke
(`OWNER` / `ADMIN`) plus Mint / Rotate token (`OWNER` only,
one-time reveal). Token bytes are not persisted in React
query cache beyond the reveal. Spend-by-agent on this bay
and on Overview is the theft-detection readout.

Research-tab `BlamePanel` and Overview ops bay consume the
read-model changes below. Instruments tab does not grow a
roster; a pass still commissions a dark-loop role, and that
path stays 404 while `AGENT_LOOP_ENABLED` is false.

### 7.4 Read paths that change

**Blame** (`app/services/blame.py`, `BlameStep`):

- `author` becomes the agent on new harness writes
  (`BlameActor.type = agent`).
- Add `sponsor: BlameActor | None`.
- Do not invent a sponsor for historical human-authored
  harness checkpoints.
- `BlameAgentRun` stays the dark-loop join; harness writes
  still have no `AgentRun`.

**Checkpoint timeline / `ActorSummary`:** include `type` (already
present) so the Console can mark agent commits. Add sponsor id
+ display name on `CheckpointRead` when set.

**Overview ops** (`GET /projects/{id}/ops`,
`app/services/ops.py` + `harness_meter.py`):

- `OpsTurnRead` / last-turn grow optional `actor_id`,
  `actor_display_name`, `actor_type`. Null on pre-identity
  rows — unknown stays unknown. Overview can group billed
  spend by `actor_id` (the Crew / Overview theft-detection
  readout).
- Meter math unchanged: prefix `harness_session_turn`, holds
  included, `hold_id` pairing. FastAPI still does not import
  `app.harness`.
- Refusals still unlisted (a refused start writes nothing).

**Crew badge:** today counts human members + invitations. May
add roster `active` count in the UI slice; not a new tab badge
kind.

---

## 8. Options considered

### Recommendation (in one paragraph)

Give each deployed agent its own `Actor(type=agent)` owned by
the deploying Account; put that Actor on a **separate roster
table**; authenticate the harness with a **scoped agent session
token** (OWNER-minted, 30-day default, instantly revocable,
no self-renew) that **replaces** the `0.52.0` human-JWT gate
on `authorize()`; attribute `author_id` /
`Contribution.actor_id` to the agent and snapshot the minting
human on `checkpoints.sponsored_by_actor_id`; stamp nullable
`ComputeDebit.actor_id` the same way; keep money on
`FundingAllocation` + the project pot. Leave
`Actor.account_id` / `deployed_by` alone on OWNER transfer;
suspend outgoing-responsible agents and revoke their tokens
until the new owner resumes (`responsible_account_id`).
Project-scoped Actors; definition catalog (table + column
together) after the first multi-agent campaign. Reuse and
migrate `Research crew` (keep the display name). No validator
agent role.

That is the smallest change that makes the end vision true
without punching a hole in membership, without making Account
an Actor, and without letting an agent fund or self-validate.

### Tradeoffs of the recommendation

- Two membership tables instead of one. The alternative
  (overloading `ProjectMember`) looks smaller and is the
  larger bug (§8 rejected #3).
- A second JWT issuer. Operational cost (new secret, rotate,
  hash-at-rest) against a much smaller blast radius than
  stuffing agent claims into the human Supabase JWT.
- Nullable debit `actor_id` means ops must show "unknown" for
  every pre-identity harness turn. Honest; not pretty.
- Project-scoped Actors mean the same "kind" of agent is a
  different UUID per project. Blame stays readable; the
  later definition catalog is how a human sees history
  across projects without merging those UUIDs.
- A 30-day token is a longer-lived secret than 12h. Revoke
  on next DB read is the kill switch; Crew / Overview
  spend-by-agent is the detection. That is the trade
  against putting a human in the loop twice a day.
- `ensure_is_member` becomes type-aware. Every caller must
  keep using it; a missed `ensure_is_human_member` on
  validation/funding is a regression we test.

### Rejected alternatives

1. **Credit MCP writes to `Research crew` by bypassing
   `ensure_is_member`.** The `0.51.1` finding. The agent is
   not a member; this is a side door. Ledger authorship would
   be right for one identity and wrong for a roster, and any
   account-less Actor could be smuggled through.

2. **Credit MCP writes to `Research crew` by setting
   `account_id` and relying on account inheritance.**
   `ensure_is_member` would pass because the owner is a
   `ProjectMember`. `ensure_can_manage` would also pass unless
   we special-case type — the agent would be the owner. One
   agent per project stays. No revoke-one-agent. The 0.8.1
   docstring's guess, explicitly overturned.

3. **Put agents on `project_members` with nullable `actor_id`
   XOR `account_id`.** Breaks `uq_project_member`,
   invitations (account-keyed), `uq_project_one_owner`,
   `list_members` (AccountSummary), and `ProjectRole`. Agents
   would need a fake Account or a fake OWNER/ADMIN. Parallel
   model inside the human table.

4. **One service `Account` per agent.** Account is the login
   principal and the funder. An agent Account could be
   invited as ADMIN, could receive `FundingAllocation`, and
   would JIT-provision a primary *human* Actor on first
   "login" (`_resolve_or_provision`). That is Account = Actor.

5. **Supabase JWT on-behalf-of / agent claim.** §3. Theft is
   the operator. Default resolver authors as the human.
   Revoke is the human session.

6. **`X-On-Behalf-Of: <agent id>` on a human JWT.** Client-
   supplied authorship. A member can frame any rostered
   (or, if unchecked, any) agent. `CheckpointCreate` growing
   `author_id` is the same bug.

7. **Reuse `AgentRun` as the harness session.** Different
   owner (`HarnessSession`), no thread at gateway time, no
   plan/steps JSON, and `0.42`–`0.51` spent a lot of ink on
   *not* adding an `AgentRun` or a campaign table. The
   sponsor snapshot belongs on `Checkpoint`, which validators
   already read.

8. **Second `Contribution` for the sponsor (action
   `commission`).** Looks like credit. Funder/contributor
   conflation. Notes-as-provenance.

9. **Per-agent `FundingAllocation` or carving the pot into
   reserved funding rows.** The agent becomes a funder.
   `unfunded` vs exhausted gets a third state. Hold/release
   semantics would have to split by actor and would re-open
   the overlapping-authorize race.

10. **Keep `uq_actors_one_agent_per_project` and treat
    "roster" as four roles on one Actor.** That is today's
    `project.agent_models`. Roles are not identities; they
    cannot be suspended independently; Blame cannot say
    which model/runtime produced a claim once two harnesses
    run.

11. **Schema-only `ComputeDebit.actor_id` without membership
    on `authorize`.** Spend would name an actor the gateway
    never proved. The outsider-`actor_env` pin would become
    a forged-attribution hole.

12. **Rewrite historical harness `author_id` from human to
    agent.** Append-only forbids it, and it would be a lie
    (those writes *were* the human JWT). Corrections are new
    rows.

13. **12-hour token, no renew.** Forces a human to re-mint
    twice a day and recreates the `0.52.0` ~1h JWT problem
    at a slightly longer interval. Revoke-on-next-read with
    a 30-day backstop is what the end vision needs.

14. **Merge project Actors that share a definition into one
    UUID.** The definition seam is a read join. Merging
    would make Blame show the same author on unrelated
    questions and would enlarge a stolen token's `sub`.

---

## 9. Phased rollout, tests, decided questions

Each slice stays small, deployable, and **dark**: no Fly
enablement, `AGENT_LOOP_ENABLED` default `false`, FastAPI does
not import `app.harness`, five tabs. Version numbers below are
placeholders after `0.52.0`; the owner assigns them when a
slice is scheduled. This file is the approved design, not a
release.

**Precursor (already shipped):** `0.52.0` (PR #48) — human
`ensure_is_member` on `HarnessSession.authorize()`;
`record_spend` does not re-check; no schema. The roster
slices below **swap** that gate; they do not invent a second
one.

### Slice one (schema) — exact inventory

Schema-on, behavior-off. Models + `__init__.py` exports.
`create_all` lockstep with Alembic. No resolver change, no
MCP behavior change, no UI, no Fly, no `AGENT_LOOP_ENABLED`.

**Enums (new):**

- `project_agent_role` — `RESEARCHER` only
- `project_agent_status` — `ACTIVE`, `SUSPENDED`, `REVOKED`

**Tables (new):**

- `project_agent_members` — `id`, `project_id`, `actor_id`,
  `deployed_by_account_id`, `responsible_account_id`, `role`,
  `status`, `token_budget_cap` (nullable; stored, not
  enforced), `usd_budget_cap` (nullable; stored, not
  enforced), `created_at`, `updated_at`
- `agent_session_tokens` — `id` (`jti`), `project_id`,
  `actor_id`, `minted_by_account_id`, `minted_by_actor_id`,
  `token_hash`, `expires_at`, `revoked_at`, `last_used_at`,
  `created_at`, `updated_at`

**Columns (add):**

- `checkpoints.sponsored_by_actor_id` UUID NULL FK `actors.id`
  ON DELETE SET NULL
- `compute_debits.actor_id` UUID NULL FK `actors.id`
  ON DELETE SET NULL

**Indexes / constraints:**

- `uq_project_agent_member` UNIQUE `(project_id, actor_id)`
- `ix_project_agent_members_project_status` `(project_id, status)`
- `ix_project_agent_members_actor_id` `(actor_id)`
- `ix_project_agent_members_responsible` `(project_id, responsible_account_id)`
- `uq_agent_session_tokens_hash` UNIQUE `(token_hash)`
- `ix_agent_session_tokens_lookup` `(actor_id, project_id, revoked_at, expires_at)`
- `ix_agent_session_tokens_project_id` `(project_id)`
- `ix_checkpoints_sponsored_by_actor_id`
- `ix_compute_debits_actor_id`
- **Drop** `uq_actors_one_agent_per_project`
- **Create** `uq_actors_one_research_crew_per_project`
  UNIQUE `(actor_metadata->>'project_id')`
  WHERE `type = 'AGENT' AND display_name = 'Research crew'`

**Data migrations (this slice):**

1. Research crew: `UPDATE actors SET account_id = owner`
   for account-less `display_name = 'Research crew'` rows
   whose `actor_metadata->>'project_id'` matches a project
   that has an `OWNER`; then `INSERT` matching
   `project_agent_members` rows
   (`deployed_by_account_id` = `responsible_account_id` =
   owner, `status = active`, `role = researcher`). Skip
   orphans (missing project / owner). Keep
   `display_name = 'Research crew'`.
2. ComputeDebit: `UPDATE compute_debits SET actor_id =
   agent_runs.agent_actor_id` where `agent_run_id` is set
   and that run has `agent_actor_id`. Historical
   `harness_session_turn` rows stay `NULL`.

**Not in slice one (later):**

- `actors.agent_definition_id` and `agent_definitions`
  (slice G, after the first multi-agent campaign)
- Type-aware `ensure_is_member` / transfer hook (slice B)
- Token mint / resolver / `authorize()` gate-swap (slice C)
- `record_compute_debit(..., actor_id=)` wiring (slice D)
- Crew UI / blame sponsor / ops actor fields (slice E)
- Per-agent cap **enforcement** (slice F) — columns exist,
  stay unused
- Fly enablement / secret-file injection (enablement-time)

| Slice | Ships | Must stay out |
| --- | --- | --- |
| **1 — schema** | The inventory above. **Shipped `0.53.0`.** | Everything in "Not in slice one" |
| **B — membership gate** | `ensure_is_member` type-aware; `ensure_can_manage` rejects agents; `ensure_is_human_member` on funding / validation / invites. OWNER-transfer hook: suspend Research crew + `responsible_account_id = outgoing` rows, revoke their tokens; ADMIN-deployed agents whose responsible account is not the outgoing owner stay active. `get_or_create_project_agent_actor` ensures a roster row. Dark loop, when later lit, uses this same roster gate. Account-less crew without a roster still `403`. **This branch as `0.54.0`.** | Token mint; Fly |
| **C — agent token** | OWNER-only mint / rotate / revoke API; 30-day default; max TTL via settings (not `fly.toml [env]`); resolver in `deps.py` + `harness/auth.py`; secret setting. MCP writes with an agent file attribute to the agent + sponsor snapshot. **Swaps** the `0.52.0` human JWT on `authorize()` for the agent session token. Human Console JWT path unchanged. **This branch as `0.55.0`.** | Fly; UI mint; `AGENT_LOOP_ENABLED`; per-agent cap enforcement |
| **D — spend** | `record_compute_debit` / `write_daily_cap_adjustment` take `actor_id`. `HarnessSession` binds the agent; `authorize` / `record_spend` load `jti` + roster. Outsider override closed. Hold notes / amount 0 / prefix / `hold_id` unchanged. Shared project daily cap (no per-agent split). Unfunded ≠ exhausted. Debit only when `tokens_used > 0` for spend. | Per-agent cap enforcement; Fly |
| **E — Crew UI** | Deployed-agents bay on the Crew tab (revoked rows visible, marked revoked); OWNER mint / rotate reveal; members-only roster read; blame sponsor; ops `actor_*` + spend-by-agent. | New tab; Fly; lighting the loop |
| **F — optional caps** | Enforce `token_budget_cap` / `usd_budget_cap` at `authorize` when non-null. Crew edit. | Splitting the project daily cap per agent; funding rows |
| **G — definition catalog** (after first multi-agent campaign) | `agent_definitions` table **and** `actors.agent_definition_id` (nullable FK) in the same revision; deploy-time pointer; read-only family rollup. Upgrade = new version + new project Actor. | Merging Actors; rewriting `author_id`; lighting the loop |

Slice one can deploy alone. Slices C–D are the first time a
live MCP child can honestly speak as an agent and run longer
than a Supabase access JWT; they still do not run on Fly.

### Test plan (when an implementation slice lands)

DB-gated unless noted. Default CI already provisions Postgres.

**Identity / membership**

- Deploy mints one agent Actor owned by the acting account and
  one roster row; second deploy of the same pair is `409`.
- Two named agents on one project are legal; two `Research
  crew` rows are not.
- Migrated Research crew: `account_id` = owner, roster
  `active`; MCP with a minted agent token authors as that
  Actor; `Contribution.actor_id` matches; no second crew row.
- Account-less un-rostered agent still `403` on both write
  stems (`0.51.1` pin stays).
- Agent with owner's `account_id` but no roster row is `403`.
- Agent with roster `suspended` / `revoked` is `403`.
- Dark-loop commission without a roster row is `403` (one
  gate; pin even while `AGENT_LOOP_ENABLED` is false if the
  service is unit-tested).
- `ensure_can_manage` as the agent is `403` (cannot invite,
  cannot PATCH models, cannot fund).
- `POST …/validations` and `POST …/funding` as the agent are
  `403` even when rostered.
- Human JWT path: author remains the human; no crew row; no
  sponsor (`0.51.1` member-write pin stays).

**Auth / threat**

- Agent token for project A on project B: no mint, no debit.
- Human JWT cannot set `author_id` to an agent (payload field
  ignored / absent).
- Agent token resolver never returns a `human` Actor.
- Revoke mid-flight: in-flight `record_spend` with
  `tokens_used > 0` writes a debit; next `authorize` refuses;
  hold/release still amount `0` with `harness_session_turn`
  prefix and `hold_id`.
- Flag-off `OPENTHEORY_DEV_ACTOR_ID` is `401`.
- Mint as a non-member is `403`; as a mere rostered agent is
  `403`; as an ADMIN (not OWNER) is `403`.
- Rotate mints a new `jti`, sets `revoked_at` on the old
  row; old compact JWT fails the next `authorize()`.
- OWNER transfer: Research crew + outgoing-responsible
  agents go `suspended`, their tokens revoked; in-flight
  `record_spend` with `tokens_used > 0` still writes; next
  `authorize()` refuses. `Actor.account_id` and
  `deployed_by_account_id` unchanged. Resume by the new
  OWNER sets `responsible_account_id` and does not un-revoke
  old tokens. An ADMIN-deployed agent whose
  `responsible_account_id` is not the outgoing owner stays
  `active`.

**Spend**

- `FundingAllocation` rows unchanged across authorize /
  record_spend.
- Unfunded project is not exhausted.
- Debit skipped when `tokens_used <= 0`; hold/release still
  written as amount `0`.
- Backfill: AgentRun-linked debits have `actor_id`; historical
  `harness_session_turn` rows stay null.
- Session bind wins over a mismatched `actor_env`.

**Reads**

- Blame: agent author + sponsor on a new harness checkpoint;
  historical human checkpoint has no sponsor.
- Ops: new spend rows expose actor; old rows expose null;
  prefix math unchanged. `test_ops` / harness_meter tests do
  not import `app.harness` from the ops module.

**Invariants (regression, every slice)**

- Only `create_checkpoint` inserts `Checkpoint`.
- Append-only ORM guards still raise on UPDATE/DELETE of
  checkpoint / debit / funding / validation / tag.
- `AGENT_LOOP_ENABLED` default false; agent-run routes still
  `404`.
- Five tab ids in `project-tab.ts`.
- Composition pin and disabled-tool set unchanged.

### Decided (owner, 2026-10-06)

| Decision | Rationale |
| --- | --- |
| Only **OWNER** mints / rotates / revokes tokens (not ADMIN). | A live token is a weeks-long capability grant, not an invite; ADMIN already deploys and can suspend. |
| Roster `GET` is **members only**. | Deployed agents are a capability surface (and a theft-detection surface), not a public contributor list. Human `GET …/members` staying public does not force this one open. |
| Per-agent caps are **stored in slice one, enforced in slice F**. | Identity + the `0.52.0` gate-swap must not change daily-cap occupancy math in the same release. |
| **No validator agent role, ever.** | Contributor and validator stay on separate tables; an agent must not assess its own work. The enum has no room for it. |
| **Revoked agents stay visible on Crew**, marked revoked. | Hiding them loses "who burned the pot" and the forensic trail after a revoke. |
| Default token TTL **30 days**, instantly revocable, no self-renew; max TTL via settings (not `fly.toml [env]`). | Weeks of autonomous research cannot require a human to re-mint twice a day; `revoked_at` on the next DB read is the control. |
| OWNER transfer **does not rewrite** `Actor.account_id` / `deployed_by`; suspends outgoing-responsible agents + Research crew; new owner resumes and mints. | Provenance stays honest; the incoming owner chooses the roster. |
| Keep the **`Research crew` display name**. | Preserves the dark-loop unique-index predicate and the existing Crew bay's language. |
| **One shared project daily cap.** No per-agent split. | Splitting would re-open the overlapping-authorize race `0.47`–`0.51` closed. |
| The dark built-in loop **must require a roster row**. | One gate for all agent authorship. A commissioning human passing the HTTP route is not enough. |
| Fly secret-file injection is an **enablement-time item**, not an open design question. | Same secret discipline as `OPENTHEORY_GATEWAY_TOKEN`; choose volume vs operator-side file when Fly enablement is scheduled, not in slice one. |
| Definition catalog (table **and** `actors.agent_definition_id`) lands **after the first multi-agent campaign**. | A column with no FK target in slice one is noise; adding both later is cheap. |
| An ADMIN-deployed agent whose `responsible_account_id` is **not** the outgoing owner **keeps running** across a transfer. | That ADMIN did not lose the project; only outgoing-responsible rows + Research crew suspend. |

No remaining open design questions. Fly injection stays listed above as enablement-time, not unresolved.

---

## Invariants this proposal must not break

- Append-only ledger; corrections are new rows.
- `create_checkpoint` is the only `Checkpoint` writer; it owns
  the single commit.
- Account is not Actor.
- Funder, contributor, and validator stay on separate tables.
- Unfunded is not exhausted.
- Billed debit only when `tokens_used > 0`.
- Hold/release rows amount `0`, notes literal
  `harness_session_turn` prefix, paired by `hold_id`.
- FastAPI does not import `app.harness`.
- `AGENT_LOOP_ENABLED` stays false; nothing enabled on Fly.
- Five UI tabs only.

---

## Pointers (current code this design is written against)

- Attribution audit: `docs/harness/attribution.md` (`0.51.1`);
  precursor membership gate: `0.52.0` (PR #48) —
  `HarnessSession.authorize()` + human JWT `ensure_is_member`
- Blueprints: `docs/blueprints/conceptual-model.md`,
  `primitives.md`, `external-harness.md`
- Harness: `docs/harness/*.md`; `app/harness/auth.py`,
  `live_mcp.py`, `session.py`, `turns.py`, `gateway.py`
- Auth / membership: `app/api/deps.py`
  `resolve_actor_from_bearer`; `app/services/project_members.py`
  `ensure_is_member` / `ensure_can_manage`
- Agent identity today: `app/services/agent_actors.py`
  (Decision #3); `Actor.__table_args__`
  `uq_actors_one_agent_per_project`
- Writes: `app/services/checkpoints.py` `create_checkpoint`;
  `app/services/tool_runs.py`; `app/services/compute.py`
  `record_compute_debit`; `app/harness/session.py`
  `write_daily_cap_adjustment`
- Spend meter: `app/services/harness_meter.py` (`SESSION_NOTES
  = "harness_session_turn"`)
- Reads: `app/services/blame.py`; `app/services/ops.py`
- Models: `Actor`, `Account`, `ProjectMember`, `Contribution`,
  `ComputeDebit`, `FundingAllocation`, `AgentRun`,
  `Checkpoint`
- Crew UI: `frontend/src/lib/project-tab.ts`;
  `components/workspace/research-crew-panel.tsx`;
  `project-workspace.tsx` Crew `TabPanel`
