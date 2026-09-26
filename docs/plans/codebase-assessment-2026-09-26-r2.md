# Codebase assessment R2 — 2026-09-26

> Reassessment after R1 remediation. Assessed against
> `cursor/assessment-r1-remediation-1d6f` at `80495c0`
> (`0.36.1` — membership + planner honesty).
> **#23 is open and unmerged** as of this writing
> (`https://github.com/kaminocorp/opentheory/pull/23`).
> `origin/main` is still `71a8929` (`0.36.0`). This document describes
> the remediation tip, not stale main without #23.
>
> R1: `docs/plans/codebase-assessment-2026-09-26-r1.md` (`375733a` / #22).
> Scope: functionality, accuracy, maintainability, clean code. Nice-to-haves
> omitted. OpenTheory hard invariants treated as P0 when violated.
> Assessment only — no code was changed in this pass.

## Executive summary

The R1 P0 and all six R1 P1s are **closed** on this tip. Membership now
covers the original ledger POSTs; the planner uses `compute_signal`;
`ClaimCreate` cannot stamp settlement fields; proof/satisfy chrome
fallthrough is warn; auth docs match `0.6.0`; the orchestrator mid-pass
policy uses the reservation quote.

Hard invariants still hold. No new P0. No new functional P1.

What remains is the R1 P2 set (intentionally deferred by `0.36.1`) plus
three narrower residuals of the R1 fixes: agent-trace pills still drop
invocation output; `ThreadCreate` still accepts a client-stamped
`status`; and seven pre-existing DB-backed toolbench write-path tests
fail when Postgres is present.

| Severity | Count | Theme |
| --- | ---: | --- |
| **P0** | 0 | — |
| **P1** | 0 | All six R1 P1s verified closed |
| **P2** | 10 | R1 P2-1–P2-7 still open, plus 3 residuals |

**What this assessment did *not* find:** a second checkpoint writer, an
append-only bypass in `app/`, a `parse_expr` call that skips
`_reject_unsafe_source`, an agent that self-validates or self-funds, a
frontend `fetch` that bypasses `lib/api.ts`, or a current HTTP research
write that skips `ensure_is_member` / `ensure_member_of_*`.

---

## What was run / what was not

| Check | Result |
| --- | --- |
| `cd backend && uv run ruff check .` | Clean |
| `cd backend && uv run pytest -q` | **649 passed, 222 skipped** (no `TEST_DATABASE_URL`) |
| `cd frontend && npm run typecheck` | Pass |
| `cd frontend && npm run lint` | Pass |
| `cd frontend && npm test` | **41 passed** (includes `resolveOutcomeMeta` fallthrough) |
| `cd frontend && npm run build` | Pass (Next.js 15.5.15) |
| DB-backed ledger / toolbench / agent suite | **Not run** — no Postgres in this environment. `0.36.1` recorded 860 passed / 4 skipped / **7 failed** against local Postgres; those 7 are characterized below from the test code, not re-executed. |
| Browser eyeball pass | **Not run** — still owed per `docs/plans/roadmap-next-steps.md`. |

R1's default pytest was 634 passed / 220 skipped. The +15 / +2 are the
new DB-free membership / schema / planner / reservation tests in
`tests/test_ledger_membership.py` plus the frontend `outcome-meta`
suite.

---

## Hard invariants — verdict

| Invariant | Verdict |
| --- | --- |
| Append-only: Checkpoint / CheckpointRef / FundingAllocation / Validation / ComputeDebit / Tag | **Holds.** Guards in `models/append_only.py:38–45`. No bulk Core `UPDATE`/`DELETE` on those tables in `app/`. |
| Single write chokepoint: only `create_checkpoint` mints `Checkpoint` | **Holds.** Sole `Checkpoint(` in app code: `services/checkpoints.py:291`. |
| Backend owns domain invariants; thin routes → services | **Holds** for ledger writes. Authorization for the original POSTs now lives on the route (P0-1 closed). Project PATCH is still the one fat-route exception (P2-4). |
| Instruments: `result` \| `refuted` \| `undecided`; exceptions mint nothing | **Holds** on the write path (`services/tool_runs.py:172–206` before any `db.add`). UI honesty: function-level fallthrough is correct; agent-trace still drops output (P2-8). |
| Account ≠ Actor; funder ≠ contributor ≠ validator | **Holds in the model.** Funding attributes money to `actor.account_id`. Agent/campaign/orchestration never write `Validation` or `FundingAllocation` (sole writers: `services/validations.py:162`, `services/funding.py:114`). |
| `docs/` source of truth; code wins on conflict | Blueprints match the ledger. `CLAUDE.md` and `deploy.md` now describe JWT + membership (R1 P1-5 closed). One stale schema docstring remains (P2-11). |
| CONTRIBUTION-GUIDELINES.md | Prime directives 1–2, 4–6 hold. Directive 3 + “writes are membership-gated (`ensure_is_member`)” now holds on every original research POST. |

Intentional non-findings (do not “fix”):

- Thread / claim / evidence creates do **not** auto-mint a checkpoint.
- Funding is contribution-only, not a research checkpoint.
- Agent / campaign / orchestration own their own commits for *mutable traces*; each ledger write still goes through `run_instrument` → `create_checkpoint`.
- Agent compose paths (`create_checkpoint`, `create_branch` inside a pass) stay ungated — the commissioning human was already a member. Putting `ensure_is_member` inside `create_checkpoint` would 403 account-less agent actors.

---

## R1 verification

### P0-1 — Any authenticated principal can write another project's ledger

**Closed.**

Every original research POST now calls `ensure_is_member` (or the nested
helpers that resolve the project from the loaded row):

| Route | Gate |
| --- | --- |
| `POST /projects/{id}/checkpoints` | `ensure_is_member` |
| `POST /projects/{id}/threads` | `ensure_is_member` |
| `POST /threads/{id}/claims` | `ensure_member_of_thread` |
| `POST /projects/{id}/validations` | `ensure_is_member` |
| `POST /claims/{id}/evidence` | `ensure_member_of_claim` |
| `POST` branch / close | `ensure_is_member` / `ensure_member_of_branch` |
| `POST /projects/{id}/merges` | `ensure_is_member` |
| `POST /projects/{id}/tags` | `ensure_is_member` |
| `POST /projects/{id}/funding` | `ensure_is_member` **and** `internal` (explicit decision: a platform comp is not a write against a project you have not joined) |

Later surfaces (instruments / agent / campaign / orchestration) were
already gated and remain so.

Frontend: project write forms use `useProjectWriteAccess`
(`frontend/src/lib/use-project-write-access.ts`) — signed in **and** a
row in `GET /projects/{id}/members`. `useActingIdentity().canWrite`
stays “signed in” only for creating a project. The comment at
`project-workspace.tsx:84–85` is now true.

Tests: `tests/test_ledger_membership.py` — DB-free unauthenticated
POSTs → `401`; DB-backed non-member → `403` and checkpoint count does
not rise. The DB-backed case was not re-run here (no Postgres); the
code and the 0.36.1 completion record it.

Residual (not a reopen): the gate is **route-level**, not inside
`create_checkpoint` / `create_claim`. That is the correct split for
agent compose. A future HTTP route that calls those services and
forgets `ensure_is_member` would re-open P0-1 the same way it survived
`0.8.1`–`0.36.0`. Defense-in-depth is a shared FastAPI dependency or a
checklist in CONTRIBUTION-GUIDELINES, not a service-layer 403 on the
chokepoint.

### P1-1 — Agent and orchestrator treat `Claim.status` as settlement

**Closed.**

`_open_claims` in both `agent_runs.py:91–93` and
`orchestration.py:135–136` delegates to
`claim_service.open_claims_for_planner`. That function batch-loads
validations, runs `compute_signal`, and keeps claims where
`claim_is_open_work(signal)` (`signal != "validated"`).
`Claim.status` is not consulted. Grep of `app/services` finds **no**
assignment of `ClaimStatus.VALIDATED` / `RETRACTED`.

`tests/test_ledger_membership.py::test_validation_removes_claim_from_open_claims`
asserts a `passed` validation empties the open set while
`Claim.status` stays `proposed`. DB-gated; not re-run here.

### P1-2 — `ClaimCreate` lets a client stamp `status` / `confidence`

**Closed.**

`schemas/claim.py:103–116` — `ClaimCreate` is a standalone model
(`extra="forbid"`) with `kind` / `statement` / `rationale` /
`claim_metadata` only. `create_claim` dumps that payload onto the ORM;
the column default remains `proposed`, `confidence` stays `NULL`.
DB-free tests reject stamped `status` and `confidence`.

### P1-3 — Agent-pass step pills use generic `outcomeMeta`

**Closed for the dangerous case.** Residual: P2-8.

`resolveOutcomeMeta` lives in `frontend/src/components/workspace/toolbench/outcome.ts`
and is imported by both `result-view.tsx` and
`agent-run-trace.tsx`. `LandedStep` now passes `step.instrument`.

It still passes `output = {}` (`agent-run-trace.tsx:66`).
`AgentRunStep` has no output field (`types/agent-run.ts:31–47`);
`_executed_step` records `outcome` (the enum) but not the invocation
payload (`agent_runs.py:149–167`).

Consequence:

- Proof / satisfy `result` with empty output → **warn / Undecided**
  (P1-4 fallthrough). A successful proof on the operator trace reads
  conservative, not as a pass. Honesty rule holds.
- `counterexample.search` weak support (`result` + `found: false`)
  still falls through to generic **Result / ok**, because `found` is
  not `false` on `{}`. Same for `table.derive_column` finite-hold.

The original P1 was “undecided / weak support must never read as a
pass.” Proof-as-pass is closed. Weak-support-as-pass on the agent
trace is the leftover, now P2.

### P1-4 — `resolveOutcomeMeta` fallthrough can paint a proof `result` as a pass

**Closed.**

`outcome.ts:71–133` — `z3.prove` / `z3.satisfy` / `lean.prove` return
**warn** unless the machine-checked flag is true. Covered by
`outcome-meta.test.ts` (6 cases, all green in this run).

### P1-5 — Assistant contract and deploy runbook still say there is no auth

**Closed.**

- `CLAUDE.md:9` — agents are a shipped `Actor` type (`0.12`+).
- `CLAUDE.md:68` — JWT → Account → human Actor; `X-Dev-Actor-Id`
  only behind `auth_dev_header_enabled`; writes then
  `ensure_is_member`.
- `docs/operations/deploy.md:7–11` — production requires a verified
  bearer; membership-gated writes; do not enable the dev header on
  Fly.
- `docs/blueprints/primitives.md:34–37` — authorization is
  membership, not credit.

One leftover: `schemas/validation.py:13` still says `actor_id` comes
from `X-Dev-Actor-Id` (P2-11). Not a runbook.

### P1-6 — Orchestrator mid-pass budget policy uses the blended catalog rate

**Closed.**

`_policy_from_reservation(agent_run, rate_per_1k)`
(`orchestration.py:574–584`) takes the rate that sized the hold.
`_commission_reserved_pass` quotes first (`quote_model_price` →
`effective_rate_per_1k`), stores it on `ReservedPass`, and
`_run_wave` passes that rate into the policy. No
`rate_for_model` on the mid-pass path. DB-free test:
`test_policy_from_reservation_uses_the_hold_rate_not_the_catalog`.

---

## Remaining / new P2 findings

R1 P2-1–P2-7 were explicitly deferred by `0.36.1`. They are still
open. Three residuals of the R1 work are new.

### P2-1 — `ensure_can_manage` / `canManageProject` mean “any member”

Unchanged. `ensure_can_manage` 403s only when there is no membership
row, unless `require_owner=True`. Frontend `canManageProject`
(`project-workspace.tsx:90–91`) and the header comment
(`project-header.tsx:76–77`) still say owner/admin. Today
`ProjectRole` is only `owner` | `admin`, so the predicate is
accidentally right until a lower-privilege role lands.

### P2-2 — Auth menu labels a non-internal account “Contributor”

`frontend/src/components/shell/auth-menu.tsx:165`. That word is a
credit role (`Contribution`), not an account posture.

### P2-3 — Claim rows still render a bare confidence percentage

`claim-list-panel.tsx:232–238`. After P1-2, new claims cannot carry a
client-stamped score, so the chip is dead for fresh rows. The column
and the chrome remain. `primitives.md` still forbids a naked score as
confidence.

### P2-4 — Project metadata PATCH mutates in the route

`api/routes/projects.py:54–90`. Docstring still claims “authorization
is enforced in the service”; the handler calls `ensure_can_manage`
then `setattr` / assign + `commit`. Project is not append-only.

### P2-5 — No repository CI workflows

Still no `.github/` tree. The contribution contract (`ruff` +
`pytest` + `typecheck` + `lint` + `build`) is honor-system. A default
pytest is now **649 passed / 222 skipped**. The tests that prove
P0-1 / P1-1 stay closed are in the skipped set unless
`TEST_DATABASE_URL` is set.

### P2-6 — Duplicate in-flight agent-run polling; `visitedTabs` mutated during render

Unchanged. `project-workspace.tsx:146–148` and `agent-pass-panel.tsx`
both poll `getAgentRun`. `visitedTabs.current.add(tab)` still runs
during render (`project-workspace.tsx:165`).

### P2-7 — Documented dual-fork race on concurrent agent passes

Unchanged. `services/agent_runs.py:113–118`. Accepted for v1.
`extra_refs` remain trusted by design.

### P2-8 — Agent-trace `LandedStep` still drops invocation output *(new residual of P1-3)*

`agent-run-trace.tsx:66`:

```ts
const meta = resolveOutcomeMeta(step.instrument, step.outcome ?? "", {});
```

Proof / satisfy are honest via fallthrough (warn). Weak-support
`counterexample.search` and finite-table holds still paint **Result /
ok**. A real `z3.prove` success paints **Undecided** on the pill
(the timeline card below is honest).

Fix: record a display hint on the step (`proven` / `found` /
`is_relation`), or persist a trimmed output map on `AgentRunStep`.
Do not make `LandedStep` fetch the checkpoint to re-parse the blame
tuple.

### P2-9 — `ThreadCreate` still accepts a client-stamped `status` *(new)*

`schemas/thread.py:11–20` — `ThreadCreate` inherits `ThreadBase`,
which includes `status: ThreadStatus = OPEN` and `stage`.
`create_thread` dumps the payload (`services/threads.py:26`). There
is **no** thread-status update path (`thread.status =` is absent
from `app/services`).

The UI sends `{ title, question }` only (`thread-list-panel.tsx:43`;
frontend `ThreadCreate` omits `status`). A member `curl` can create
`status=closed` / `dead_end` / `blocked`. The orchestrator then
skips the thread (`_OPEN_THREAD_STATUSES` is `open` | `active`)
forever.

This is the same *shape* as R1 P1-2, at much lower blast radius:
membership-gated, no forged `Validation`, the column is live (unlike
`Claim.status`). Strip `status` from `ThreadCreate` (keep `stage` if
create-time stage is wanted) or `extra="forbid"` and default
`OPEN` in the service.

### P2-10 — Seven pre-existing DB-backed toolbench write-path tests fail *(new / pre-existing)*

`0.36.1` recorded **7 failed** when run with `TEST_DATABASE_URL`.
From the test code, the cause is not `0.36.1`:

`tests/toolbench/test_write_path.py` builds `Stub("calc.eval")` with
`InputModel = {value: int}` and calls `run_instrument`. Since
`0.11.3`, `run_instrument` dispatches through the sandbox worker,
which looks the name up in the **real** registry
(`execution/worker.py:62`). The worker runs production `calc.eval`
(`expression` required) against `{"value": 25}` — not the stub.
Geometry `*_latex` companions are a sibling assertion drift.

These tests skip without Postgres, so default CI-shaped pytest stays
green. They are the write-path suite that is supposed to prove
chokepoint composition. Either register a distinct stub name
(`test.stub`) via `tests/toolbench/stubs.py`, or stop naming the
stub `calc.eval`.

### P2-11 — `ValidationCreate` docstring still names `X-Dev-Actor-Id`

`schemas/validation.py:13`. Production acting actor is the bearer
JWT. One-line docstring fix; not a runbook.

---

## Files >500 LOC

Line counts from `wc -l` on `80495c0`. R1 counts in parentheses
where they moved.

### Backend

| LOC | Δ vs R1 | File | Split recommendation |
| ---: | ---: | --- | --- |
| **954** | −11 | `backend/app/services/agent_runs.py` | Still the split from R1: `commission.py` / `branch_select.py` / `execute_pass.py`. Openness now lives in `claims.open_claims_for_planner` — do not fork a second predicate when splitting. |
| **786** | +6 | `backend/app/services/orchestration.py` | `eligibility.py` / `wave_executor.py` / `lifecycle.py`. `_policy_from_reservation` now takes the quote; keep that signature when moving. |
| **726** | 0 | `backend/app/services/campaigns.py` | `lifecycle.py` vs `cycle_wave.py`. |
| **642** | 0 | `backend/app/services/diff.py` | `resolve_ref.py` vs `delta_build.py`. Shared ancestry with `blame.py` (399) still worth extracting. |
| **522** | 0 | `backend/app/toolbench/instruments/_lean_support.py` | Mathlib / `lake` vs prelude stub. |
| **514** | 0 | `backend/app/toolbench/instruments/_interval_support.py` | Enclosure engine vs relation decision. Lower priority. |

### Frontend

| LOC | Δ vs R1 | File | Split recommendation |
| ---: | ---: | --- | --- |
| **1421** | 0 | `frontend/src/components/workspace/toolbench/drive-forms.tsx` | **Highest remaining frontend maintainability risk** (now larger than `result-view`). One file per instrument form + a thin registry. |
| **1337** | −149 | `frontend/src/components/workspace/toolbench/result-view.tsx` | `resolveOutcomeMeta` extracted to `outcome.ts` (216). Per-instrument bodies still belong in their own files. |
| **628** | −1 | `frontend/src/types/research.ts` | `claim.ts` / `ledger.ts` / `membership.ts`; barrel-re-export. |
| **566** | 0 | `frontend/src/components/workspace/project-workspace.tsx` | Tab panel / rollup / budget / instrument-context into `project-workspace-parts/`. |
| **547** | +3 | `frontend/src/components/workspace/branch-bar.tsx` | Line selector vs close/merge modals vs merge form. |

Approaching the line: `claim-list-panel.tsx` (489), `lib/api.ts` (457),
`agent-run-trace.tsx` (408). Split `claim-list-panel` when touching
P2-3.

---

## Test / CI gaps that hide bugs

1. **Default pytest is still not a ledger gate.** This run: `649
   passed, 222 skipped`. The tests that lock P0-1 and P1-1
   (`test_non_member_cannot_write_another_projects_ledger`,
   `test_validation_removes_claim_from_open_claims`) skip without
   Postgres.
2. **No `.github/workflows`.** Unchanged from R1. If CI is added, the
   useful job is `TEST_DATABASE_URL=… pytest` against a throwaway
   Postgres — and it must treat the 7 write-path failures (P2-10) as
   the first ticket, or the job will be red on day one.
3. **Browser eyeball pass** still owed. Would catch P2-8 chrome.
4. **`tests/conftest.py` localhost guard** on implicit `DATABASE_URL`
   is still correct and must stay.

---

## Drift vs `docs/blueprints`

Blueprints match the code on the primitives that matter. The
membership paragraph added to `primitives.md` in `0.36.1` is
accurate.

Remaining drift that will cause wrong behavior:

| Doc | Drift | Effect |
| --- | --- | --- |
| `schemas/validation.py:13` | Acting actor described as `X-Dev-Actor-Id` | Assistants reading the schema (not CLAUDE.md) re-learn the 0.3.x header. P2-11. |

`docs/plans/roadmap-next-steps.md` correctly says `0.36.1` is this
branch, not `main`. Keep that banner until #23 merges.

`docs/changelog.md` index line for `0.36.1` matches the tip. Do not
claim `0.36.1` on `main` until #23 is merged.

---

## Prioritized remediation (next fix PR)

One concern per PR. R1 items 1–5 are **done** on this tip (unmerged).

| # | PR | Closes | Notes |
| ---: | --- | --- | --- |
| **1** | GitHub Actions: ruff + pytest **with Postgres** + frontend typecheck/lint/build; repair the 7 write-path stubs so the job is green | P2-5, P2-10 | Makes P0-1 / P1-1 stay closed. Do this before any more ledger work. |
| **2** | Agent-trace display hint or trimmed step output; `LandedStep` stops passing `{}` | P2-8 | Small. Needs a frontend test that `counterexample.search` + `result` + no output is not `ok`, *or* that the step carries `found`. |
| **3** | `ThreadCreate` drops `status` (service defaults `OPEN`); `ValidationCreate` docstring | P2-9, P2-11 | Same shape as P1-2; one-file backend. |
| **4** | Naming / confidence chrome / route-to-service move / poll hook | P2-1–P2-4, P2-6 | After the test gate. |
| **5** | Split remaining >500 LOC files (`drive-forms`, `result-view`, `orchestration`, `campaigns`, `diff`) | Large-file flag | Only after behavior is covered by CI. |

Do not start a “cleanup” PR that mixes CI, file splits, and honesty
chrome. The membership hole is closed on this tip; the thing that
keeps it closed is a Postgres job.

---

## R1 → R2 scoreboard

| ID | R1 severity | R2 verdict |
| --- | --- | --- |
| P0-1 membership on original ledger POSTs + UI `canWrite` | P0 | **Closed** |
| P1-1 planner open-claims via `compute_signal` | P1 | **Closed** |
| P1-2 `ClaimCreate` forbids `status` / `confidence` | P1 | **Closed** |
| P1-3 agent-trace uses `resolveOutcomeMeta` | P1 | **Closed** (residual P2-8: empty output) |
| P1-4 proof/satisfy fallthrough → warn | P1 | **Closed** |
| P1-5 CLAUDE.md / deploy.md auth | P1 | **Closed** |
| P1-6 reservation quote for mid-pass policy | P1 | **Closed** |
| P2-1–P2-7 | P2 | **Open** (deferred by 0.36.1) |
