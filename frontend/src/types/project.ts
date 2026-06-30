// Mirrors the backend `ProjectStatus` enum exactly (models/enums.py). No `completed` — the backend
// has no such status, so the frontend must not type-permit a value a save would 422 on.
export type ProjectStatus = "draft" | "active" | "paused" | "archived";

// Which OpenRouter model powers each research role (0.8.10). Config, *not* credit. A `null` role is
// unassigned. Mirrors the backend `AgentModels`; the API always returns all four keys.
export type AgentRole = "research_lead" | "thread_manager" | "researcher" | "research_assistant";

export type AgentModels = {
  research_lead: string | null;
  thread_manager: string | null;
  researcher: string | null;
  research_assistant: string | null;
};

// One entry in the curated OpenRouter catalog (`GET /agent-models/catalog`). `id` is the slug
// stored on the project; `name` is the label; `provider` groups the dropdown.
export type ModelOption = {
  id: string;
  name: string;
  provider: string;
};

export type Project = {
  id: string;
  title: string;
  slug: string;
  question: string;
  description: string | null;
  // Deep, optional long-form briefing as Markdown (0.8.1).
  background: string | null;
  status: ProjectStatus;
  // Per-role model roster (0.8.10).
  agent_models: AgentModels;
  created_at: string;
  updated_at: string;
};

export type ProjectCreate = {
  title: string;
  slug: string;
  question: string;
  description?: string | null;
  background?: string | null;
  status?: ProjectStatus;
};

// Partial metadata update (0.8.1): every field optional; `slug` is immutable so it is absent.
// Mirrors the backend ProjectUpdate (applied with exclude_unset).
export type ProjectUpdate = {
  title?: string;
  question?: string;
  description?: string | null;
  background?: string | null;
  status?: ProjectStatus;
};
