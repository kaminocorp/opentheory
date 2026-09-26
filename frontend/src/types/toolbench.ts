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
  // Records the produced checkpoint on a branch (else the project main line), so a run made while
  // viewing a branch lands on that line rather than silently on main.
  branch_id?: string | null;
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

// Output shape of `z3.prove` (0.13.x) — free-form on the wire, typed here so drive/result cards
// stay honest about the three outcomes (proof / counter-model / undecided).
export type Z3ProveOutput = {
  goal: string;
  variables: Record<string, "int" | "real" | "bool" | string>;
  constraints: string[];
  proven: boolean;
  refuted: boolean;
  status_reason?: string | null;
  witness?: Record<string, string> | null;
  certificate?: string | null;
  used_hypotheses?: string[] | null;
  goal_latex?: string | null;
  constraints_latex?: string[] | null;
};

// Output shape of `z3.satisfy` (0.33.0) — sat model / unsat / undecided.
export type Z3SatisfyOutput = {
  variables: Record<string, "int" | "real" | "bool" | string>;
  constraints: string[];
  satisfied: boolean;
  unsatisfiable: boolean;
  status_reason?: string | null;
  model?: Record<string, string> | null;
  certificate?: string | null;
  used_constraints?: string[] | null;
  constraints_latex?: string[] | null;
};

// Output shape of `lean.prove` (0.23.0 / 0.26.0) — proved / failed / undecided.
// Grade A only when `outcome === "proved"` (status `result`). Failed typechecks
// are not refutations. `mathlib` is the opt-in; missing lake/Mathlib is undecided.
export type LeanProveOutput = {
  source: string;
  outcome: "proved" | "failed" | "undecided";
  proven: boolean;
  status_reason?: string | null;
  banned_constructs?: string[] | null;
  diagnostics?: string | null;
  lean_version?: string | null;
  certificate?: string | null;
  mathlib?: boolean;
  lake_used?: boolean;
  mathlib_rev?: string | null;
};

// Output shape of Bench 6 `table.*` (0.34.0) — structured grid, exact cells.
export type TableArtifactOutput = {
  title?: string | null;
  columns: string[];
  rows: Record<string, string>[];
  n_rows: number;
  n_cols: number;
  has_labels?: boolean;
  exact?: boolean;
  markdown?: string;
  name?: string;
  expression?: string;
  is_relation?: boolean;
  holds_per_row?: Array<boolean | null> | null;
  n_false?: number | null;
  n_undecided?: number | null;
  witness?: Record<string, string> | null;
  expression_latex?: string | null;
};

// Output shape of `interval.eval` (0.35.0) — proven enclosure, never a float.
export type IntervalEvalOutput = {
  expression: string;
  is_relation: boolean;
  lo?: string | null;
  hi?: string | null;
  left_lo?: string | null;
  left_hi?: string | null;
  right_lo?: string | null;
  right_hi?: string | null;
  holds?: boolean | null;
  precision_bits: number;
  method?: string | null;
  status_reason?: string | null;
  expression_latex?: string | null;
  enclosure_latex?: string | null;
  left_enclosure_latex?: string | null;
  right_enclosure_latex?: string | null;
};

// Output shape of Bench 6 `plot.*` (0.34.0) — Vega-Lite spec, approximate viz.
export type PlotArtifactOutput = {
  expression?: string;
  variable?: string;
  domain?: string[];
  n_samples?: number;
  n_plotted?: number;
  n_points?: number;
  mark?: string;
  approximate: boolean;
  spec: Record<string, unknown>;
  points: Array<{ x: number; y: number }>;
  note: string;
  status_reason?: string | null;
  expression_latex?: string | null;
  x_title?: string;
  y_title?: string;
};
