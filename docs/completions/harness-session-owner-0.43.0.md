# 0.43.0 — Harness session owner + odd-perfect reference campaign

**Goal.** One session owner for an external DeepSeek Harness run, so
`ComputeDebit`, the turn cap, and pre-LLM exhaust sit on the path a
campaign actually runs (`dsh → llm-pi-ai → python -m app.harness.gateway`),
not only on the `supervise_turn` library tests call. Ship a small
reference campaign for odd perfect numbers. Do not light
`AGENT_LOOP_ENABLED`. Prefer no schema / no migration. Default CI stays
green without `OPENROUTER_API_KEY` or a `dsh` binary.

**Shape.** New `backend/app/harness/session.py` + `campaign.py`.
`create_gateway_app` accepts a bound `HarnessSession` (or
`OPENTHEORY_PROJECT_ID`). Live MCP stays the only domain door. **No
schema, no migration.** Sits on shipped `0.42.0` (`a61affd`, #35).

## What shipped

- **Session owner.** `HarnessSession` binds one run to a human-created
  project. `authorize()` re-verifies composition, applies
  `OPENTHEORY_HARNESS_MAX_TURNS`, and refuses a funded pot with
  `available <= 0` *before* the LLM call. `record_spend()` writes
  `ComputeDebit` only when `tokens_used > 0` (notes
  `harness_session_turn`, no `AgentRun`). A refused start writes
  nothing. Exceptions mint nothing.
- **Metered gateway path.** The HTTP child the Cordis plugin points at
  now sees the owner. Turn cap / exhaust / debit happen there. A bare
  child without a project stays the unmetered probe proxy and is not
  the campaign path. `python -m app.harness.campaign` starts the
  metered child only when `OPENTHEORY_PROJECT_ID` is set.
- **Reference campaign.** Odd perfect numbers. The human sets the
  question, the research-crew roster (`project.agent_models`), and the
  budget (`FundingAllocation`). The harness is instrument-only
  (`run_instrument` / `create_checkpoint`). It never funds, never
  self-validates, never merges. Dead ends stay. Account ≠ Actor. Does
  not reuse `ResearchCampaign` (that row is the built-in planner).
- **P2 (cheap, in scope).** Extra-body allowlist drops `models` /
  `route` / `transforms` so they cannot bypass the fail-closed
  provider claim. Fixture probe logs go through
  `protocol.maybe_log` (redacted).

## What did not change

- `create_checkpoint` remains the only Checkpoint writer.
- Append-only guards, membership, instruments, built-in campaigns,
  orchestrator.
- `AGENT_LOOP_ENABLED` default `false`. Fly `[env]` still has no
  secrets. The gateway / MCP child is **not** enabled on Fly.
- Funder ≠ contributor ≠ validator. Account ≠ Actor.
- Unfunded ≠ exhausted (refuse only when `funded > 0` and
  `available <= 0`).
- No Alembic revision. No frontend. Live MCP inventory unchanged.

## Honest caveats

- A green default pytest is not a live OpenRouter / `dsh` session.
- Turn index is process-local. A restarted child starts at turn 0.
- A bare `python -m app.harness.gateway` without
  `OPENTHEORY_PROJECT_ID` is still unmetered (probe only). The
  campaign path binds a session.
- Daily caps / ops dashboard / Fly enablement are later.

## Tests

- Reference spec is odd-perfect + instrument-only; campaign does not
  import `ResearchCampaign` / funding / Actor.
- Session owner and gateway are not Checkpoint writers; `live_mcp.py`
  is the only harness import of `app.services.checkpoints`.
- Extra-body `models` / `route` stripped; fixture uses
  `protocol.maybe_log`; `fly.toml [env]` has no secrets;
  FastAPI still ignores `app.harness`.
- HTTP turn-cap refuse before the LLM call.
- DB-backed: exhausted funded project does not call the model and
  mints nothing; debit only when `tokens_used > 0`; unfunded is not
  exhausted; attempted completion debits and mints nothing; live MCP
  after a session turn is the only checkpoint writer.

## Verification

- `ruff check .` clean.
- Default pytest (no `TEST_DATABASE_URL`): **795 passed, 245 skipped**.
  +16 vs shipped `0.42.0` (779) — session owner, campaign spec,
  extra-body allowlist, fixture `maybe_log`. +5 skipped (ledger suite).
- With `TEST_DATABASE_URL`: **1036 passed, 4 skipped** — +21 vs `0.42.0`
  (1015). Lean / Mathlib stay off. Frontend untouched.

## Unverified

- A live OpenRouter call with a real key in this environment.
- A full `dsh` session against the session-owned HTTP gateway.
- Fly enablement of the harness child.
