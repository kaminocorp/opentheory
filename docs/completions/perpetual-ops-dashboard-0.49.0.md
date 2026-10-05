# 0.49.0 — Perpetual ops dashboard

**Goal.** Give the human operator who sets the research question, agent
roster, and budget a truthful, read-only view of the budgeted perpetual
setup — per-project pot vs spent, today's harness daily-cap usage
against `OPENTHEORY_HARNESS_DAILY_TOKEN_CAP` (including open/released
holds by `hold_id`), recent harness ledger rows, and whether the
built-in loop / gateway is actually enabled. Do not light
`AGENT_LOOP_ENABLED`. Do not enable the gateway or MCP child on Fly.
Default CI stays green without `OPENROUTER_API_KEY` or a live network.

**Shape.** A derived public GET (`GET /projects/{id}/ops`) plus a quiet
Overview bay. The daily-cap numbers are the same meter
`HarnessSession.authorize()` writes: today's `ComputeDebit` rows whose
notes start with the literal `harness_session_turn` prefix. The product
API does not import `app.harness`; the shared meter lives in
`app/services/harness_meter.py`. **No schema, no migration, no campaign
table.** Sits on shipped `0.48.0` (`7094d18`, #41).

## Why this shape

- A sixth deepdive tab is frozen for v1. Overview is already the
  operator surface (budget, Run research, continuous campaign).
- Refused starts mint nothing. Inventing a refusals log would be a
  write. The dashboard says they are not recorded.
- FastAPI cannot see whether a separate Fly process is running. Loop
  enablement is `settings.agent_loop_enabled`. Gateway / MCP child are
  `unknown`.
- The campaign child may override `OPENTHEORY_HARNESS_DAILY_TOKEN_CAP`
  independently of this API process. The payload labels that.

## What shipped

- **Read-only snapshot.** `GET /projects/{id}/ops` returns budget
  (unfunded ≠ exhausted), today's harness token sum vs the cap this
  API process sees, today's holds paired by `hold_id` (legacy id-less
  holds pair FIFO), the newest 20 `harness_session_turn` rows, a
  refusals honesty block, and enablement. Missing project is `404`.
  The handler never writes. `create_checkpoint` remains the only
  Checkpoint writer.
- **Shared meter.** Notes prefix, `hold_id` parse, today's sum, and
  hold pairing live in `app.services.harness_meter`. The session owner
  re-exports the same functions. FastAPI still does not import
  `app.harness`.
- **Overview bay.** Quiet Perpetual ops panel. No Start / Stop / Fund
  controls. Unknown stays labeled unknown.

## What did not change

- `create_checkpoint` remains the only Checkpoint writer.
- Append-only guards, membership, instruments, built-in campaigns,
  orchestrator.
- `AGENT_LOOP_ENABLED` default `false`. Fly `[env]` still has no
  secrets. The gateway / MCP child is **not** enabled on Fly.
- Funder ≠ contributor ≠ validator. Account ≠ Actor.
- No Alembic revision. No campaign table. No sixth tab.
- Gateway version stays `0.48.0` (this slice does not change the
  gateway).
- Process-local turn index still resets to 0 on restart.

## Honest caveats

- A green default pytest is not a live OpenRouter / `dsh` session.
- Refusals cannot be listed. They are not on the ledger.
- Gateway / MCP child enablement on Fly is unknown to this API
  process.
- Cap / TTL are what *this* API process sees. A child-only override
  is unknown and labeled as such.
- A single turn that burns more than the remaining room can still
  finish over the cap (the check is before the model).
- Browser eyeball pass remains owed.

## Tests

- DB-free: unfunded ≠ exhausted; invalid cap is unknown; hold pairing
  by `hold_id` + legacy FIFO; refusals not invented; OpenAPI GET-only;
  FastAPI ops path AST-walks do not import `app.harness`.
- DB-gated: missing project 404; empty project is unfunded / used 0;
  harness spend + hold/release counted; non-harness and
  `harnessXsession_turn` decoy ignored; GET mints no checkpoint;
  funded exhausted pot is exhausted, not unfunded.
- Existing daily-cap / FastAPI-ignores-harness / fly.toml-no-secrets
  tests stay.

## Verification

- `ruff check .` clean.
- Default pytest (no `TEST_DATABASE_URL`, no `OPENROUTER_API_KEY`):
  **839 passed, 257 skipped**. +9 passed vs shipped `0.48.0` (830)
  (ops honesty / OpenAPI / import-posture). +4 skipped (ops ledger
  reads).
- Harness pytest: **87 passed, 25 skipped** without
  `TEST_DATABASE_URL` — same as shipped `0.48.0`.
- Frontend: typecheck / lint / build clean. **62** node:test cases
  (+5 honesty cases).
- Ledger suite skips without `TEST_DATABASE_URL` (CI Postgres runs
  it). Lean / Mathlib stay off.

## Unverified

- A live OpenRouter call with a real key in this environment.
- A full `dsh` session against the session-owned HTTP child.
- Fly enablement of the harness child.
- Pixel-level browser walk of the Overview bay.
