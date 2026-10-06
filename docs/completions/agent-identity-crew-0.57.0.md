# 0.57.0 — Crew UI / blame sponsor / ops actor fields

**Goal.** Land slice E (Crew UI) of the approved agent-actor
identity design: the deployed-agents bay on the existing Crew
tab, members-only roster read, OWNER token reveal, suspend /
resume / revoke where the backend allows, blame sponsor,
checkpoint sponsor, and ops `actor_*` + spend-by-agent. Stay
dark: no Fly, no `AGENT_LOOP_ENABLED`, no per-agent cap
enforcement, no definition catalog. No live Supabase apply
(no migration). Sits on shipped `0.56.0` (`2a2a018`, #52).

**Shape.** Read + UI on the existing 0022 schema. No new table,
no new column, no Alembic revision.

## What shipped

- `GET /projects/{id}/agents` — members only (`ensure_is_member`).
  Includes revoked rows. Status, responsible / deployed-by
  handles, last used, billed spend Σ, live token metadata.
  Never email, never token hash, never the compact JWT.
- `POST /projects/{id}/agents` — OWNER / ADMIN deploy (named
  agent, or `reuse_research_crew`).
- `PATCH /projects/{id}/agents/{actor_id}` — suspend / revoke
  (`OWNER` / `ADMIN`); resume (`OWNER` only). Suspend / revoke
  fan out `revoked_at` on live tokens in the same transaction.
- Crew tab **Deployed agents** bay (full-width above Research
  crew + Collaborators). Five tabs. OWNER mint / rotate /
  revoke token with a one-time modal reveal. Token plaintext
  is component state only and is wiped on dismiss.
- Blame `sponsor: BlameActor | None`. Historical human rows
  stay unsponsored.
- `CheckpointRead.sponsored_by` (id + display name) when set.
- Ops `actor_id` / `actor_display_name` / `actor_type` on
  recent turns and last turn. `spend_by_agent` groups billed
  harness spend by `compute_debits.actor_id`.
- `authorize()` refuses when session and MCP credentials both
  resolve and name different actors (`TurnRefused`, no hold).

## What did not change

- Per-agent cap enforcement (slice F).
- `agent_definitions` (slice G).
- FastAPI does not import `app.harness`. `fly.toml [env]` has
  no secrets. Nothing enabled on Fly. Five tabs.
- No migration. 0022 is still not applied to live Supabase.

## Tests

- Roster list is members-only; outsider 403; unauthenticated
  401; revoked rows remain; billed spend Σ excludes holds.
- Deploy named agent; Research-crew reuse 409 when already
  rostered.
- ADMIN may deploy / suspend / revoke; ADMIN may not resume;
  OWNER resume sets `responsible_account_id`; `REVOKED` resume
  is 409.
- Agent session bearer is 403 on GET/POST/PATCH roster
  (HTTP is human-only).
- Blame and checkpoint reads carry `sponsor` / `sponsored_by`
  on an agent-authored row; human rows stay null.
- Ops turn `actor_*` and `spend_by_agent` group billed harness
  spend; holds do not count.
- Diverged session / MCP credentials: `TurnRefused`, no hold.
  MCP-side empty still stamps the session agent.

## Verification

- Filled after ruff / pytest / frontend suite on this branch.

## Unverified

- Live MCP child speaking as an agent on Fly (not enabled).
- Per-agent cap enforcement (slice F).
- Browser walk of a signed-in Crew tab against a seeded
  project (depends on local Next + FastAPI + throwaway
  Postgres).
