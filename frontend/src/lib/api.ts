import type {
  AgentModels,
  ModelOption,
  Project,
  ProjectCreate,
  ProjectUpdate,
} from "@/types/project";
import type { InstrumentDescriptor, ToolRunRequest, ToolRunResult } from "@/types/toolbench";
import type {
  AccountUpdate,
  Branch,
  BranchClose,
  BranchCreate,
  BranchSummary,
  Checkpoint,
  CheckpointCreate,
  Claim,
  ClaimCreate,
  Evidence,
  EvidenceCreate,
  Funding,
  FundingCreate,
  InvitationCreate,
  Me,
  ProjectBudget,
  ProjectInvitation,
  ProjectMember,
  ProjectOverview,
  ProjectRole,
  Thread,
  ThreadCreate,
  ThreadSummary,
  Validation,
  ValidationCreate,
} from "@/types/research";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

// The acting credential is held module-side and kept in sync by the AuthProvider, so the typed
// api functions stay plain (no token argument threaded through every call). The AuthProvider
// pushes the verified Supabase bearer token here; `request` attaches it when present. Without a
// token, reads still succeed (the backend serves them publicly) and writes are rejected with 401.
let accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

function authHeaders(): Record<string, string> {
  return accessToken ? { Authorization: `Bearer ${accessToken}` } : {};
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    // Surface the backend's `detail` when present so mutation errors are legible.
    let detail = "";
    try {
      const data = (await response.json()) as { detail?: unknown };
      if (typeof data?.detail === "string") {
        detail = data.detail;
      } else if (Array.isArray(data?.detail)) {
        // FastAPI request-validation errors (422) are a list of {msg, loc, ...} objects. Surface the
        // messages (stripping Pydantic v2's "Value error, " prefix) instead of a raw JSON blob.
        detail = (data.detail as Array<{ msg?: unknown }>)
          .map((e) => (typeof e.msg === "string" ? e.msg.replace(/^Value error,\s*/, "") : null))
          .filter((m): m is string => Boolean(m))
          .join("; ");
      } else if (data?.detail != null) {
        detail = JSON.stringify(data.detail);
      }
    } catch {
      // non-JSON error body; fall back to the status code
    }
    throw new Error(detail ? `${response.status}: ${detail}` : `Request failed with ${response.status}`);
  }

  // 204 No Content (e.g. DELETE) carries no body — `response.json()` would throw on the empty
  // payload, so short-circuit to undefined (callers type these as Promise<void>).
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

// A write request body; the acting credential rides on every request via authHeaders().
function writeInit(body: unknown): RequestInit {
  return { method: "POST", body: JSON.stringify(body) };
}

// A partial-update (PATCH) request body — for in-place metadata edits (0.8.1).
function patchInit(body: unknown): RequestInit {
  return { method: "PATCH", body: JSON.stringify(body) };
}

// A full-replace (PUT) request body — e.g. the agent-model roster (0.8.10).
function putInit(body: unknown): RequestInit {
  return { method: "PUT", body: JSON.stringify(body) };
}

// --- Identity ---------------------------------------------------------------

// The resolved acting actor plus its owning account (roles live on the account in 0.7.0), driving
// the identity menu and write gating.
export function getMe(): Promise<Me> {
  return request<Me>("/me");
}

// Edit the caller's own principal — currently just the public `@username` (0.8.3). Throws on a
// 409 (handle taken) or 422 (invalid/reserved), surfaced via the request helper's `detail`.
export function updateMe(payload: AccountUpdate): Promise<Me> {
  return request<Me>("/me", patchInit(payload));
}

// --- Projects ---------------------------------------------------------------

export function listProjects(): Promise<Project[]> {
  return request<Project[]>("/projects");
}

// Create a project (write-gated: the acting actor rides on the request via authHeaders()).
export function createProject(payload: ProjectCreate): Promise<Project> {
  return request<Project>("/projects", writeInit(payload));
}

export function getProject(projectId: string): Promise<Project> {
  return request<Project>(`/projects/${projectId}`);
}

export function getProjectOverview(projectId: string): Promise<ProjectOverview> {
  return request<ProjectOverview>(`/projects/${projectId}/overview`);
}

// Edit project metadata (owner/admin; the acting actor rides on the request). Partial update.
export function updateProject(projectId: string, payload: ProjectUpdate): Promise<Project> {
  return request<Project>(`/projects/${projectId}`, patchInit(payload));
}

// --- Agent models (0.8.10) ---------------------------------------------------

// The curated OpenRouter catalog that populates the role-assignment dropdowns. Public read; the
// list is static so callers can cache it aggressively.
export function getAgentModelCatalog(): Promise<ModelOption[]> {
  return request<ModelOption[]>("/agent-models/catalog");
}

// Replace a project's per-role model roster (owner/admin). Full replace — send the complete map
// (a role omitted/`null` becomes unassigned). Returns the updated project.
export function updateAgentModels(projectId: string, payload: AgentModels): Promise<Project> {
  return request<Project>(`/projects/${projectId}/agent-models`, putInit(payload));
}

// --- Project members / stewardship (0.8.1) ----------------------------------

// Public member list (handles + roles); safe to call unauthenticated.
export function listProjectMembers(projectId: string): Promise<ProjectMember[]> {
  return request<ProjectMember[]>(`/projects/${projectId}/members`);
}

// Remove a member (owner only). 204 No Content — no body to parse.
export async function removeProjectMember(projectId: string, accountId: string): Promise<void> {
  await request<void>(`/projects/${projectId}/members/${accountId}`, { method: "DELETE" });
}

// Change a member's role / transfer ownership (owner only).
export function updateProjectMember(
  projectId: string,
  accountId: string,
  role: ProjectRole,
): Promise<ProjectMember> {
  return request<ProjectMember>(`/projects/${projectId}/members/${accountId}`, patchInit({ role }));
}

// --- Invitations (0.8.7) ----------------------------------------------------

// Invite an existing account by @username or email (owner/admin). Throws on 404 (no such account),
// 409 (self / already a member / already invited), surfaced via the request helper's `detail`.
export function inviteProjectMember(
  projectId: string,
  payload: InvitationCreate,
): Promise<ProjectInvitation> {
  return request<ProjectInvitation>(`/projects/${projectId}/invitations`, writeInit(payload));
}

// A project's outstanding (pending) invitations (owner/admin only).
export function listProjectInvitations(projectId: string): Promise<ProjectInvitation[]> {
  return request<ProjectInvitation[]>(`/projects/${projectId}/invitations`);
}

// Revoke a pending invitation (owner/admin). 204 No Content — no body to parse.
export async function revokeInvitation(projectId: string, invitationId: string): Promise<void> {
  await request<void>(`/projects/${projectId}/invitations/${invitationId}`, { method: "DELETE" });
}

// The caller's own pending invitations (the bell inbox).
export function getMyInvitations(): Promise<ProjectInvitation[]> {
  return request<ProjectInvitation[]>("/me/invitations");
}

// Accept / decline an invitation addressed to the caller (invitee-only).
export function acceptInvitation(invitationId: string): Promise<ProjectInvitation> {
  return request<ProjectInvitation>(`/invitations/${invitationId}/accept`, writeInit({}));
}

export function declineInvitation(invitationId: string): Promise<ProjectInvitation> {
  return request<ProjectInvitation>(`/invitations/${invitationId}/decline`, writeInit({}));
}

// --- Threads ----------------------------------------------------------------

export function listThreads(projectId: string): Promise<ThreadSummary[]> {
  return request<ThreadSummary[]>(`/projects/${projectId}/threads`);
}

export function getThread(threadId: string): Promise<Thread> {
  return request<Thread>(`/threads/${threadId}`);
}

export function createThread(projectId: string, payload: ThreadCreate): Promise<Thread> {
  return request<Thread>(`/projects/${projectId}/threads`, writeInit(payload));
}

// --- Claims -----------------------------------------------------------------

export function listClaims(threadId: string): Promise<Claim[]> {
  return request<Claim[]>(`/threads/${threadId}/claims`);
}

export function createClaim(threadId: string, payload: ClaimCreate): Promise<Claim> {
  return request<Claim>(`/threads/${threadId}/claims`, writeInit(payload));
}

// --- Evidence ---------------------------------------------------------------

export function listEvidence(claimId: string): Promise<Evidence[]> {
  return request<Evidence[]>(`/claims/${claimId}/evidence`);
}

export function attachEvidence(claimId: string, payload: EvidenceCreate): Promise<Evidence> {
  return request<Evidence>(`/claims/${claimId}/evidence`, writeInit(payload));
}

// --- Checkpoints ------------------------------------------------------------

export function listCheckpoints(projectId: string): Promise<Checkpoint[]> {
  return request<Checkpoint[]>(`/projects/${projectId}/checkpoints`);
}

export function createCheckpoint(
  projectId: string,
  payload: CheckpointCreate,
): Promise<Checkpoint> {
  return request<Checkpoint>(`/projects/${projectId}/checkpoints`, writeInit(payload));
}

// --- Validations ------------------------------------------------------------

export function createValidation(
  projectId: string,
  payload: ValidationCreate,
): Promise<Validation> {
  return request<Validation>(`/projects/${projectId}/validations`, writeInit(payload));
}

// --- Branches ---------------------------------------------------------------

export function listBranches(projectId: string): Promise<BranchSummary[]> {
  return request<BranchSummary[]>(`/projects/${projectId}/branches`);
}

export function createBranch(projectId: string, payload: BranchCreate): Promise<Branch> {
  return request<Branch>(`/projects/${projectId}/branches`, writeInit(payload));
}

export function closeBranch(branchId: string, payload: BranchClose): Promise<Branch> {
  return request<Branch>(`/branches/${branchId}/close`, writeInit(payload));
}

// --- Funding (0.6.3) --------------------------------------------------------

export function listFunding(projectId: string): Promise<Funding[]> {
  return request<Funding[]>(`/projects/${projectId}/funding`);
}

export function getProjectBudget(projectId: string): Promise<ProjectBudget> {
  return request<ProjectBudget>(`/projects/${projectId}/budget`);
}

export function createFunding(projectId: string, payload: FundingCreate): Promise<Funding> {
  return request<Funding>(`/projects/${projectId}/funding`, writeInit(payload));
}

// --- Toolbench instruments (0.9.x) ------------------------------------------

// The public instrument catalog (name, schemas, three-outcome contract) — reflects the code
// registry, so it is static reference data and callers can cache it aggressively. Public read.
export function getInstrumentCatalog(): Promise<InstrumentDescriptor[]> {
  return request<InstrumentDescriptor[]>("/instruments");
}

// Run an instrument in a project and land the durable, attributed result in the ledger. Membership
// gated (the acting actor rides on the request). A bad `inputs` payload surfaces as a 422 and mints
// nothing; an unknown instrument name is a 404.
export function runInstrument(
  projectId: string,
  name: string,
  payload: ToolRunRequest,
): Promise<ToolRunResult> {
  return request<ToolRunResult>(
    `/projects/${projectId}/instruments/${encodeURIComponent(name)}/run`,
    writeInit(payload),
  );
}
