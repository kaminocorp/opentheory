// Centralized TanStack Query keys so reads and the mutations that invalidate them
// stay in sync.

export const queryKeys = {
  me: ["me"] as const,
  projects: ["projects"] as const,
  project: (projectId: string) => ["project", projectId] as const,
  overview: (projectId: string) => ["overview", projectId] as const,
  threads: (projectId: string) => ["threads", projectId] as const,
  claims: (threadId: string) => ["claims", threadId] as const,
  evidence: (claimId: string) => ["evidence", claimId] as const,
  checkpoints: (projectId: string) => ["checkpoints", projectId] as const,
  branches: (projectId: string) => ["branches", projectId] as const,
  funding: (projectId: string) => ["funding", projectId] as const,
  budget: (projectId: string) => ["budget", projectId] as const,
};
