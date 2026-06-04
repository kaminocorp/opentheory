import type { Project } from "@/types/project";
import type {
  Actor,
  ActorCreate,
  Checkpoint,
  CheckpointCreate,
  Claim,
  ClaimCreate,
  Evidence,
  EvidenceCreate,
  ProjectOverview,
  Thread,
  ThreadCreate,
  ThreadSummary,
} from "@/types/research";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

// Header carrying the acting dev actor on every write (replaced by real auth in 0.6.0).
const DEV_ACTOR_HEADER = "X-Dev-Actor-Id";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
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

function writeInit(actorId: string, body: unknown): RequestInit {
  return {
    method: "POST",
    body: JSON.stringify(body),
    headers: { [DEV_ACTOR_HEADER]: actorId },
  };
}

// --- Projects ---------------------------------------------------------------

export function listProjects(): Promise<Project[]> {
  return request<Project[]>("/projects");
}

export function getProject(projectId: string): Promise<Project> {
  return request<Project>(`/projects/${projectId}`);
}

export function getProjectOverview(projectId: string): Promise<ProjectOverview> {
  return request<ProjectOverview>(`/projects/${projectId}/overview`);
}

// --- Actors (dev identity; create is the bootstrap path, no acting actor) ----

export function listActors(): Promise<Actor[]> {
  return request<Actor[]>("/actors");
}

export function createActor(payload: ActorCreate): Promise<Actor> {
  return request<Actor>("/actors", { method: "POST", body: JSON.stringify(payload) });
}

// --- Threads ----------------------------------------------------------------

export function listThreads(projectId: string): Promise<ThreadSummary[]> {
  return request<ThreadSummary[]>(`/projects/${projectId}/threads`);
}

export function getThread(threadId: string): Promise<Thread> {
  return request<Thread>(`/threads/${threadId}`);
}

export function createThread(
  projectId: string,
  payload: ThreadCreate,
  actorId: string,
): Promise<Thread> {
  return request<Thread>(`/projects/${projectId}/threads`, writeInit(actorId, payload));
}

// --- Claims -----------------------------------------------------------------

export function listClaims(threadId: string): Promise<Claim[]> {
  return request<Claim[]>(`/threads/${threadId}/claims`);
}

export function createClaim(
  threadId: string,
  payload: ClaimCreate,
  actorId: string,
): Promise<Claim> {
  return request<Claim>(`/threads/${threadId}/claims`, writeInit(actorId, payload));
}

// --- Evidence ---------------------------------------------------------------

export function listEvidence(claimId: string): Promise<Evidence[]> {
  return request<Evidence[]>(`/claims/${claimId}/evidence`);
}

export function attachEvidence(
  claimId: string,
  payload: EvidenceCreate,
  actorId: string,
): Promise<Evidence> {
  return request<Evidence>(`/claims/${claimId}/evidence`, writeInit(actorId, payload));
}

// --- Checkpoints ------------------------------------------------------------

export function listCheckpoints(projectId: string): Promise<Checkpoint[]> {
  return request<Checkpoint[]>(`/projects/${projectId}/checkpoints`);
}

export function createCheckpoint(
  projectId: string,
  payload: CheckpointCreate,
  actorId: string,
): Promise<Checkpoint> {
  return request<Checkpoint>(`/projects/${projectId}/checkpoints`, writeInit(actorId, payload));
}
