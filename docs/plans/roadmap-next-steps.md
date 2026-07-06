# Roadmap Next Steps

> **Last updated:** 2026-07-06 · **Current release line:** `0.12.4` (Thin agent loop shipped).
> For the per-phase ledger see `docs/changelog.md`; for the completed `0.12.x` plan see
> `docs/executing/thin-agent-loop-0.12-implementation-plan.md` (proposal:
> `docs/executing/thin-agent-loop-0.12.md`).

## Where we are

OpenTheory is a **live research ledger** with a deterministic toolbench and a **thin agent loop**.
The foundation through `0.4.x` (ledger writes, validation, branching), identity and
collaboration through `0.8.x`, auth and funding through `0.6.x`–`0.7.x`, the
toolbench spine plus flagship math instruments through `0.9.x`–`0.10.x`, the execution
sandbox through `0.11.x`, and the thin agent loop through `0.12.x`, are all shipped and deployed.

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

**Agents are now bounded operators.** A member commissions a **Run agent pass** on a thread
(`0.12.x`): the assigned Research-crew model plans a capped sequence of *existing* instrument
runs, and the agent Actor lands attributed checkpoints on a durable agent branch through the
**same** `run_instrument` chokepoint humans use — a full `AgentRun` trace shows what it tried and
what landed; the human then accepts, rejects (dead-end), or branches. Still bounded, not
autonomous: no continuous/scheduled loop, no multi-thread orchestrator, no project-budget metering
yet (`0.12.5`, deferred — per-pass safety caps bound blast radius). The guiding constraint held
throughout: every capability was human-usable through the API *first*, so the agent simply uses
what humans already could.

## Guiding principle (unchanged)

Build the smallest complete research workflow that records what changed, why it changed,
who changed it, and what evidence or artifacts were involved — then extend it without
bypassing the checkpoint chokepoint or conflating funder / contributor / validator roles.

## Recommended next releases

### `0.12.x` — Thin agent loop ✅ **shipped** (`0.12.0`–`0.12.4`)

Delivered: a bounded pass (planner → capped instrument runs on a durable agent branch through the
same chokepoint), a request-scoped `202` + background execution, the pollable `AgentRun` trace, and
the workspace trigger/trace/review UI. **`0.12.5` (project-budget metering) deferred** — the
per-pass safety caps (`agent_pass_max_runs`, token cap) bound blast radius, so the line demos without
it. Prod enablement is a flag flip (`AGENT_LOOP_ENABLED=true`) + the `OPENROUTER_API_KEY` Fly secret.

**Natural follow-ons (pick per demand):** `0.12.5` project-budget metering (debit the project's
compute budget per pass, honoring funder/contributor separation); an iterative plan→observe→replan
within a pass; and eventually the orchestrator agent that allocates project budget across subagents.

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

1. ~~**Execution sandbox** (`0.11.x`)~~ ✅ shipped.
2. ~~**Thin agent loop** (`0.12.x`)~~ ✅ shipped — Research crew is now a bounded operator.
3. **Tier 1 retrieval** — literature pin instruments (Crossref / arXiv / OpenAlex) on the proven
   `source.pin` shape. Directly widens what an agent pass can *do*.
4. **Z3 instrument** — machine-checked falsification / unsat without Lean infra; a strong new
   instrument for the agent loop to reach for.
5. **`0.12.5` project-budget metering** — debit the project's compute budget per pass (stretch; the
   per-pass safety caps already bound a single pass).
6. **Bench 6 surfaces** — tables and Vega-Lite plots when a thread needs them.
7. **Lean + full substrate** — Claim 5; only after the above.

## Shipped milestones (reference)

| Release | What landed |
|---|---|
| `0.3.x` | Human-operable ledger write path + workspace |
| `0.4.x` | Validation, branching, enriched read models |
| `0.6.x`–`0.7.x` | Auth (Supabase JWT), `Account`/`Actor`, funding allocations, live deploy |
| `0.8.x` | Kamino Console, stewardship, `@username`, invitations, Research crew UI |
| `0.9.x` | Toolbench spine, adapter/registry, five instruments, drive/show UI, security hardening |
| `0.10.x` | `counterexample.search`, LaTeX companions, KaTeX — flagship claims 1–4 ready |
| `0.11.x` | Execution sandbox — killable subprocess, wall-clock/memory caps, concurrency limit |
| `0.12.x` | Thin agent loop — planner, bounded orchestrator, `202`+background API, workspace UI |

## Success criteria for the next milestone

**Tier 1 retrieval** is successful when an agent pass (or a human) can pin a literature source
(Crossref / arXiv / OpenAlex) as content-addressed Evidence via the same `source.pin` shape
`oeis.search` proved — landing an attributed checkpoint through the chokepoint, with a reproducible
citation (`url` + `retrieved_at` + `raw_response_hash`).