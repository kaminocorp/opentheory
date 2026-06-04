// Shared domain types mirroring the backend read schemas (app/schemas/*).
// Enum string values are the lowercase JSON values the API emits.

export type ActorType = "human" | "agent" | "system";

export type Actor = {
  id: string;
  type: ActorType;
  display_name: string;
  external_id: string | null;
  actor_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ThreadStage =
  | "decompose"
  | "hypothesize"
  | "formalize"
  | "design"
  | "execute"
  | "validate"
  | "integrate";

export type ThreadStatus = "open" | "active" | "blocked" | "dead_end" | "closed";

export type Thread = {
  id: string;
  project_id: string;
  title: string;
  question: string;
  stage: ThreadStage;
  status: ThreadStatus;
  thread_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

// Thread list rows carry their claim count (0.3.4).
export type ThreadSummary = Thread & {
  claim_count: number;
};

export type ActorSummary = {
  id: string;
  display_name: string;
  type: ActorType;
};

export type ProjectCounts = {
  threads: number;
  claims: number;
  evidence: number;
  checkpoints: number;
};

export type ProjectOverview = {
  id: string;
  title: string;
  slug: string;
  question: string;
  description: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  counts: ProjectCounts;
};

export type ClaimKind =
  | "hypothesis"
  | "assumption"
  | "constraint"
  | "observation"
  | "objection"
  | "result"
  | "retraction";

export type ClaimStatus =
  | "proposed"
  | "supported"
  | "challenged"
  | "validated"
  | "retracted";

export type Claim = {
  id: string;
  project_id: string;
  thread_id: string | null;
  kind: ClaimKind;
  status: ClaimStatus;
  statement: string;
  rationale: string | null;
  confidence: number | null;
  claim_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type RelationKind = "support" | "weaken" | "context";

export type Evidence = {
  id: string;
  project_id: string;
  thread_id: string | null;
  title: string;
  source_type: string;
  uri: string | null;
  retrieved_at: string | null;
  content_hash: string | null;
  citation: string | null;
  notes: string | null;
  evidence_metadata: Record<string, unknown>;
  relation_kind: RelationKind;
  link_id: string;
  created_at: string;
  updated_at: string;
};

export type CheckpointRef = {
  id: string;
  target_type: string;
  target_id: string;
  role: string;
  // Human label for the referenced primitive, resolved server-side (0.3.4).
  label: string | null;
};

export type Checkpoint = {
  id: string;
  project_id: string;
  thread_id: string | null;
  author_id: string | null;
  author: ActorSummary | null;
  contribution_kind: string | null;
  stage: ThreadStage | null;
  summary: string;
  content: Record<string, unknown>;
  notes: string | null;
  parent_ids: string[];
  refs: CheckpointRef[];
  created_at: string;
  updated_at: string;
};

// Create payloads (project_id / thread_id / actor are supplied out-of-body).

export type ActorCreate = {
  type: ActorType;
  display_name: string;
};

export type ThreadCreate = {
  title: string;
  question: string;
};

export type ClaimCreate = {
  kind: ClaimKind;
  statement: string;
  rationale?: string | null;
  confidence?: number | null;
};

export type EvidenceCreate = {
  title: string;
  source_type: string;
  uri?: string | null;
  notes?: string | null;
  relation_kind: RelationKind;
};

export type CheckpointCreate = {
  thread_id?: string | null;
  summary: string;
  notes?: string | null;
};
