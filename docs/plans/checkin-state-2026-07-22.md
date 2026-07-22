# Platform check-in — 22 Jul 2026

> **Snapshot of current state** after `0.12.x` (thin agent loop) and the open-source
> readiness pass (`0.12.7`–`0.12.8`). Not a roadmap commitment; for what's *next*, see
> `docs/plans/roadmap-next-steps.md` and `docs/changelog.md`.

**Version:** `0.12.8` · **Deploy:** live (Fly backend · Vercel frontend · Supabase Postgres)

---

## Bottom line

OpenTheory is a **live, human-operable research ledger** with a **deterministic math
toolbench**, a **bounded (dark-launched) agent pass**, and real auth/collab — *not* yet
an autonomous research engine.

**Analogy:** the **lab notebook, instruments, and a technician who can run a short
recipe when asked** are real. The **PI that runs the program continuously**, the
**library of papers**, the **proof assistant**, and the **finance office that meters
the grant** are not.

---

## What it can do already

### Research ledger (core product — solid)

| Capability | Status |
| --- | --- |
| Projects, threads, claims, evidence | ✅ |
| Immutable **checkpoints** (commit-shaped) through a single chokepoint | ✅ |
| **Branches** — fork, work in parallel, close as dead-end / superseded | ✅ |
| **Validations** — re-assessments as *new* rows (never edits) | ✅ |
| Append-only enforced at the ORM layer | ✅ |
| Timeline / log / show + contribution attribution | ✅ |
| Claim signal / contradiction-ish read models | ✅ |

### Identity, access, collab

| Capability | Status |
| --- | --- |
| Supabase auth (email/password + JWT, ES256/JWKS) | ✅ |
| `Account` owns principal; `Actor` owns research provenance | ✅ |
| Project ownership, members, roles | ✅ |
| Invite by `@username` or email; inbox accept/decline | ✅ |
| Public **read-only** without sign-in; writes require auth | ✅ |

### Toolbench (honesty model)

Five production instruments, all landing attributed checkpoints through the same
chokepoint:

| Instrument | Does |
| --- | --- |
| `calc.eval` | Exact symbolic/numeric evaluation (SymPy) |
| `expr.compare` | Expression equivalence — refutes only on a *provably* non-zero difference |
| `geometry.coordinate_measure` | Exact coordinate geometry (flagship *across a corner*) |
| `counterexample.search` | Deterministic grid search for a falsifying witness |
| `oeis.search` | Integer sequence ID with a *pinned* citation |

Also shipped: KaTeX rendering, assumptions on the blame line, execution sandbox
(subprocess isolation, wall-clock / memory caps, concurrency limit).

**Contract:** failed runs mint nothing; `undecided` is never a pass; `refuted` only
when the instrument can prove it.

Flagship *measuring across a corner* (claims 1–4) is walkthrough-ready. Claim 5
(Lean → Grade A) remains out of scope.

### Thin agent loop (`0.12.x` — built, dark by default)

- A project member commissions **one bounded pass** on a thread.
- Planner (OpenRouter) returns a capped plan of *existing* instrument runs.
- An agent `Actor` lands results on a durable **agent branch** via the same
  `run_instrument` path humans use — no parallel write model.
- Pollable `AgentRun` trace; human review via reject / fork / validate paths.
- **Off in prod until** `AGENT_LOOP_ENABLED=true` + `OPENROUTER_API_KEY`.

Still bounded, not autonomous: no continuous/scheduled loop, no multi-thread
orchestrator, no project-budget metering yet.

### Product shell

OpenTheory Console UI, stewardship, Research crew model assignment (UI + pass
consumption), funding *recorded* (native / `internal` only — not settlement).

### Shipped milestones (reference)

| Release | What landed |
| --- | --- |
| `0.3.x` | Human-operable ledger write path + workspace |
| `0.4.x` | Validation, branching, enriched read models |
| `0.6.x`–`0.7.x` | Auth, `Account`/`Actor`, funding allocations, live deploy |
| `0.8.x` | Console, stewardship, `@username`, invitations, Research crew UI |
| `0.9.x` | Toolbench spine, instruments, drive/show UI, security hardening |
| `0.10.x` | `counterexample.search`, LaTeX companions, KaTeX — flagship 1–4 ready |
| `0.11.x` | Execution sandbox |
| `0.12.x` | Thin agent loop — planner, orchestrator, `202`+trace API, workspace UI |

---

## What it cannot do (yet)

### Not an autonomous research engine

| Gap | Reality today |
| --- | --- |
| Continuous / scheduled research | ❌ Human must commission each pass |
| Multi-thread / multi-agent project orchestrator | ❌ Single-thread, single pass |
| Plan → observe → replan loops | ❌ One planning call, then deterministic execution |
| Project **budget metering** that stops work when compute is spent | ❌ Per-pass safety caps only (`0.12.5` deferred); token budgets recorded, not enforced against funding |
| Agents that self-validate or fund | ❌ Deliberately separated roles |

### Research-git incomplete

| Op | Status |
| --- | --- |
| commit / branch / log | ✅ built |
| blame (data on checkpoints) | 🟡 *recorded* (blame tuple on every tool run); semantic `blame` op planned |
| merge / semantic diff / tag | ⬜ planned |
| Content-addressed checkpoint IDs | ⬜ UUIDs today |

### Research flow is optional metadata, not law

Stages (`decompose → hypothesize → formalize → design → execute → validate → integrate`)
exist on the enum and may sit on a checkpoint, but **nothing enforces** the skeleton.
No stage executors, no auto-advance, no integrate-into-project-belief step.
See `docs/vision/research-flow.md` (design intent, not current build).

### Tool surface is narrow

| Missing | Why it matters |
| --- | --- |
| Literature pins (Crossref / arXiv / OpenAlex) | Only OEIS for retrieval |
| Z3 / SMT | Machine-checked unsat / counterexamples without Lean |
| Lean / formal proofs | Claim 5 / Grade A out of scope |
| Interval arithmetic, tables, plots | Stretch / later benches |
| Object storage for large artifacts | Metadata/hashes only in Postgres |

### Product / economic layer unfinished

| Gap | Reality |
| --- | --- |
| Real funding / Stripe settlement | Allocations recorded only |
| Reputation / influence | Vision only — no data model |
| Demo seed projects | Explicitly deprioritized |
| Agent loop always-on in prod | Dark-launched |

### Known sharp edges

- Concurrent first agent passes on the same thread can fork **two** agent branches
  (no DB-level uniqueness guard).
- Token ceiling is **recorded**, not enforced (until `0.12.5`-class work).
- Some ops docs lag auth reality (`docs/operations/deploy.md` still describes a
  pre-`0.6` open posture in places).

---

## Main gaps → fully autonomous research engine

Ordered by how blocking they are for the *vision* (continuous agents that compound
knowledge under budget):

### 1. Autonomy spine *(biggest product gap)*

- Scheduler / continuous loop
- Project-level orchestrator that allocates budget across threads / subagents
- Iterative replan within (and across) passes
- **Budget enforcement** wired to `FundingAllocation` so capital actually bounds depth

Without this: a powerful remote-controlled lab, not an engine that runs while you sleep.

### 2. Belief integration

- Semantic **merge** of branches (agree / conflict / coexist)
- Semantic **diff** (“what does this line now believe?”)
- **Tags** for citable established results
- Optional-but-real stage discipline + integrate step that updates project-level
  claims / confidence

Today the ledger records history well; it does not yet *synthesize* parallel lines
into a living project belief state.

### 3. Instrument breadth (what agents can actually do)

Roadmap priority after `0.12` (see `roadmap-next-steps.md`):

1. Tier-1 literature pins (reuse `source.pin` from `oeis.search`)
2. Z3 for machine-checked falsification
3. Later: tables / plots, intervals, Lean + heavier substrate

The agent loop is only as strong as the menu; five math/OEIS tools will not carry
long-horizon domains end-to-end.

### 4. Human-in-the-loop → selective autonomy

Today: human commissions, human validates, human accepts/rejects branches.

Needed for “engine”: policy for when agents may auto-advance, auto-close dead ends,
and escalate only contradictions — still without conflating funder / contributor /
validator.

### 5. Economic & trust layer

Settlement (real money → real compute), reputation, stronger multi-party validation
norms. Funding exists as data; it does not yet *drive* the system.

### 6. Ops / production maturity

- Flip agent dark-launch safely in prod
- Harden concurrent agent-branch race
- Enforce token caps
- Object storage for large artifacts
- Keep deploy / ops docs honest with auth reality

---

## One-sentence layer positions

| Layer | Position |
| --- | --- |
| **Ledger** | Mature enough to trust as the system of record |
| **Human research workspace** | Usable end-to-end for collaborative claim / evidence / validate work |
| **Toolbench** | Production-grade for a small math falsification niche (flagship claims 1–4) |
| **Agents** | **Bounded operators**, not researchers; dark unless enabled |
| **Autonomous engine** | Still the vision — continuous budgeted multi-thread research with integrate/merge and a much wider instrument set |

---

## Pointers

| Doc | Role |
| --- | --- |
| `docs/changelog.md` | Per-phase ledger of what landed |
| `docs/plans/roadmap-next-steps.md` | Recommended next releases |
| `docs/blueprints/primitives.md` | Domain model + invariants (source of truth for *what is*) |
| `docs/vision/research-git.md` | Target git-for-research semantics (partially built) |
| `docs/vision/research-flow.md` | Target stage skeleton (not current build) |
| `docs/vision/product-vision.md` | Ambition / example domains (not a build target) |
| `docs/TLDR.md` | One-page product orientation |
| `docs/executing/thin-agent-loop-0.12.md` | Agent loop proposal (implementation completed through `0.12.4`) |
