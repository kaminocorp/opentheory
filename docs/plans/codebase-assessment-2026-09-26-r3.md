# Codebase assessment R3 — 2026-09-26

> Final reassessment after R2 P2 bugfixes. Assessed against
> `cursor/assessment-r2-p2-bugfixes-e590` at `1097120`
> (`0.36.2` — ThreadCreate + agent-trace honesty + write-path suite).
>
> **Stacked PRs are still unmerged.** As of this writing:
>
> | PR | Title | State | Base |
> | --- | --- | --- | --- |
> | [#23](https://github.com/kaminocorp/opentheory/pull/23) | `0.36.1` R1 remediation | OPEN | `main` |
> | [#24](https://github.com/kaminocorp/opentheory/pull/24) | docs: assessment R2 | DRAFT | `#23` branch |
> | [#25](https://github.com/kaminocorp/opentheory/pull/25) | `0.36.2` R2 P2 bugfixes | DRAFT | `#23` branch |
>
> `origin/main` is still `71a8929` (`0.36.0`). `#24` and `#25` are
> **siblings** on `#23`, not a linear stack. This document describes the
> `0.36.2` tip (`1097120`), not stale main without `#23`/`#25`.
>
> R1: `docs/plans/codebase-assessment-2026-09-26-r1.md` (`375733a` / #22,
> on `main`). R2: `docs/plans/codebase-assessment-2026-09-26-r2.md` lives
> only on #24 (`44b8587`) — it is **not** in this tree. This pass read it
> via `gh` from that branch.
>
> Scope: functionality, accuracy, maintainability, clean code. Nice-to-haves
> omitted. OpenTheory hard invariants treated as P0 when violated.
> Assessment only — no code was changed in this pass.

## Executive summary

The R2 bug-like residuals are **closed** on this tip. `ThreadCreate`
cannot stamp `status`. Agent-trace pills pass a persisted display map
into `resolveOutcomeMeta` (via `landedStepMeta`). Write-path stubs
register as `test.stub*` and geometry write-path assertions accept
`*_latex` companions. The `ValidationCreate` docstring matches JWT auth.

R1 P0 and all six R1 P1s remain **closed**. Hard invariants still hold.
No new P0. No new functional P1.

What remains is the deferred R1 P2 set (naming, confidence chrome, fat
route, no CI, poll hook, documented dual-fork race) plus two small
residuals of the same class R2 already treated as P2 (a stale
`BranchCreate` docstring; the planner *prompt* still prints the dead
`Claim.status` column even though the *filter* uses `compute_signal`).

**Another functionality-bug remediation loop is not warranted.** The
assessor loop can stop for bug severity. Remaining P2s are
maintainability and should be ordinary product PRs (CI first), not a
fourth assessor round.

| Severity | Count | Theme |
| --- | ---: | --- |
| **P0** | 0 | — |
| **P1** | 0 | R1 P1s stay closed; R2 residuals closed; no new functional P1 |
| **P2** | 9 | R1 P2-1–P2-7 still open, plus 2 small residuals |

**What this assessment did *not* find:** a second checkpoint writer, an
append-only bypass in `app/`, a `parse_expr` call that skips
`_reject_unsafe_source`, an agent that self-validates or self-funds, a
frontend `fetch` that bypasses `lib/api.ts`, a current HTTP research
write that skips `ensure_is_member` / `ensure_member_of_*`, a
client-stamped `Claim.status` / `Thread.status` on create, or an
agent-trace pill that still passes `{}` when the step recorded output.

---

## What was run / what was not

| Check | Result |
| --- | --- |
| `cd backend && uv run ruff check .` | Clean |
| `cd backend && uv run pytest -q` | **664 passed, 222 skipped** (no `TEST_DATABASE_URL`) |
| `cd frontend && npm run typecheck` | Pass |
| `cd frontend && npm run lint` | Pass |
| `cd frontend && npm test` | **45 passed** (includes `landedStepMeta` vs ResultView) |
| `cd frontend && npm run build` | Pass (Next.js 15.5.15) |
| DB-backed ledger / toolbench / agent suite | **Not run** — no Postgres in this environment. The repaired write-path tests (`test.stub*` + geometry latex) stay in the skipped set. Characterized from the test code, not re-executed. |
| Browser eyeball pass | **Not run** — still owed per `docs/plans/roadmap-next-steps.md`. |

R2's default pytest (on `80495c0`) was 649 passed / 222 skipped. The +15
are the DB-free ThreadCreate / trace-display / write-path stub tests
landed in `0.36.2`. Frontend tests stayed at 45 (R2 was 41; `0.36.2`
added the `landedStepMeta` suite).

---

## Hard invariants — verdict

| Invariant | Verdict |
| --- | --- |
| Append-only: Checkpoint / CheckpointRef / FundingAllocation / Validation / ComputeDebit / Tag | **Holds.** Guards in `models/append_only.py:38–45`. No bulk Core `UPDATE`/`DELETE` on those tables in `app/`. |
| Single write chokepoint: only `create_checkpoint` mints `Checkpoint` | **Holds.** Sole `Checkpoint(` in app code: `services/checkpoints.py:291`. |
| Backend owns domain invariants; thin routes → services | **Holds** for ledger writes. Authorization for the original POSTs lives on the route (P0-1 stays closed). Project PATCH is still the one fat-route exception (P2-4). |
| Instruments: `result` \| `refuted` \| `undecided`; exceptions mint nothing | **Holds** on the write path (`services/tool_runs.py:172–206` before any `db.add`). UI honesty: `landedStepMeta` now feeds recorded output (R2 P2-8 closed). |
| Account ≠ Actor; funder ≠ contributor ≠ validator | **Holds in the model.** Funding attributes money to `actor.account_id`. Sole `Validation(` / `FundingAllocation(` writers: `services/validations.py:162`, `services/funding.py:114`. Agent/campaign/orchestration never write either. |
| `docs/` source of truth; code wins on conflict | Blueprints match the ledger. `CLAUDE.md` and `deploy.md` describe JWT + membership (R1 P1-5 stays closed). One stale schema docstring remains (`BranchCreate`, P2-12). |
| CONTRIBUTION-GUIDELINES.md | Prime directives 1–2, 4–6 hold. Directive 3 + “writes are membership-gated (`ensure_is_member`)” holds on every original research POST. |

Intentional non-findings (do not “fix”):

- Thread / claim / evidence creates do **not** auto-mint a checkpoint.
- Funding is contribution-only, not a research checkpoint.
- Agent / campaign / orchestration own their own commits for *mutable traces*; each ledger write still goes through `run_instrument` → `create_checkpoint`.
- Agent compose paths (`create_checkpoint`, `create_branch` inside a pass) stay ungated — the commissioning human was already a member. Putting `ensure_is_member` inside `create_checkpoint` would 403 account-less agent actors.

---

## R2 verification — bug-like residuals

### P2-8 — Agent-trace `LandedStep` dropped invocation output

**Closed.**

Backend persists a trimmed display map on landed steps:

```165:169:backend/app/services/agent_runs.py
def _trace_display_output(output: Any) -> dict[str, Any]:
    """Trim a landed invocation output to the display flags the agent-trace pills need."""
    if not isinstance(output, dict):
        return {}
    return {key: output[key] for key in _TRACE_DISPLAY_KEYS if key in output}
```

`_TRACE_DISPLAY_KEYS` is exactly the set `resolveOutcomeMeta` reads
(`proven`, `refuted`, `satisfied`, `unsatisfiable`, `found`,
`is_relation`, `outcome`). `_executed_step` records `output` (default
`{}`). Landed steps call
`output=_trace_display_output(_invocation_output(result))`
(`agent_runs.py:650–658`).

Frontend no longer passes `{}`:

```202:207:frontend/src/components/workspace/toolbench/outcome.ts
export function landedStepMeta(step: {
  instrument: string;
  outcome?: string | null;
  output?: Record<string, unknown> | null;
}): OutcomeMeta {
  return resolveOutcomeMeta(step.instrument, step.outcome ?? "", step.output ?? {});
}
```

`LandedStep` uses `landedStepMeta(step)`
(`agent-run-trace.tsx:66–67`). Pre-0.36.2 rows without `output` keep
proof/satisfy fallthrough (warn). Covered by
`outcome-meta.test.ts` (`landedStepMeta` suite: proven match, weak-support
counterexample is not `ok`, finite-table hold, recorded output ≠ empty
map).

### P2-9 — `ThreadCreate` accepted a client-stamped `status`

**Closed.**

`ThreadCreate` is standalone (`extra="forbid"`), no `status`
(`schemas/thread.py:19–34`). `create_thread` stamps
`ThreadStatus.OPEN` (`services/threads.py:27–30`). There is still no
thread-status update path in `app/services`. DB-free tests reject
`closed` / `dead_end` / `blocked` / `active` and extra keys
(`tests/test_ledger_membership.py:103–118`).

### P2-10 — Seven DB-backed write-path tests failed (stub named `calc.eval`)

**Closed at the code/test layer. Not re-executed against Postgres.**

`tests/toolbench/stubs.py` registers `test.stub` /
`test.stub_refuted` / `test.stub_undecided` / `test.stub_boom`.
`WritePathStub("calc.eval")` raises. `test_write_path.py` asserts the
names and that the sandbox worker dispatches `test.stub` to
`{value: 25}` — not production `calc.eval`. Geometry write-path
asserts `radians` / `degrees` **and** `*_latex` companions
(`test_instruments_write_path.py:183–190`).

Those tests still skip without `TEST_DATABASE_URL`. Default pytest
staying green does **not** prove the DB round-trip. The failure mode
R2 named is gone from the test code.

### P2-11 — `ValidationCreate` docstring named `X-Dev-Actor-Id` only

**Closed.** `schemas/validation.py:13–14` now says bearer JWT, with
the dev header only when `auth_dev_header_enabled`. A sibling
docstring remains on `BranchCreate` (P2-12).

---

## R1 verification — still closed on this tip

Re-checked on `1097120`; none of the `0.36.2` edits reopened them.

| ID | Verdict | Evidence |
| --- | --- | --- |
| P0-1 membership on original ledger POSTs + UI `canWrite` | **Closed** | Every listed POST calls `ensure_is_member` / `ensure_member_of_*`. Project forms use `useProjectWriteAccess`. `useActingIdentity().canWrite` is create-project only. |
| P1-1 planner open-claims via `compute_signal` | **Closed** | `_open_claims` → `open_claims_for_planner` → `claim_is_open_work(compute_signal(...))`. Residual: the LLM *prompt* still prints `claim.status` (P2-13). |
| P1-2 `ClaimCreate` forbids `status` / `confidence` | **Closed** | `extra="forbid"`; fields omitted. Tests still pass. |
| P1-3 agent-trace uses `resolveOutcomeMeta` | **Closed** | Now with real output (P2-8). |
| P1-4 proof / satisfy fallthrough → warn | **Closed** | `outcome.ts:71–132`; tests assert empty `{}` is never `ok`. |
| P1-5 `CLAUDE.md` / `deploy.md` auth | **Closed** | JWT + membership; agents are a shipped `Actor` type. |
| P1-6 reservation quote for mid-pass policy | **Closed as specified** | `_policy_from_reservation(agent_run, rate)` uses the hold rate. Orchestrated `run_agent_pass` still fetches a *fresh* `quote_model_price` for the debit (`agent_runs.py:383–402`). That is seconds-scale temporal drift, not the catalog-vs-live bug R1 named. Not a new P1. |

---

## Remaining P2 findings

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
and the chrome remain. The same row also prints `{claim.status}`
(`:245–247`) — create-time `proposed` next to a live `GroundingChip`
and (further down) `claim.signal`. Same family: a stored field the
read model does not treat as settlement, shown as if it were.

### P2-4 — Project metadata PATCH mutates in the route

`api/routes/projects.py:54–90`. Docstring still claims “authorization
is enforced in the service”; the handler calls `ensure_can_manage`
then `setattr` / assign + `commit`. Project is not append-only.

### P2-5 — No repository CI workflows

Still no `.github/` tree. The contribution contract (`ruff` +
`pytest` + `typecheck` + `lint` + `build`) is honor-system. A default
pytest is now **664 passed / 222 skipped**. The tests that lock P0-1 /
P1-1 / P2-9 stay in the skipped set unless `TEST_DATABASE_URL` is set.

### P2-6 — Duplicate in-flight agent-run polling; `visitedTabs` mutated during render

Unchanged. `project-workspace.tsx:144–148` and `agent-run-trace.tsx`
both poll `getAgentRun` (TanStack dedupes HTTP).
`visitedTabs.current.add(tab)` still runs during render
(`project-workspace.tsx:165`).

### P2-7 — Documented dual-fork race on concurrent agent passes

Unchanged. `services/agent_runs.py:113–118`. Accepted for v1.
`extra_refs` remain trusted by design.

### P2-12 — `BranchCreate` docstring still names `X-Dev-Actor-Id` *(new residual of P2-11)*

`schemas/branch.py:14`: *“`actor_id` from the `X-Dev-Actor-Id`
header.”* Production acting actor is the bearer JWT. Same class as
closed P2-11; one-line docstring. Does not affect runtime.

### P2-13 — Planner prompt still prints dead `Claim.status` *(new residual of P1-1)*

`agent/prompts.py:115–120` still emits `status: {claim.status.value}`
for every open claim. The *filter* is correct (`open_claims_for_planner`
uses `compute_signal`). The LLM therefore sees create-time `proposed`
on claims that may already be `contested` on the validation axis
(grounding is rendered honestly beside it). Not a ComputeDebit leak —
those claims are still open work. Accuracy of the prompt, not of the
predicate.

---

## Files >500 LOC

Line counts from `wc -l` on `1097120`. R2 counts (on `80495c0`) in
parentheses where they moved.

### Backend

| LOC | Δ vs R2 | File | Split recommendation |
| ---: | ---: | --- | --- |
| **990** | +36 | `backend/app/services/agent_runs.py` | Still the split from R1: `commission.py` / `branch_select.py` / `execute_pass.py`. The +36 is `_TRACE_DISPLAY_KEYS` / `_trace_display_output` / `_invocation_output` / `_executed_step` output. Openness lives in `claims.open_claims_for_planner` — do not fork a second predicate when splitting. |
| **786** | 0 | `backend/app/services/orchestration.py` | `eligibility.py` / `wave_executor.py` / `lifecycle.py`. `_policy_from_reservation` takes the quote; keep that signature when moving. |
| **726** | 0 | `backend/app/services/campaigns.py` | `lifecycle.py` vs `cycle_wave.py`. |
| **642** | 0 | `backend/app/services/diff.py` | `resolve_ref.py` vs `delta_build.py`. Shared ancestry with `blame.py` still worth extracting. |
| **522** | 0 | `backend/app/toolbench/instruments/_lean_support.py` | Mathlib / `lake` vs prelude stub. |
| **514** | 0 | `backend/app/toolbench/instruments/_interval_support.py` | Enclosure engine vs relation decision. Lower priority. |

### Frontend

| LOC | Δ vs R2 | File | Split recommendation |
| ---: | ---: | --- | --- |
| **1421** | 0 | `frontend/src/components/workspace/toolbench/drive-forms.tsx` | **Highest remaining frontend maintainability risk.** One file per instrument form + a thin registry. |
| **1337** | 0 | `frontend/src/components/workspace/toolbench/result-view.tsx` | Per-instrument bodies still belong in their own files. `resolveOutcomeMeta` already extracted (`outcome.ts`, 229). |
| **628** | 0 | `frontend/src/types/research.ts` | `claim.ts` / `ledger.ts` / `membership.ts`; barrel-re-export. |
| **566** | 0 | `frontend/src/components/workspace/project-workspace.tsx` | Tab panel / rollup / budget / instrument-context into `project-workspace-parts/`. |
| **547** | 0 | `frontend/src/components/workspace/branch-bar.tsx` | Line selector vs close/merge modals vs merge form. |

Approaching the line: `claim-list-panel.tsx` (489), `lib/api.ts` (457),
`agent-run-trace.tsx` (409). Split `claim-list-panel` when touching
P2-3.

These splits are **not** a reason to start another assessor loop.
They are the next maintainability PRs after CI exists.

---

## Test / CI gaps that hide bugs

1. **Default pytest is still not a ledger gate.** This run: `664
   passed, 222 skipped`. The tests that lock P0-1, P1-1, P2-9, and the
   repaired write-path suite skip without Postgres.
2. **No `.github/workflows`.** Unchanged from R1/R2. If CI is added,
   the useful job is `TEST_DATABASE_URL=… pytest` against a throwaway
   Postgres. The write-path stubs (P2-10) are the reason that job can
   now be green on day one — it has not been proven in this
   environment.
3. **Browser eyeball pass** still owed. Would confirm P2-8 chrome
   live, and would still catch P2-2 / P2-3.
4. **`tests/conftest.py` localhost guard** on implicit `DATABASE_URL`
   is still correct and must stay.

---

## Drift vs `docs/blueprints`

Blueprints match the code on the primitives that matter. The
membership paragraph added to `primitives.md` in `0.36.1` is
accurate.

Remaining drift that will cause wrong *assistant* behavior (not
runtime):

| Doc | Drift | Effect |
| --- | --- | --- |
| `schemas/branch.py:14` | Acting actor described as `X-Dev-Actor-Id` | Assistants reading the schema re-learn the 0.3.x header. P2-12. |

`docs/plans/roadmap-next-steps.md` correctly says `0.36.1` / `0.36.2`
are stacked branches, not `main`. Keep that banner until `#23` / `#25`
merge.

`docs/changelog.md` index lines for `0.36.1` / `0.36.2` match this
tip. Do not claim either on `main` until the stacked PRs merge.

---

## Prioritized remediation

**Stop the assessor bug-fix loop.** There is no P0 and no functional
P1 on this tip. The next work is ordinary product PRs, one concern
each:

| # | PR | Closes | Notes |
| ---: | --- | --- | --- |
| **1** | GitHub Actions: ruff + pytest **with Postgres** + frontend typecheck/lint/build | P2-5 | Makes P0-1 / P1-1 / P2-8–P2-10 stay closed. The write-path stubs are already honest. |
| **2** | Naming / confidence chrome / route-to-service / poll hook / `BranchCreate` docstring / planner prompt `status` | P2-1–P2-4, P2-6, P2-12, P2-13 | After the test gate. Hide or relabel `{claim.status}` with the confidence chip. |
| **3** | Split remaining >500 LOC files (`drive-forms`, `result-view`, `agent_runs`, `orchestration`, `campaigns`, `diff`) | Large-file flag | Only after behavior is covered by CI. |

Do not start a “cleanup” PR that mixes CI, file splits, and chrome.
Do not open a fourth assessor round to rediscover P2-1–P2-7.

The dual-fork race (P2-7) stays accepted for v1.

---

## R1 → R2 → R3 scoreboard

| ID | R1 | R2 | R3 |
| --- | --- | --- | --- |
| P0-1 membership on original ledger POSTs + UI `canWrite` | P0 | **Closed** | **Closed** |
| P1-1 planner open-claims via `compute_signal` | P1 | **Closed** | **Closed** (residual P2-13: prompt text) |
| P1-2 `ClaimCreate` forbids `status` / `confidence` | P1 | **Closed** | **Closed** |
| P1-3 agent-trace uses `resolveOutcomeMeta` | P1 | **Closed** (residual P2-8: empty output) | **Closed** |
| P1-4 proof/satisfy fallthrough → warn | P1 | **Closed** | **Closed** |
| P1-5 CLAUDE.md / deploy.md auth | P1 | **Closed** | **Closed** |
| P1-6 reservation quote for mid-pass policy | P1 | **Closed** | **Closed** |
| P2-8 agent-trace dropped output | — | P2 | **Closed** |
| P2-9 `ThreadCreate` client `status` | — | P2 | **Closed** |
| P2-10 write-path stub named `calc.eval` | — | P2 | **Closed** (code/tests; DB suite not re-run) |
| P2-11 `ValidationCreate` docstring | — | P2 | **Closed** |
| P2-1–P2-7 | P2 | **Open** | **Open** (deferred) |
| P2-12 `BranchCreate` docstring | — | — | **Open** (sibling of P2-11) |
| P2-13 planner prompt prints `Claim.status` | — | — | **Open** (sibling of P1-1) |

---

## Go / no-go

**No-go on further functionality-bug remediation loops.**

The ledger core held across three assessor rounds. The one P0
(membership) and the six P1s are closed on this tip. The three R2
bug-like residuals are closed. Remaining work is P2 maintainability
(CI, file size, naming, chrome) plus two one-line residuals.

Merge the stacked PRs (`#23` then `#25`; `#24` is the R2 doc) when
ready. A Postgres CI job is the highest-value *next* change — it is
how the closures stay closed — but it is not a reason to run R4 as
another assessor pass.
