# OpenTheory — TLDR

> **A platform for continuous, agent-driven research.** Instead of one-off
> answers, OpenTheory hosts *living* research projects: a tightly-scoped question
> is decomposed into parallel threads, worked continuously, and every meaningful
> move is written to an append-only, git-shaped **research ledger** with full
> provenance. Knowledge compounds; nothing resets between sessions; dead ends are
> recorded, not deleted.

## The one-paragraph version

A **project** poses a research question. It is broken into **threads** that are
explored in parallel — proposing hypotheses, formalizing them, running
simulations, testing constraints. Each meaningful state change is committed as an
immutable **checkpoint** in the ledger, carrying who did it, why, and what
evidence or artifacts were involved. The result is not chat output but a
*transparent map of knowledge in motion*: active threads, key findings,
contradictions, and confidence levels you can inspect and trace.

## The core idea: a git for research

The ledger borrows git's shape (see `docs/research-git.md`):

| Git            | OpenTheory                                              |
| -------------- | ------------------------------------------------------- |
| commit         | **checkpoint** — an immutable, attributed state change  |
| branch         | a parallel line of exploration (dead ends preserved)    |
| merge / diff   | integrating or comparing research lines                 |
| blame          | provenance — who contributed what, and on what evidence |
| tag            | a marked, citable result                                |

**Append-only is enforced in code, not by convention.** Corrections, reversals,
and retractions are *new* records — a re-assessment is a new validation row,
never an edit. All ledger writes funnel through a single checkpoint chokepoint so
provenance and contribution recording can't be bypassed.

## Three roles, deliberately never conflated

This is a load-bearing design rule, enforced in the data model:

- **Funders** finance projects or specific threads, directing compute toward the
  paths they believe in. Each project runs against an explicit **token budget**:
  a small budget buys a fast, shallow pass; a larger one buys broader
  exploration, more retries, and stronger validation. Capital controls *how much
  structured investigation the system can afford before stopping.*
- **Contributors** produce the intellectual work — shaping hypotheses, supplying
  evidence — and earn attribution for it.
- **Validators** assess results, building confidence that is *explainable through
  evidence and validation history*, never a naked score.

A funder financing a thread earns no intellectual credit for it; a validator
assessing a claim is not its author. Keeping these separate is what keeps credit
meaningful while still allowing broad participation.

## Domain primitives

`Project` → `Thread`, `Claim`, `Artifact`, `Evidence`, `Checkpoint`, `Branch`,
`Validation`, `Contribution`, `FundingAllocation`. An **`Actor`** (`human` |
`agent` | `system`) performs every action — authoring checkpoints, making
contributions, performing validations, allocating funding. (Full relationships
and invariants live in `docs/primitives.md`.)

## Where it is today vs. where it's going

**Today — a human-operable research ledger (shipped, live):**

- The full ledger write path is real: open projects and threads, add claims,
  attach evidence, record immutable checkpoints, fork/close branches, and record
  validations — all through the enforced chokepoint, all attributed.
- Identity is real: verified auth provisions actors; funding allocations are
  recorded as a separate, source-aware concern.
- It runs as a split Next.js frontend + FastAPI backend + Postgres, deployed
  live, presented in the "Kamino Console" design language.

**Once done — an autonomous research engine:**

- **Agents** become first-class operators, using the *same* APIs, permissions,
  and provenance rules as humans — never a parallel data model. They propose
  checkpoints that a human or orchestrator can accept, reject, or branch.
- Projects run **continuously** against their token budgets, decomposing
  questions into threads and working them in parallel without resetting.
- **Reputation and influence** accrue over time to those who consistently back,
  produce, and validate the right directions.
- Real funding and settlement replace the simulated allocations.

The guiding constraint throughout: **the backend is the single source of truth
and enforces every invariant even if the frontend is bypassed**, and any new
capability is made human-usable through the API *first* — so that when agents
arrive, they simply use what humans already could.

## Example domains (from the vision)

Hard, long-horizon, fragmentable problems where claims and constraints can be
shown concretely: dark-matter model constraints, quantum gravity, the Riemann
hypothesis, Navier–Stokes smoothness, P vs NP, protein folding beyond known
structures, high-temperature superconductivity.

---

*This is a high-level orientation. For depth, read (in order of importance):
`docs/primitives.md` (the model and its invariants), `docs/research-git.md` (the
ledger semantics), `docs/vision.md` (product vision), `docs/techstack.md` (stack
rationale), and `docs/changelog.md` (what has actually shipped).*
