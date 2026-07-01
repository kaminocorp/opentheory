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
  members: (projectId: string) => ["members", projectId] as const,
  // The curated OpenRouter model catalog (0.8.10) — static, so it can cache indefinitely.
  agentModelCatalog: ["agent-models", "catalog"] as const,
  // The toolbench instrument catalog (0.9.x) — reflects the code registry, so it is static and
  // caches indefinitely, like the agent-model catalog above.
  instrumentCatalog: ["instruments", "catalog"] as const,
  // Invitations (0.8.7): the caller's bell inbox + a project's outstanding invites.
  myInvitations: ["me", "invitations"] as const,
  projectInvitations: (projectId: string) => ["invitations", projectId] as const,
};
