# Research Flow

The rigid skeleton every research thread moves through. Agents do not invent new stages, skip stages, or reorder them. They only decide *what* happens within a stage and *when* to advance.

## Why a fixed skeleton

Unconstrained agents compound errors. Fixing the shape of the flow gives us:

- **Predictable checkpoints** — known places to persist, validate, and resume.
- **Comparable progress** — every thread, in every project, advances along the same axis.
- **Debuggability** — a stuck thread is stuck *at a specific stage*, not somewhere in a soup of reasoning.
- **Auditable provenance** — claims always trace back to the stage that produced them.

## Stages

A thread is a sub-question under a project. It moves through these stages in order:

```
1. Decompose   → break the question into smaller, answerable sub-questions
2. Hypothesize → propose candidate answers / models / mechanisms
3. Formalize   → express hypotheses in precise (mathematical / structural) form
4. Design      → specify what would test, constrain, or falsify the formalized hypothesis
5. Execute     → run the test (simulation, numerical experiment, proof attempt, dataset fit)
6. Validate    → independently check the execution output against the design
7. Integrate   → fold the result back into the project's body of knowledge
```

### What each stage owns

| Stage | Input | Output | Typical tool-agents called |
|---|---|---|---|
| Decompose | A question | A set of child threads (or "atomic — no decomposition") | structure-checker, duplicate-detector |
| Hypothesize | Atomic question | One or more candidate hypotheses with rationale | literature-search, prior-art-lookup |
| Formalize | A hypothesis (prose) | A formal object (equation, model, claim with types) | math-formalizer, schema-validator |
| Design | Formal hypothesis | A test specification (inputs, expected shape of evidence, falsification criteria) | test-designer, constraint-extractor |
| Execute | Test specification | Raw results | simulator, numerical-runner, proof-checker, dataset-fitter |
| Validate | Results + test spec | Pass / fail / inconclusive, with notes | independent-rerunner, statistical-validator, contradiction-checker |
| Integrate | Validated result | An update to the project ledger (new claims, retracted claims, updated confidences) | merge-resolver, confidence-updater |

## Stage transitions are checkpoints

Advancing from stage *N* to stage *N+1* requires a **checkpoint commit** to the research-git ledger (see `research-git.md`). A stage cannot be re-entered destructively — re-doing a stage means **branching** from the prior checkpoint, not overwriting it.

A checkpoint records:

- The stage just completed
- Inputs consumed
- Outputs produced
- Agent(s) responsible
- Tool-agents invoked (with their inputs/outputs)
- Evidence references
- Parent checkpoint(s)

## Stage outcomes

Each stage produces one of three outcomes:

- **Advance** — output is well-formed, move to next stage.
- **Reject** — output is unusable; branch back to an earlier checkpoint and retry with different inputs.
- **Dead-end** — the stage proved the thread is not worth pursuing further. The thread is closed but the reasoning is preserved (negative results matter).

Dead-ends are a first-class outcome, not a failure. The ledger keeps them visible so other threads don't redo the same exploration.

## Who advances stages

- **Stage executors** (specialized orchestrators) run the stage internally and propose a checkpoint.
- **Thread orchestrator** decides whether to accept the checkpoint, reject it, or branch.
- **Project orchestrator** never touches stages directly — it decides which threads get attention/compute.
- **Tool-agents** never advance stages; they only return values to whoever called them.

## What is *not* in scope here

- The git-like ledger mechanics (commits, branches, merges) — see `research-git.md`.
- Funding, attribution, and human steering — separate concern.
- The internal implementation of any tool-agent — they're black boxes from the flow's perspective.
