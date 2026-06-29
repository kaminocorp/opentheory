# Conceptual Blueprint — The OpenTheory Mental Model

> A one-screen map of how OpenTheory's primitives fit together and *why* they're
> shaped the way they are. This is the mental model, not the spec — for
> authoritative detail read `docs/primitives.md` (the model + invariants),
> `docs/research-git.md` (the ledger semantics), and the current backend
> `models/` (the truth when the docs and code disagree).

---

## The one-line idea

**A git for research.** A research question becomes a living, append-only,
git-shaped ledger of immutable, attributed state changes — so knowledge
compounds, dead ends are recorded rather than deleted, and every belief is
traceable to who produced it and on what evidence.

---

## The primitives, grouped by what they're *for*

### 1. Containers & inquiry structure

| Primitive   | What it is                                                        | Shape                         |
| ----------- | ----------------------------------------------------------------- | ----------------------------- |
| **Project** | Top-level research container — the question, scope, everything    | The aggregation root          |
| **Thread**  | A focused *line of inquiry* within a project                      | A roughly **linear chain**    |
| **Branch**  | A parallel *line of exploration*, usually within a thread         | A **fork** that may merge back |

### 2. Knowledge units

| Primitive    | What it is                                                       | Note                                    |
| ------------ | --------------------------------------------------------------- | --------------------------------------- |
| **Claim**    | The central knowledge unit — a structured assertion             | First-class; confidence is *explained*  |
| **Artifact** | A *produced* research object (proof, sim, dataset, plot, paper) | Content-addressed where possible        |
| **Evidence** | A source/result that supports, weakens, falsifies, contextualizes | External evidence is *pinned* (URI + timestamp + hash) |

### 3. The ledger (git-shaped)

| Primitive      | What it is                                              | Note                            |
| -------------- | ------------------------------------------------------ | ------------------------------- |
| **Checkpoint** | An immutable, attributed snapshot of a state change     | **This is the commit.**         |

### 4. The three deliberately-separated roles

| Primitive            | Concern         | What it must *not* imply               |
| -------------------- | --------------- | -------------------------------------- |
| **FundingAllocation** | money → project | correctness, authorship, validation    |
| **Contribution**      | who did what    | (the substrate for reputation)         |
| **Validation**        | who assessed it | authorship of the thing being assessed |

### 5. The actor

| Primitive   | What it is                                              | Note                                       |
| ----------- | ------------------------------------------------------ | ------------------------------------------ |
| **Actor**   | The thing that performs an action (`human`/`agent`/`system`) | Research provenance lives here       |
| **Account** | The *auth principal* that **owns** Actors (added `0.7.0`) | Holds `external_id`, `roles`, funding attribution |

---

## Thread vs Branch — the distinction that trips people up

There is **no `Line` primitive.** "Line" appears only informally in the docs and
points at two different things:

- a **"line of inquiry"** → a **Thread**
- a **"line of exploration"** / "main line of belief" → a **Branch**

So the real question is always **Thread vs Branch**:

|              | **Thread**                          | **Branch**                                    |
| ------------ | ----------------------------------- | --------------------------------------------- |
| Shape        | A roughly **linear chain** of work  | A **fork** that fans out, may merge back      |
| Purpose      | A distinct *sub-question*           | *Competing/parallel attempts* at the same one |
| Git analogy  | A workstream                        | A git branch                                  |
| Lifecycle    | Opened, worked, accumulates claims  | Forks from a checkpoint; merges, closes, or coexists |

**Mental model:** a project is a **DAG of checkpoints**. Threads are the roughly
linear chains within it; branches fan out and *sometimes* merge back. A dead-end
branch doesn't vanish — it stops, with a **closing checkpoint that records why**
it was abandoned. Negative results are kept because they prevent repeated work.

---

## The git-for-research correspondence

| Git          | OpenTheory                                              |
| ------------ | ------------------------------------------------------- |
| commit       | **Checkpoint** — an immutable, attributed state change  |
| branch       | **Branch** — a parallel line of exploration             |
| merge / diff | integrating or comparing research lines                 |
| blame        | provenance — who contributed what, on what evidence     |
| tag          | a marked, citable result                                |

---

## Three roles, never conflated (the load-bearing rule)

A **funder** finances, a **contributor** produces, a **validator** assesses.
These roles can overlap in real people, but the **data model refuses to conflate
them** — they are three separate tables, each attributed independently:

- A funder financing a thread mints a `FundingAllocation`, but earns **no**
  intellectual `Contribution` credit for the work it pays for.
- A validator's judgement is a **new** `Validation` row — never an edit to the
  claim it assesses.
- Funding controls *how much structured investigation the system can afford
  before stopping* (each project runs against a token budget), but never *what is
  true*.

This is what keeps credit meaningful while allowing broad participation.

---

## The semantics that make it hold together

Two invariants are **enforced in code, not by convention** — they hold even if
the frontend or route layer is bypassed:

- **Append-only** (`models/append_only.py`): ORM `before_update` / `before_delete`
  guards raise `AppendOnlyError` on `Checkpoint`, `CheckpointRef`,
  `FundingAllocation`, and `Validation`. Corrections, reversals, and retractions
  are **new records**, never edits. (Caveat: the guards fire on the ORM
  unit-of-work only; bulk Core `UPDATE`/`DELETE` and DDL bypass them by design.)

- **The checkpoint chokepoint** (`services/checkpoints.py`): `create_checkpoint`
  is the **only** code path that writes a `Checkpoint`. Composing flows
  (validation, branching) call *into* it with trusted `extra_refs` rather than
  minting their own checkpoints, and it owns the single DB `commit` — so each
  write is one atomic transaction that also auto-records the `Contribution`. If
  any part fails, nothing orphans.

And one philosophical rule that shapes the whole model:

- **Confidence is explainable, not a naked score.** A claim's confidence is
  derived from its evidence and validation history, so you can always trace *why*
  something is believed.

---

## The relationship map

```text
Account                      (auth principal; owns Actors — added 0.7.0)
  └── Actor                  (human | agent | system; performs every action)
        ├── Contribution
        ├── FundingAllocation
        ├── Checkpoint        (authors)
        └── Validation        (performs)

Project
  ├── FundingAllocation
  ├── Thread
  │     ├── Claim
  │     ├── Artifact
  │     ├── Evidence
  │     ├── Checkpoint
  │     └── Branch
  ├── Claim
  ├── Artifact
  ├── Evidence
  ├── Checkpoint
  ├── Validation
  └── Contribution
```

---

## Design rule: human-first, agents later

Anything an agent may eventually do must **first** be possible for a human
contributor through the platform — create/refine a claim, attach evidence, open a
thread, fork a branch, validate a result, challenge an assumption, fund a project.

Agents are **not a parallel data model**: an agent is just an `Actor` of
`type=agent`, using the *same* APIs, permissions, and provenance rules as humans,
with metadata describing its model/provider/version/run-context. The backend is
the single source of truth and enforces every invariant — so when agents arrive,
they simply use what humans already could.

---

## A note on staying in sync

`docs/primitives.md` is the source-of-truth domain doc and now reflects the
`0.7.0` `Account` / `Actor` split (identity, `roles`, and funding attribution on
`Account`; research provenance on `Actor`). This blueprint is the *compression* of
that doc, not a competing source. When any doc and the code disagree, **the code
wins** — trust `backend/app/models/` + `docs/changelog.md`.
