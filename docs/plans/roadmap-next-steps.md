# Roadmap Next Steps

## Context

OpenTheory has the foundation for a research platform:

- `0.1.0` established the FastAPI backend, core domain models, Alembic setup, and smoke-test tooling.
- `0.2.0` established the Next.js frontend, typed API reads, project index, and project detail surfaces.

The next phase should turn the existing primitives into a human-operable research ledger before adding autonomous agents, payments, or advanced graph views. Agents should eventually use the same primitives that humans can use manually.

## Guiding Principle

Build the smallest complete research workflow that records what changed, why it changed, who changed it, and what evidence or artifacts were involved.

The product should first answer one practical question:

> Can OpenTheory remember a research move with provenance and show it back clearly?

## Recommended Next Release: `0.3.0`

### Human-Operable Research Ledger

Create the first end-to-end vertical slice of the ledger:

1. Open or create a project.
2. Open a research thread inside the project.
3. Add a structured claim.
4. Attach supporting, weakening, or contextual evidence.
5. Create an immutable checkpoint that records the state change.
6. Show the checkpoint in the project ledger UI.

This should remain manual and product-shaped. The goal is not agent automation yet; the goal is to make the ledger primitives real and usable.

### Backend Scope

- Add API routes for `Thread`, `Claim`, `Evidence`, and `Checkpoint`.
- Add read models for project detail pages that include threads, claims, evidence, and recent checkpoints.
- Add create flows that record `Contribution` entries for meaningful user actions.
- Add a service layer for checkpoint creation so append-only ledger rules are enforced in one place.
- Generate the first real Alembic migration for the existing domain models.
- Add focused tests for:
  - project thread creation
  - claim creation
  - evidence attachment
  - checkpoint creation
  - append-only checkpoint behavior

### Frontend Scope

- Expand the project detail page into a lightweight research workspace.
- Add a thread list for each project.
- Add a claim and evidence panel scoped to the selected thread.
- Add a checkpoint timeline showing research state changes.
- Add loading, empty, and error states for the new reads.
- Keep creation flows simple enough to validate the core workflow without overbuilding editors or dashboards.

### Out of Scope

- Autonomous agents.
- Real payment processing.
- Reputation and influence scoring.
- Complex DAG visualization.
- Full authentication and authorization.
- Artifact storage for large uploaded files.

## Follow-On Releases

### `0.4.0` - Validation And Branching

Add the next layer of research integrity:

- Validation records for claims, evidence, artifacts, checkpoints, and branches.
- Branch creation from checkpoints.
- Dead-end and rejected branch states.
- UI for validations, contradictions, and branch status.
- Tests for validation targets and branch lifecycle behavior.

### `0.5.0` - Demo Research Projects

Seed the product with realistic public research state:

- Add one or two demo projects from the vision areas.
- Prefer domains where claims, evidence, and constraints can be shown concretely.
- Include seeded threads, claims, evidence, checkpoints, and dead ends.
- Use demo data to make the frontend feel like a living research map instead of an empty scaffold.

Good candidates:

- Dark matter model constraints.
- High-temperature superconductivity mechanisms.
- Protein folding beyond known structures.

### `0.6.0` - Auth, Attribution, And Funding Simulation

Add identity and stewardship without introducing real money yet:

- Basic user identity.
- Actor-aware contribution records.
- Simulated funding allocations.
- Project-level budget and funding history views.
- Clear separation between funding, contribution, and validation.

### `0.7.0` - Agent-Ready Execution Surface

Prepare for agents once the human workflow is stable:

- Agent actor type.
- Agent-facing API keys or scoped credentials.
- Stage-aware thread execution metadata.
- Tool-result artifacts.
- Checkpoint proposals that can be accepted, rejected, or branched by a human or orchestrator.

## Priority Order

1. Make the ledger write path real.
2. Show ledger state clearly in the frontend.
3. Preserve append-only provenance.
4. Add validation and branching.
5. Seed realistic demo research.
6. Add identity, attribution, and funding simulation.
7. Introduce agents as operators of the same primitives.

## Success Criteria For The Next Milestone

`0.3.0` is successful when a user can manually perform a meaningful research action and see a durable, attributed checkpoint representing that action in the project UI.

