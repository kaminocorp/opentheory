// Toolbench API types (0.9.x), mirroring the backend read schemas: app/schemas/instrument.py
// (the catalog descriptor) and app/schemas/tool_run.py (the run request + result). The core
// provenance types — `ResultStatus` and the `ToolInvocation` blame tuple — live in `research.ts`
// beside `Checkpoint` (which carries them) and are re-exported here so a consumer imports the whole
// toolbench surface from one place.

import type { Checkpoint, ResultStatus } from "./research";

export type { ResultStatus, ToolInvocation } from "./research";

// One of the three honest outcomes, surfaced with its meaning so the catalog self-describes. The
// same three ride on every descriptor (the contract is universal), so the UI reads one entry and
// knows how to render each outcome.
export type ResultContractOutcome = {
  status: ResultStatus;
  meaning: string;
};

// A read-only description of one instrument (`GET /instruments`). `input_schema` / `output_schema`
// are real JSON Schema (from the backend Pydantic models); static reference data, cacheable
// indefinitely — like the agent-model catalog.
export type InstrumentDescriptor = {
  name: string;
  namespace: string;
  version: string;
  engine: string;
  engine_version: string;
  description: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  result_contract: ResultContractOutcome[];
};

// Body for `POST /projects/{id}/instruments/{name}/run`. `inputs` is the raw instrument payload —
// validated against the resolved instrument's InputModel *server-side* (a mismatch is a 422), so the
// envelope stays generic across every instrument. `assumptions` are recorded on the produced
// Evidence/Artifact and in the blame tuple. `thread_id` scopes the result; `claim_id` (with an
// optional `relation_kind`) also mints Evidence linked to that claim.
export type ToolRunRequest = {
  inputs: Record<string, unknown>;
  assumptions?: Record<string, unknown>;
  thread_id?: string | null;
  claim_id?: string | null;
  relation_kind?: string | null;
};

// What the run endpoint returns (201). The blame tuple rides on `checkpoint.tool_invocations`; the
// produced artifact/evidence are linked by id, with `status` + `content_hash` lifted for
// convenience. Phase 7 renders provenance from the blame tuple + these ids.
export type ToolRunResult = {
  checkpoint: Checkpoint;
  artifact_id: string;
  evidence_id: string | null;
  status: ResultStatus;
  content_hash: string;
};
