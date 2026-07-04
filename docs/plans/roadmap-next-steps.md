# Roadmap Next Steps

> **Last updated:** 2026-07-03 · **Current release line:** `0.11.6` (Execution Sandbox shipped).
> For the per-phase ledger see `docs/changelog.md`; for the completed `0.11.x` execution
> plan see `docs/executing/execution-sandbox-0.11.md`.

## Where we are

OpenTheory is a **live, human-operable research ledger** with a deterministic toolbench.
The foundation through `0.4.x` (ledger writes, validation, branching), identity and
collaboration through `0.8.x`, auth and funding through `0.6.x`–`0.7.x`, and the
toolbench spine plus flagship math instruments through `0.9.x`–`0.10.x`, and the execution
sandbox through `0.11.x`, are all shipped and deployed.

A signed-in member can today:

1. Own or collaborate on a project; invite others; assign Research crew models (UI only).
2. Decompose work into threads; add claims; attach evidence; record checkpoints.
3. Fork and close branches; record validations; read contradiction signals.
4. Run five production instruments from the workspace — with KaTeX-readable math and bounded
   execution (subprocess isolation, wall-clock/memory caps, concurrency limit):
   `calc.eval`, `expr.compare`, `geometry.coordinate_measure`, `oeis.search`,
   `counterexample.search` — each landing an attributed checkpoint through the chokepoint.

The flagship *measuring across a corner* thread (claims 1–4) is walkthrough-ready with
shipped instruments. Claim 5 (Lean proof → Grade A) remains explicitly out of scope until
the execution substrate exists.

**Agents are not operators yet.** Research crew model picks are configuration only; nothing
autonomously drives `POST …/instruments/{name}/run`. The guiding constraint still holds:
any new capability is human-usable through the API *first*, so agents can later use the
same primitives.

## Guiding principle (unchanged)

Build the smallest complete research workflow that records what changed, why it changed,
who changed it, and what evidence or artifacts were involved — then extend it without
bypassing the checkpoint chokepoint or conflating funder / contributor / validator roles.

## Recommended next releases

### `0.12.x` — Thin agent loop (recommended next)

**Why after sandbox:** Research crew UI (`0.8.10`) already names four roles and OpenRouter
models. The missing piece is an orchestrator that turns a thread + stage into instrument
runs on the **same** membership-gated API humans use.

**Goal:** one bounded agent pass on a thread — propose checkpoints via existing write paths;
human accepts, rejects, or branches (no parallel agent data model).

**Scope (sketch):**

- Background job or worker invoking `POST …/instruments/{name}/run` with the acting actor
  attributed correctly.
- Stage-aware metadata from `docs/research-flow.md` (optional hints, not hard law).
- Rate/token budget per project (ties to existing `FundingAllocation` simulation).
- Human-visible trace: what the agent tried, what landed on the ledger.

**Out of scope:** full autonomous continuous research, reputation scoring, real payments.

### `0.10.6+` (optional stretch) — `interval.eval`

Proven numeric enclosures via `python-flint` / Arb — `docs/executing/falsify-and-render-0.10.md`
Appendix B. Not required for flagship claims 1–4; pick up if interval bounds become a demo
need before Z3.

### Tier 1 retrieval wave — literature pin instruments

After sandbox or in parallel if capacity allows:

- Crossref / arXiv / OpenAlex pin instruments (reuse `source.pin` pattern from `oeis.search`).
- See `docs/plans/toolbench-catalog.md` Tier 1 table.

### Verifier wave — Z3 before Lean

- **Z3** (`z3-solver`): Tier 0, in-process, near-free — counterexamples and unsat certificates.
- **Lean**: Tier 2 — forces execution substrate; Claim 5 / Grade A. Do not start until sandbox
  + agent loop are stable.

### Deferred / deprioritized

| Item | Notes |
|---|---|
| **`0.5.0` demo seeding** | Plan exists (`docs/plans/0.5.0-demo-research-projects.md`); team preference is **no seed data** — projects start from scratch. Revisit only if empty-state UX becomes a product problem. |
| **`formula.render` instrument** | Superseded for v1 by additive `*_latex` + KaTeX in `formula.tsx` (`0.10.4`–`0.10.5`). |
| **Tables / plots (`table.*`, `plot.*`)** | Bench 6; after core agent loop or when a demo needs tabular falsification grids. |
| **Real funding / settlement** | `FundingAllocation` is recorded; Stripe etc. remain future. |
| **Reputation / influence** | Vision doc; no data model yet. |
| **Object storage for large artifacts** | Blobs stay off Postgres; upload path not built. |

## Priority order (from here)

1. **Execution sandbox** (`0.11.x`) — safe ceiling before agents and Z3/Lean.
2. **Thin agent loop** (`0.12.x`) — Research crew becomes an operator, not just config.
3. **Tier 1 retrieval** — literature pin instruments on the proven `source.pin` shape.
4. **Z3 instrument** — machine-checked falsification / unsat without Lean infra.
5. **Bench 6 surfaces** — tables and Vega-Lite plots when a thread needs them.
6. **Lean + full substrate** — Claim 5; only after the above.

## Shipped milestones (reference)

| Release | What landed |
|---|---|
| `0.3.x` | Human-operable ledger write path + workspace |
| `0.4.x` | Validation, branching, enriched read models |
| `0.6.x`–`0.7.x` | Auth (Supabase JWT), `Account`/`Actor`, funding allocations, live deploy |
| `0.8.x` | Kamino Console, stewardship, `@username`, invitations, Research crew UI |
| `0.9.x` | Toolbench spine, adapter/registry, five instruments, drive/show UI, security hardening |
| `0.10.x` | `counterexample.search`, LaTeX companions, KaTeX — flagship claims 1–4 ready |

## Success criteria for the next milestone

`0.11.x` is successful when a deliberately expensive or blocking instrument input is
terminated by the sandbox with a clear client error, no checkpoint is minted, and normal
bounded runs (flagship walkthrough) are unaffected.