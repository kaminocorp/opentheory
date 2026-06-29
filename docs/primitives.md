# Core Primitives

OpenTheory should start as a human-operable research platform. Agents are future operators of the same primitives humans can use manually, not a separate foundation. The core model should therefore be simple, auditable, and usable without automation.

## Design rule

Anything an agent may eventually do should first be possible for a human contributor to do through the platform:

- create or refine a claim
- attach evidence
- open a thread
- fork a branch
- validate a result
- challenge an assumption
- fund a project
- promote or retract a finding

Agents can later be added as another actor type using the same APIs, permissions, and provenance rules.

## Project

The top-level research container.

A project defines the main research question, scope, public description, active threads, accepted findings, open contradictions, confidence map, contributors, and funding history.

Key relationships:

- has many `Thread`
- has many `Claim`
- has many `Checkpoint`
- has many `FundingAllocation`
- has many `Contribution`

Funding note:

- `Project` should reference funding through `FundingAllocation`.
- Funding allocations are a ledger of monetary top-ups directed to a project.
- Funding affects available resources and prioritization, but does not imply correctness, authorship, or validation.

## FundingAllocation

A financial ledger entry for money directed to a project.

Each allocation records a top-up, pledge, grant, refund, adjustment, or other funding event. It should be append-only rather than destructively edited, because funding history is part of project provenance.

Typical fields:

- `id`
- `project_id`
- `account_id` — the funding **principal** (`Account`, not `Actor`): money comes from the thing that holds a payment method
- `amount`
- `currency`
- `kind`
- `source` — `native` (platform compute, gated to `internal` accounts) or `stripe` (external funder)
- `status`
- `payment_reference`
- `created_at`
- `notes`

Possible `kind` values:

- `top_up`
- `grant`
- `refund`
- `adjustment`

Possible `status` values:

- `pending`
- `settled`
- `failed`
- `refunded`

## Thread

A focused line of inquiry inside a project.

A thread can represent a sub-question, hypothesis path, reproduction attempt, objection, dataset investigation, proof attempt, or dead-end exploration.

Key relationships:

- belongs to `Project`
- has many `Claim`
- has many `Artifact`
- has many `Evidence`
- has many `Checkpoint`
- may have many `Branch`

Threads should not require one fixed research flow. A flow can be attached as metadata or a template, but the primitive should support different research styles.

## Claim

A structured assertion the project is tracking.

Claims are the central knowledge unit. They can be hypotheses, assumptions, constraints, observations, objections, intermediate results, conclusions, or retractions.

Key relationships:

- belongs to `Project`
- may belong to `Thread`
- may be supported by `Evidence`
- may be challenged by other `Claim`
- may be expressed by or derived from `Artifact`
- may be changed through `Checkpoint`
- may be reviewed by `Validation`

Claims should carry state and confidence, but confidence should be explainable through evidence and validation history rather than a naked score.

## Artifact

A produced research object.

Examples include equations, formal models, proofs, simulations, plots, datasets, code outputs, benchmark results, uploaded notes, papers, diagrams, and generated reports.

Key relationships:

- belongs to `Project`
- may belong to `Thread`
- may support or express one or more `Claim`
- may be referenced by `Evidence`
- may be created or updated through `Checkpoint`

Artifacts should be content-addressed where possible so the platform can prove exactly what was used or produced.

## Evidence

A source, observation, or result used to support, weaken, falsify, or contextualize a claim.

Evidence can point to external papers, datasets, experiment outputs, prior checkpoints, human reviews, simulations, agent analyses, or uploaded artifacts.

Key relationships:

- belongs to `Project`
- may belong to `Thread`
- may target one or more `Claim`
- may reference one or more `Artifact`
- may be introduced through `Checkpoint`

External evidence should be pinned with enough metadata to make it reproducible: URI, retrieval timestamp, hash if available, citation metadata, and notes about relevance.

## Checkpoint

An immutable snapshot of a meaningful research state change.

A checkpoint is similar to a git commit, but for research state rather than files. It records what changed, why it changed, who changed it, and what evidence or artifacts were involved.

Key relationships:

- belongs to `Project`
- may belong to `Thread`
- may have parent checkpoints
- may create or modify claims, artifacts, evidence links, validations, branch state, and confidence
- has many `Contribution`

Checkpoints should be append-only. Corrections, reversals, and retractions are new checkpoints, not edits to old ones.

## Branch

A parallel research path.

Branches are used for competing hypotheses, alternative interpretations, rejected retries, independent reproductions, and exploratory work that should not overwrite the main line of inquiry.

Key relationships:

- belongs to `Project`
- usually belongs to `Thread`
- forks from a `Checkpoint`
- contains later `Checkpoint`
- may merge, close, or coexist with other branches

Dead-end branches should remain visible. Negative results are useful because they prevent repeated work.

## Validation

A structured review of a claim, artifact, checkpoint, branch, or result.

Validation records whether something passed, failed, is inconclusive, needs reproduction, contradicts other work, or should be retracted.

Key relationships:

- belongs to `Project`
- may target `Claim`
- may target `Artifact`
- may target `Checkpoint`
- may target `Branch`
- is recorded through `Checkpoint`
- creates `Contribution`

Validation should be separate from contribution and funding. A funder may finance work, a contributor may produce work, and a validator may assess work; those roles can overlap but should not be conflated.

## Contribution

An attribution and provenance record for meaningful activity.

Contributions capture who did what, when, and against which primitive. The actor can be a human now or an agent later.

Examples:

- created a project
- opened a thread
- proposed a claim
- attached evidence
- uploaded an artifact
- created a checkpoint
- validated a result
- challenged a claim
- merged a branch
- funded a project

Key relationships:

- belongs to `Project`
- references an actor
- references the target primitive
- may reference a `Checkpoint`
- may reference a `FundingAllocation`

Contribution is the substrate for attribution, reputation, influence, and later agent accountability.

## Account

The authentication *principal* (added in `0.7.0`) — one per external login (Supabase `auth.users`) — that **owns** one or more `Actor`s.

Principal-level concerns live here, deliberately separated from research provenance:

- `external_id` — the IdP subject (`sub`); the unique key auth resolves on.
- `email` — the principal's contact address.
- `roles` — queryable authorization (e.g. `internal`, which gates native funding). Authorization describes the *principal*, not a single action identity.
- funding attribution — a `FundingAllocation` is attributed to the `Account`, because money comes from the thing that holds a payment method. The *act* of funding is still recorded as an `Actor` `Contribution` — the act vs. the money.

Key relationships:

- owns many `Actor`
- has many `FundingAllocation`

An account is a mutable identity row (roles and email can change) and is **not** part of the append-only ledger. Research provenance never moves here — it stays on `Actor`.

## Actor

The entity performing an action.

Actors can be humans initially and agents later. The platform should not need a parallel data model for agents; an agent should be an actor with metadata describing its model, provider, version, permissions, and run context.

An actor is **owned by an `Account`** (the auth principal). Research provenance is attributed to the `Actor`; identity, authorization (`roles`), and funding attribution live on its `Account`.

Key relationships:

- belongs to `Account` (nullable — `system` and dev-bootstrap actors are account-less)
- has many `Contribution`
- may author `Checkpoint`
- may perform `Validation`

Possible actor types:

- `human` (one primary human actor per account)
- `agent`
- `system`

## Suggested Relationship Map

```text
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

Account                       (auth principal — owns Actors)
  ├── Actor
  └── FundingAllocation

Actor
  ├── Contribution
  ├── Checkpoint        (authors)
  └── Validation        (performs)
```

## Implementation Bias

The first version should preserve these invariants:

- Funding is append-only.
- Checkpoints are append-only.
- Claims are first-class objects.
- Evidence and artifacts are separately addressable.
- Branches preserve parallel exploration and dead ends.
- Humans and agents use the same primitives.
- Workflow stages are optional metadata, not hard-coded platform law.
