import type { Project, ProjectCreate } from "@/types/project";
import type {
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
  Me,
  ProjectBudget,
  ProjectOverview,
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
      } else if (data?.detail != null) {
        detail = JSON.stringify(data.detail);
      }
    } catch {
      // non-JSON error body; fall back to the status code
    }
    throw new Error(detail ? `${response.status}: ${detail}` : `Request failed with ${response.status}`);
  }

  return response.json() as Promise<T>;
}

// A write request body; the acting credential rides on every request via authHeaders().
function writeInit(body: unknown): RequestInit {
  return { method: "POST", body: JSON.stringify(body) };
}

// --- Identity ---------------------------------------------------------------

// The resolved acting actor plus its owning account (roles live on the account in 0.7.0), driving
// the identity menu and write gating.
export function getMe(): Promise<Me> {
  return request<Me>("/me");
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
