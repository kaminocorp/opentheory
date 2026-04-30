# Research-Git

A git-like ledger for research, not code. The unit of versioning is a **claim** (or hypothesis, result, decomposition) rather than a file. The graph it produces is the project's living state of understanding.

## Why git-shaped

Research has the same needs version control solved for code:

- **Persistence with history** — never lose what you tried, even when it didn't work.
- **Parallel exploration** — multiple hypotheses can be developed in parallel without stomping on each other.
- **Provenance** — every claim traces back to the agent, tool, and evidence that produced it.
- **Reversibility** — bad merges can be backed out; abandoned branches can be revisited.
- **Diffability** — "what does this thread now believe that it didn't before" is a real question with a real answer.

Borrowing git's primitives gives us a mental model people already understand, and a data model that's already proven to work at scale.

## Core primitives

### Commit (= checkpoint)

Produced at every stage transition in the research flow (see `research-flow.md`).

Fields:

- `id` — content-addressed hash
- `parent(s)` — one parent for normal advance, multiple for merges
- `stage` — which research-flow stage this commit closes
- `thread` — the thread this commit belongs to
- `author` — orchestrator and/or tool-agents responsible
- `inputs` — refs to commits/evidence consumed
- `outputs` — the artifacts produced (hypotheses, formal objects, test specs, results, validations)
- `tool_invocations` — for each tool-agent called: name, version, inputs, outputs
- `evidence_refs` — pointers to external data (datasets, papers, prior commits)
- `confidence` — current confidence level for the claim(s) this commit asserts
- `notes` — free-form, but structured fields above are authoritative

Commits are immutable. A "fix" is a new commit on a new branch, not an edit.

### Branch

A line of exploration. Created when:

- A stage is **rejected** and retried with different inputs.
- An orchestrator wants to explore an **alternative hypothesis** in parallel.
- A reviewer wants to attempt an **independent reproduction**.

Branches are cheap. Most will be abandoned. Abandonment is recorded, not deleted.

### Merge

Synthesis. Combining two or more branches back into a single line of belief. Three outcomes:

- **Clean merge** — branches agree; their claims are unified.
- **Conflict** — branches disagree; conflict must be resolved by an explicit `merge-resolver` tool-agent or orchestrator decision. The resolution itself is recorded as a commit with a rationale.
- **Coexist** — branches represent legitimately different viable hypotheses; they remain as siblings, both tracked, neither merged until evidence breaks the tie.

### Diff

A diff between two commits answers: *what claims, confidences, or open questions changed?* Not a textual diff — a **semantic** diff over the structured outputs.

### Blame

For any claim in the project, blame returns the chain of commits, agents, and tool invocations that produced it. This is the substrate for attribution and for debugging bad results.

### Tag

A named pointer at a commit. Used for:

- **Validated results** — a commit promoted to "this is something the project considers established."
- **Milestones** — funding-relevant or attribution-relevant moments.
- **Retractions** — a tag pointing at the last-good commit before a bad result was integrated.

## The graph

A project is a DAG of commits. Threads are roughly linear chains within it; branches fan out and (sometimes) merge back. Dead-end branches just stop — they remain reachable, with a closing commit that records *why* they were abandoned.

```
project root
  ├── thread A
  │     ├── decompose ── hypothesize ── formalize ── design ── execute ── validate ── integrate
  │     │                       └── (alt hypothesis branch) ── ... ── dead-end
  │     └── (reproduction branch) ── execute ── validate ── (merges back at integrate)
  └── thread B
        └── ...
```

## What's stored where

- **Commits, branches, tags, refs** — the ledger itself. Authoritative, append-only.
- **Artifacts** (results, formal objects, simulations) — content-addressed; commits reference them by hash.
- **External evidence** — referenced by URI + hash; never copied wholesale, but its hash is pinned so we know if it changes.

## Operations agents perform

Limited, named operations. Agents do not get to write to the ledger arbitrarily.

- `commit(stage, inputs, outputs, tool_invocations, parent)` — close a stage.
- `branch(from_commit, reason)` — open a new line of exploration.
- `merge(commits, resolution)` — synthesize, with explicit resolution if conflict.
- `tag(commit, name, kind)` — promote, milestone, or retract.
- `close_branch(commit, outcome)` — mark a branch as dead-end or superseded.

Reads (`diff`, `blame`, `log`, `show`) are unrestricted.

## What is *not* in scope here

- The stage definitions themselves — see `research-flow.md`.
- Storage backend, schemas, on-disk format — implementation detail.
- Funding, attribution payouts, governance — separate concern that *uses* blame and tags but doesn't define them.
