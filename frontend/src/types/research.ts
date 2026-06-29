// Shared domain types mirroring the backend read schemas (app/schemas/*).
// Enum string values are the lowercase JSON values the API emits.

export type ActorType = "human" | "agent" | "system";

export type Actor = {
  id: string;
  type: ActorType;
  display_name: string;
  // The owning principal (0.7.0, Account-owns-Actor); null for system/dev/unlinked actors.
  // `external_id` and `roles` moved to the Account.
  account_id: string | null;
  actor_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

// The authentication principal (0.7.0) that owns actors. Holds the IdP subject, contact email, and
// queryable authorization `roles` (`internal` gates native funding). Mirrors the backend AccountRead.
export type Account = {
  id: string;
  external_id: string | null;
  display_name: string;
  email: string | null;
  roles: string[];
  created_at: string;
  updated_at: string;
};

// Privacy-safe funder identity (no email/roles), mirroring the backend AccountSummary.
export type AccountSummary = {
  id: string;
  display_name: string;
};

// GET /me — the resolved acting actor plus its owning account (roles/email), driving the identity
// menu + write gating. Mirrors the backend MeRead.
export type Me = Actor & {
  account: Account | null;
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
  validations: number;
  branches: number;
};

export type BranchStatusCounts = {
  open: number;
  dead_end: number;
  closed: number;
};

// A contested claim surfaced on the overview (0.4.4).
export type ContradictionItem = {
  claim_id: string;
  thread_id: string | null;
  statement: string;
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
  branch_counts: BranchStatusCounts;
  contradictions: ContradictionItem[];
  // Budget derived from the funding ledger (0.6.3); null if not yet loaded.
  budget: ProjectBudget | null;
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

// Derived display signal (0.4.4): computed from validation history, server-side.
export type ClaimSignal = "none" | "contested" | "validated";

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
  // Embedded validation history (oldest first) and derived signal (0.4.4).
  validations: Validation[];
  signal: ClaimSignal;
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
  // The branch this checkpoint sits on; null = the project main line (0.4.2).
  branch_id: string | null;
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
  branch_id?: string | null;
  summary: string;
  notes?: string | null;
};

// --- Validations (0.4.1) ----------------------------------------------------

export type ValidationOutcome =
  | "passed"
  | "failed"
  | "inconclusive"
  | "needs_reproduction"
  | "contradicts"
  | "retract";

// Targets a human can validate in 0.4.x (artifact is wired backend-side but has no
// write flow yet, so it is omitted from the UI).
export type ValidationTargetType = "claim" | "checkpoint" | "branch";

export type Validation = {
  id: string;
  project_id: string;
  actor_id: string | null;
  actor: ActorSummary | null;
  target_type: string | null;
  target_id: string | null;
  outcome: ValidationOutcome;
  notes: string | null;
  // The checkpoint this validation was recorded through (0.4.1).
  recording_checkpoint_id: string | null;
  created_at: string;
  updated_at: string;
};

export type ValidationCreate = {
  target_type: ValidationTargetType;
  target_id: string;
  outcome: ValidationOutcome;
  notes?: string | null;
};

// --- Branches (0.4.2) -------------------------------------------------------

export type BranchStatus = "open" | "merged" | "closed" | "dead_end";

export type Branch = {
  id: string;
  project_id: string;
  thread_id: string | null;
  forked_from_checkpoint_id: string | null;
  name: string;
  reason: string | null;
  status: BranchStatus;
  created_at: string;
  updated_at: string;
};

// Branch list rows carry their checkpoint count (0.4.4).
export type BranchSummary = Branch & {
  checkpoint_count: number;
};

export type BranchCreate = {
  from_checkpoint_id: string;
  name: string;
  reason?: string | null;
  thread_id?: string | null;
};

// Only the two closing outcomes are accepted by the API.
export type BranchCloseOutcome = "dead_end" | "closed";

export type BranchClose = {
  outcome: BranchCloseOutcome;
  reason?: string | null;
};

// --- Funding (0.6.3) --------------------------------------------------------
// Monetary amounts are Decimals serialized as strings (e.g. "500.00") to preserve precision.

export type FundingKind = "top_up" | "grant" | "refund" | "adjustment";
export type FundingSource = "native" | "stripe";
export type FundingStatus = "pending" | "settled" | "failed" | "refunded";

export type Funding = {
  id: string;
  project_id: string;
  // The funder is the principal (0.7.0, Decision #5); `account` is the privacy-safe AccountSummary.
  account_id: string | null;
  account: AccountSummary | null;
  amount: string;
  currency: string;
  kind: FundingKind;
  source: FundingSource;
  status: FundingStatus;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type FundingCreate = {
  amount: string;
  currency?: string;
  kind?: FundingKind;
  source?: FundingSource;
  notes?: string | null;
};

// Budget derived from the funding ledger: funded = Σ settled; spent = 0 until agents (0.7.0).
export type ProjectBudget = {
  project_id: string;
  currency: string;
  funded: string;
  spent: string;
  available: string;
  by_source: Record<string, string>;
  by_status: Record<string, string>;
};
