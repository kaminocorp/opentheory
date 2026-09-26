# Codebase assessment R1 — 2026-09-26

> Assessed against `origin/main` at `71a8929` (`0.36.0` — research-git blame).
> Scope: functionality, accuracy, maintainability, clean code. Nice-to-haves omitted.
> OpenTheory hard invariants treated as P0 when violated.

## Executive summary

The ledger core is sound. Append-only guards, the `create_checkpoint` chokepoint,
the instrument failure-split, Account ≠ Actor on funding, and
funder ≠ contributor ≠ validator in the *data model* all hold. Agents, campaigns,
and orchestrations never write `Validation` or `FundingAllocation`. New 0.33–0.36
surfaces (`z3.satisfy`, Bench 6 tables/plots, `interval.eval`, blame) compose
through the same write path or mint nothing.

The one P0 is authorization drift: research writes that shipped before
`ensure_is_member` (0.8.1 / 0.9.2) are still “any authenticated principal may
mutate any project,” and the UI enables those writes for any signed-in user.
The backend does **not** authorize those writes even if the frontend is
bypassed — a prime-directive miss.

| Severity | Count | Theme |
| --- | ---: | --- |
| **P0** | 1 | Membership missing on core ledger writes (backend + UI) |
| **P1** | 6 | Agent open-claim filter on a dead column; client-stamped `Claim.status`; honesty chrome; assistant/ops auth drift; reservation rate drift |
| **P2** | 7 | Naming, naked confidence, fat route, no CI, documented races, duplicate poll |

**What this assessment did *not* find:** a second checkpoint writer, an
append-only bypass in `app/`, a `parse_expr` call that skips
`_reject_unsafe_source`, an agent that self-validates or self-funds, or a
frontend `fetch` that bypasses `lib/api.ts`.

---

## What was run / what was not

| Check | Result |
| --- | --- |
| `cd backend && uv run ruff check .` | Clean |
| `cd backend && uv run pytest -q` | **634 passed, 220 skipped** (no `TEST_DATABASE_URL`) |
| `cd frontend && npm run typecheck` | Pass |
| `cd frontend && npm run lint` | Pass |
| `cd frontend && npm run build` | Pass (Next.js 15.5.15) |
| DB-backed ledger / toolbench / agent suite | **Not run** — no Postgres in this environment. Those are the tests that would have caught P0/P1-2 if they existed. |
| Browser eyeball pass | **Not run** — still owed per `docs/plans/roadmap-next-steps.md`. |

---

## Hard invariants — verdict

| Invariant | Verdict |
| --- | --- |
| Append-only: Checkpoint / CheckpointRef / FundingAllocation / Validation / ComputeDebit / Tag | **Holds.** Guards in `models/append_only.py:38–45`. No bulk Core `UPDATE`/`DELETE` on those tables in `app/`. |
| Single write chokepoint: only `create_checkpoint` mints `Checkpoint` | **Holds.** Sole `Checkpoint(` in app code: `services/checkpoints.py:291`. Composing flows (`validations`, `branches`, `merges`, `tags`, `tool_runs`) `db.add` then call the chokepoint; they do not commit first. |
| Backend owns domain invariants; thin routes → services | **Mostly holds.** Routes are thin except project PATCH (P2). **Authorization** for pre-0.9 research writes is missing (P0). |
| Instruments: `result` \| `refuted` \| `undecided`; exceptions mint nothing | **Holds** on the write path (`services/tool_runs.py:172–206` runs before any `db.add`). UI honesty has two localized chrome bugs (P1). |
| Account ≠ Actor; funder ≠ contributor ≠ validator | **Holds in the model.** Funding attributes money to `actor.account_id` (`services/funding.py:111–116`) and records a `fund` contribution with `checkpoint_id=None`. Compute debit never writes `FundingAllocation`. Agent/campaign/orchestration never write `Validation` or `FundingAllocation`. |
| `docs/` source of truth; code wins on conflict | Blueprints match the ledger. **CLAUDE.md and `docs/operations/deploy.md` still say there is no auth** (P1) — that will produce wrong code and wrong ops. |
| CONTRIBUTION-GUIDELINES.md | Prime directives 1–2, 4–6 hold. Directive 3 + “writes are membership-gated (`ensure_is_member`)” is violated on the original ledger POSTs (P0). |

Intentional non-findings (do not “fix”):

- Thread / claim / evidence creates do **not** auto-mint a checkpoint (`services/checkpoints.py:9–10`, plan Decision #3).
- Funding is contribution-only, not a research checkpoint (`services/funding.py:3–7`).
- Agent / campaign / orchestration own their own commits for *mutable traces*; each ledger write still goes through `run_instrument` → `create_checkpoint`.

---

## P0 findings

### P0-1 — Any authenticated principal can write another project's ledger

**Where**

Backend research POSTs that authenticate via `ActingActor` and then delegate
with **no** `ensure_is_member` / `ensure_can_manage`:

| Route | Symbol |
| --- | --- |
| `POST /projects/{id}/checkpoints` | `api/routes/checkpoints.py:18–24` |
| `POST /threads/{id}/claims` | `api/routes/claims.py:18–24` |
| `POST /projects/{id}/validations` | `api/routes/validations.py:18–24` |
| `POST /projects/{id}/threads` | `api/routes/threads.py:19–25` |
| `POST /claims/{id}/evidence` | `api/routes/evidence.py:18–24` |
| `POST` branch / close | `api/routes/branches.py:24–30`, `52–58` |
| `POST /projects/{id}/merges` | `api/routes/merges.py:18–24` |
| `POST /projects/{id}/tags` | `api/routes/tags.py:18–24` |
| `POST /projects/{id}/funding` | `api/routes/funding.py:18–26` (internal-gated only) |

Contrast — later surfaces *do* gate:

- `api/routes/instruments.py:68`
- `api/routes/agent_runs.py:56`
- `api/routes/orchestrations.py:44`
- `api/routes/campaigns.py:42`

The gate already exists: `services/project_members.py:95–113`
(`ensure_is_member` — research writes, no `FOR UPDATE` project lock).

Frontend makes the hole reachable without `curl`:

- `canWrite` is “signed in + `/me` resolved,” **not** membership — `frontend/src/lib/use-identity.ts:53`.
- Claim / evidence / checkpoint / validation / thread / branch / tag forms all key off `canWrite` (e.g. `claim-list-panel.tsx:77–101`, `validation-controls.tsx:59–82`, `checkpoint-timeline-panel.tsx:46–91`).
- `project-workspace.tsx:81–88` comments that “the backend still authorizes every write.” That is true for instruments / agent / campaign, **false** for the ledger POSTs above.

**Why it matters**

CONTRIBUTION-GUIDELINES: *“Public reads are public; writes are membership-gated
(`ensure_is_member`).”* Prime directive 3: the backend enforces invariants even
if the frontend is bypassed. A signed-in non-member can today:

- mint checkpoints and tags on any project they can guess the UUID of
- propose claims and attach evidence
- **record a `Validation`** (passed / retract / contradicts) on someone else's claim — that is a validator acting without being invited
- fork, close, or merge branches

Attribution still lands on their Actor, so the ledger is coherent but
**wrong relative to the 0.8.1 membership model**. Project UUIDs are in
shareable `?tab=` / `?thread=` URLs (`0.31.0`).

Funding is a sibling: native funding requires `internal` (`funding.py:98–103`)
but not membership. That may be intentional (platform comps any project); say
so in the fix or add the member check.

**Suggested fix**

1. Call `ensure_is_member(db, project_id, actor)` on every research write
   route. For nested paths (`/threads/{id}/claims`, `/claims/{id}/evidence`,
   `/branches/{id}/close`) resolve `project_id` from the loaded row *before*
   authorizing, then act.
2. Do **not** put the gate only in the UI. Services should own it (or a shared
   dependency the route always declares) so `curl` cannot skip it.
3. Align `canWrite` with membership on a project surface (pass
   `canManageProject` / a new `isProjectMember` into the write forms), so the
   comment at `project-workspace.tsx:81` becomes true.
4. Add DB-free or DB-backed `403` tests mirroring
   `tests/agent/test_agent_runs_api.py` and `tests/toolbench/test_instruments_api.py`
   for checkpoint / claim / validation / branch / merge / tag / thread / evidence.

---

## P1 findings

### P1-1 — Agent and orchestrator treat `Claim.status` as settlement; nothing ever writes it

**Where**

```94:104:backend/app/services/agent_runs.py
async def _open_claims(db: AsyncSession, thread_id: UUID) -> list[Claim]:
    ...
            Claim.status.notin_(_SETTLED_CLAIM_STATUSES),
```

Same filter: `services/orchestration.py:136–145` with
`_SETTLED_CLAIM_STATUSES = (ClaimStatus.RETRACTED, ClaimStatus.VALIDATED)`
(`agent_runs.py:69`, `orchestration.py:66`).

`Claim.status` defaults to `proposed` (`models/claim.py:27–31`). Grep of
`app/` finds **no** assignment of `ClaimStatus.VALIDATED` or `RETRACTED`.
`compute_signal` is explicit that it does **not** mutate stored status
(`services/claims.py:20–28`, `schemas/claim.py:10–14`).

Orchestration then applies a *second* filter on grounding
(`claim_is_raisable`, `orchestration.py:97–99`, `183–191`) — evidence axis
only. A human `Validation(outcome=passed)` therefore:

- flips display `signal` to `validated`
- leaves `Claim.status == proposed`
- stays in the planner's open set
- stays “open work” for `SKIP_NO_OPEN_CLAIMS`

**Why it matters**

The agent spends `ComputeDebit` re-working claims a validator already settled.
The two-axis design is correct (do not merge signal + grounding into a score);
the bug is using a **dead column** as the openness predicate instead of
`compute_signal` / grounding headlines.

**Suggested fix**

Replace the status filter with the same derivations the read model already
owns: batch `validations_by_claim` + `compute_signal`, and keep
`claim_is_raisable` for the evidence axis. Decide product-explicitly whether
`signal == "validated"` excludes a claim from the planner (recommended: yes
for “open work”; grounding still decides *raisable*). Add a test:
validation-only settlement → claim absent from `_open_claims`.

Do **not** silently ORM-update `Claim.status` on validation — that would stamp
a derived signal and recreate the naked-score problem.

### P1-2 — `ClaimCreate` lets a client stamp `status` (and a naked `confidence`)

**Where:** `schemas/claim.py:94–104` — `ClaimCreate` inherits `ClaimBase`,
which includes `status: ClaimStatus = PROPOSED` and `confidence`.
`create_claim` dumps the payload onto the ORM (`services/claims.py:86–90`).

The UI does not send `status` (`frontend/src/types/research.ts` `ClaimCreate`
omits it; `claim-list-panel.tsx:89` sends `{ kind, statement }`). The API
does.

**Why it matters**

A `curl` can create `status=validated` with no `Validation` row. Combined with
P1-1, the agent then *skips* that claim. Or `status=proposed` + a later
validation is ignored (P1-1). `confidence` is a client-supplied score the
read model also echoes — the second axis `primitives.md` forbids treating as
truth.

**Suggested fix**

Drop `status` and `confidence` from `ClaimCreate` (keep them on `ClaimRead` if
the column stays). If create-time confidence is still wanted, name it
`stated_confidence` and never let it drive the planner.

### P1-3 — Agent-pass step pills use generic `outcomeMeta`, not instrument-honest chrome

**Where:** `frontend/src/components/workspace/agent-pass/agent-run-trace.tsx:65–71`
(`LandedStep` → `outcomeMeta(step.outcome)`).

`outcomeMeta("result")` is tone `ok` (`toolbench/outcome.ts:25–28`).
`ResultView.resolveOutcomeMeta` (`result-view.tsx:1195–1340`) downgrades
several `result` cases (counterexample with `found: false`; table relation
that only holds on the finite table; proof instruments that are not
`proven === true`).

**Why it matters**

Honesty rule: undecided / weak support must never read as a pass. The result
card is careful; the agent trace — the surface operators watch while a pass
runs — is not.

**Suggested fix**

Extract `resolveOutcomeMeta` from `result-view.tsx` into
`toolbench/outcome-meta.ts` and reuse it in `LandedStep` (needs
`step.instrument` + parsed invocation output, or a display hint recorded on
the step).

### P1-4 — `resolveOutcomeMeta` fallthrough can paint a proof `result` as a pass

**Where:** `result-view.tsx:1211–1233` (`z3.prove`), `1257–1278` (`lean.prove`),
`1234–1255` (`z3.satisfy`), then `return outcomeMeta(status)` at `:1340`.

Special cases only fire when `status === "result" && output.proven === true`
(or satisfy `satisfied === true`). Any other `status === "result"` on those
instruments becomes generic **Result / ok**, while `Z3ProveBody` /
`LeanProveBody` render `UndecidedCard` / `FailedProofCard`.

**Why it matters**

Pill vs body disagreement. If a blame tuple is lenient-read (missing
`proven`), the chrome lies.

**Suggested fix**

Default fallthrough for proof / satisfy instruments: **warn / Undecided**.
Only emit `ok` when the machine-checked flag is true.

### P1-5 — Assistant contract and deploy runbook still say there is no auth

**Where**

- `CLAUDE.md:68` — *“There is no auth yet (real identity is planned for `0.6.0`)”*;
  acting actor described as `X-Dev-Actor-Id` only.
- `docs/operations/deploy.md:7–10` — *“No authentication yet… anyone with the
  URL can read and write.”*
- `CONTRIBUTION-GUIDELINES.md` (and `api/deps.py:150–189`) correctly describe
  JWT → Account → human Actor, with the dev header behind
  `auth_dev_header_enabled` (default **False**, `core/config.py:40`).

CONTRIBUTION-GUIDELINES.md itself says divergence between it and `CLAUDE.md`
is a bug.

**Why it matters**

An assistant following `CLAUDE.md` will wire writes to a header that
production rejects, or will assume the live API is open. An operator
following `deploy.md` will treat a publicly reachable Fly app as an accepted
preview hole. Auth shipped in `0.6.0`; Account-owns-Actor in `0.7.0`.

**Suggested fix**

Rewrite the acting-actor paragraph in `CLAUDE.md` to match
`api/deps.py` / the guidelines. Replace the deploy.md banner with: production
requires a verified bearer; `X-Dev-Actor-Id` is local/test only; writes are
membership-gated (**once P0-1 lands**).

### P1-6 — Orchestrator mid-pass budget policy uses the blended catalog rate, not the live quote

**Where**

- Reserve path uses `quote_model_price` → `quote.effective_rate_per_1k`
  (`orchestration.py:597–612`).
- `_policy_from_reservation` (`orchestration.py:575–581`) builds
  `ProjectBudgetPolicy(..., rate_per_1k=compute_service.rate_for_model(agent_run.model))`
  — the static catalog / settings blend, **not** the quote that sized the hold.

Standalone `run_agent_pass` does this correctly: same `price_quote` for
reserve, policy, and debit (`agent_runs.py:359–378`).

**Why it matters**

`ProjectBudgetPolicy.check` can stop early or run long relative to the
reserved slice and the `ComputeDebit` snapshot (`0.28.0`). Concurrent
sub-passes (`0.27.0`) are the blast radius.

**Suggested fix**

Persist the effective rate (or the quote source) on the `AgentRun` at reserve
time, and have `_policy_from_reservation` read that. Or pass the quote
through. Do not re-derive from `rate_for_model`.

---

## P2 findings

### P2-1 — `ensure_can_manage` / `canManageProject` mean “any member,” comments say owner/admin

`ensure_can_manage` (`project_members.py:52–92`) 403s only when there is no
membership row, unless `require_owner=True`. Today's `ProjectRole` is only
`owner` | `admin`, so “any member” ≈ “owner/admin” — until a lower-privilege
role is added. Frontend `canManageProject` (`project-workspace.tsx:87–88`) and
the header comment (`project-header.tsx:76–77`) encode the wrong name.

**Fix:** Rename to `isProjectMember` / `canRunResearchWrites`. If metadata
edit is truly owner/admin-only, check `role` on both sides.

### P2-2 — Auth menu labels a non-internal account “Contributor”

`frontend/src/components/shell/auth-menu.tsx:164–165`. That word is a credit
role (`Contribution`), not an account posture. Use “Signed in” / “Member” /
“External account.”

### P2-3 — Claim rows still render a bare confidence percentage

`claim-list-panel.tsx:218–224` — `{Math.round(claim.confidence * 100)}%` next
to the statement, beside (but visually competing with) `GroundingChip` and
validation signal. `primitives.md` forbids a naked score as confidence.

**Fix:** Hide the field, or label it “stated at create — not grounding.”

### P2-4 — Project metadata PATCH mutates in the route

`api/routes/projects.py:54–69` (`update_project`) and `:74–88`
(`set_project_agent_models`) authorize then `setattr` / assign + `commit` in
the handler. Docstring claims “authorization is enforced in the service.”
Project is not append-only, so this is not a ledger bug — it is the one
fat-route exception to “services own domain.”

**Fix:** Move the patch into `services/projects.py`.

### P2-5 — No repository CI workflows

There is no `.github/` tree. Vercel builds the frontend on deploy; Fly does
not run `ruff` / `pytest`. The contribution contract
(`ruff` + `pytest` + `typecheck` + `lint` + `build`) is honor-system.

A default `pytest` is **634 passed / 220 skipped**. Completions docs
repeatedly record that green-but-hollow number. Ledger / toolbench / agent
regressions (including P0-1 and P1-1) are invisible in CI even if a workflow
is added, unless it provisions Postgres and sets `TEST_DATABASE_URL`.

### P2-6 — Duplicate in-flight agent-run polling; `visitedTabs` mutated during render

- `project-workspace.tsx` and `agent-pass-panel.tsx` both poll
  `queryKeys.agentRuns` / `getAgentRun` (TanStack dedupes the network; interval
  / `enabled` can still drift).
- `project-workspace.tsx` adds to `visitedTabs.current` during render
  (React concurrent/Strict Mode footgun).

**Fix:** one `useThreadAgentPassLive` hook; move the set-add into `useEffect`.

### P2-7 — Documented dual-fork race on concurrent agent passes

`services/agent_runs.py:124–129`: two near-simultaneous commissions on the
same thread can each miss the other's `branch_id` and fork two open agent
lines. Non-destructive (next pass reuses the newest). Accepted for v1; still
the reason a durable queue is on the roadmap. Not a fix-now unless you are
already in `agent_runs.py` for P1-1.

`extra_refs` remain trusted by design (`checkpoints.py:234–237`). Keep them
server-only — a future compose helper that forwards client JSON as
`extra_refs` would bypass `_validate_refs`. No current violation.

---

## Files >500 LOC

Line counts from `wc -l` on `71a8929`.

### Backend

| LOC | File | Split recommendation |
| ---: | --- | --- |
| **965** | `backend/app/services/agent_runs.py` | `commission.py` (`start_agent_pass`, stale sweep), `branch_select.py` (`select_agent_branch`, `_open_claims`), `execute_pass.py` (plan → observe → replan + instrument steps). Do this in the same PR as P1-1 so the new openness predicate has one owner. |
| **780** | `backend/app/services/orchestration.py` | `eligibility.py` (`classify_*`, skip reasons), `wave_executor.py` (`_commission_reserved_pass`, `_run_wave`), `lifecycle.py` (start / cancel / sweep). Pull `_policy_from_reservation` with P1-6. |
| **726** | `backend/app/services/campaigns.py` | `lifecycle.py` vs `cycle_wave.py`. |
| **642** | `backend/app/services/diff.py` | `resolve_ref.py` (token → checkpoint + ancestry) vs `delta_build.py` (claim / signal / grounding / instrument deltas). Blame (`services/blame.py`, 399) already reuses the walk — a shared ancestry module would stop a third copy. |
| **522** | `backend/app/toolbench/instruments/_lean_support.py` | Isolate Mathlib / `lake` bridge from the prelude stub if Lean work continues. |
| **514** | `backend/app/toolbench/instruments/_interval_support.py` | Optional: enclosure engine vs relation decision. Lower priority than the service splits. |

### Frontend

| LOC | File | Split recommendation |
| ---: | --- | --- |
| **1486** | `frontend/src/components/workspace/toolbench/result-view.tsx` | **Highest frontend maintainability risk.** Per-instrument bodies (`z3-prove-body.tsx`, `interval-eval-body.tsx`, `table-body.tsx`, `plot-body.tsx`, …), shared cards, and **export `resolveOutcomeMeta`** (P1-3 / P1-4). 0.33–0.35 added ~570 lines here. |
| **1421** | `frontend/src/components/workspace/toolbench/drive-forms.tsx` | One file per instrument form + a thin registry/dispatch. 0.33–0.35 added ~536 lines. Honesty copy will keep rotting if every new instrument lands in this switch. |
| **629** | `frontend/src/types/research.ts` | Split `claim.ts` / `ledger.ts` / `membership.ts`; barrel-re-export. |
| **566** | `frontend/src/components/workspace/project-workspace.tsx` | Tab panel / rollup / budget / instrument-context into `project-workspace-parts/`. Orchestrator should only own URL + query wiring. |
| **544** | `frontend/src/components/workspace/branch-bar.tsx` | Line selector vs close/merge modals vs merge form. |

Approaching the line (not over): `claim-list-panel.tsx` (489), `lib/api.ts` (457),
`agent-run-trace.tsx` (408). Split `claim-list-panel` when touching P2-3.

---

## Test / CI gaps that hide bugs

1. **Default pytest is not a ledger gate.** This run: `634 passed, 220 skipped`.
   CONTRIBUTION-GUIDELINES already warn about this. P0-1 and P1-1 have **no**
   covering test even in the skipped set (no non-member `403` on
   checkpoint/claim/validation; no “validation settles `_open_claims`”).
2. **No `.github/workflows`.** Nothing runs `ruff` / `pytest` / `typecheck` /
   `lint` on a PR. If CI is added, the useful job is
   `TEST_DATABASE_URL=… pytest` against a throwaway Postgres — the DB-free
   job alone will stay green while P0-1 ships.
3. **Grounding / agent DB-gated round-trips** have been recorded as unrun
   across several completions (`0.16.0` eight read-model tests; orchestrator
   yield tests). Still true here.
4. **No membership tests on the original write surface.** Instrument / agent /
   campaign / orchestration API tests *do* assert `403` for a non-member.
   That inconsistency is how P0-1 survived four release lines after `0.8.1`.
5. **Browser eyeball pass** still owed (`roadmap-next-steps.md`). Not a
   correctness gate for this assessment; it would have caught P1-3 chrome.

`tests/conftest.py` localhost guard on implicit `DATABASE_URL` is correct
and must stay — the suite `DROP SCHEMA public CASCADE`s.

---

## Drift vs `docs/blueprints` (only if it causes wrong behavior or debt)

Blueprints (`primitives.md`, `conceptual-model.md`, `techstack.md`) match the
code on the primitives that matter: append-only set, Account-owns-Actor,
ComputeDebit ≠ FundingAllocation, blame as a derived read that mints nothing.

Drift that *will* cause wrong behavior:

| Doc | Drift | Effect |
| --- | --- | --- |
| `CLAUDE.md:68` | “No auth yet”; acting actor is `X-Dev-Actor-Id` | Assistants implement the 0.3.x header path; production is JWT. See P1-5. |
| `docs/operations/deploy.md:7–10` | “No authentication yet… anyone with the URL can write” | Operators treat a live Fly app as an accepted open write. Auth has been on since `0.6.0`. See P1-5. |
| `CLAUDE.md:9` | “Agents are a future `Actor` type” | Agents are a shipped `Actor` type (`0.12`+) using the same APIs. Not a runtime bug; it steers new work toward a parallel model the prime directives forbid. |

`docs/plans/roadmap-next-steps.md:25` still says `0.36.0` is “this branch, not
`main`.” Cosmetic; `71a8929` *is* `main`. Fix when someone is already in that
file.

`docs/blueprints/primitives.md` does not mention project membership. The
0.8.1 model lives in changelog / `project_members.py`. Worth a short
“authorization is membership, not credit” paragraph so the next writer does
not re-learn P0-1 from the blueprint alone — **after** the code fix.

---

## Prioritized remediation (next fix PR)

One concern per PR. Suggested order:

| # | PR | Closes | Notes |
| ---: | --- | --- | --- |
| **1** | Membership on every research write + UI `canWrite` aligned + `403` tests | P0-1 | Highest blast radius. Do not fold in refactors. Funding membership: decide explicitly. |
| **2** | Open-claim selection from `compute_signal` + grounding; strip `status` from `ClaimCreate` | P1-1, P1-2 | Needs the DB-backed suite. Optional first split of `agent_runs.py` if the file is already open. |
| **3** | Extract `resolveOutcomeMeta`; use it in the agent trace; proof fallthrough → warn | P1-3, P1-4 | Natural moment to start splitting `result-view.tsx` / `drive-forms.tsx`. |
| **4** | Rewrite `CLAUDE.md` acting-actor + `deploy.md` auth banner; note agents are shipped | P1-5 | Docs-only, can ship in parallel with #1. |
| **5** | Reservation policy uses the same quote as the hold / debit | P1-6 | Small, isolated, needs agent DB tests. |
| **6** | GitHub Actions: ruff + pytest (with Postgres service) + frontend typecheck/lint/build | P2-5 | Makes #1–#2 stay closed. |
| **7** | Naming / confidence chrome / route-to-service move / poll hook | P2-1–P2-4, P2-6 | After the functional holes. |
| **8** | Split remaining >500 LOC service files (`orchestration`, `campaigns`, `diff`) | Large-file flag | Only after #2 / #5 so behavior is stable. |

Do not start a “cleanup” PR that mixes membership, planner filters, and a
1400-line frontend split. The membership hole is the one that is live.
