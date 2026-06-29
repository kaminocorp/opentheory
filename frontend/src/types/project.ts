export type ProjectStatus = "draft" | "active" | "paused" | "completed" | "archived";

export type Project = {
  id: string;
  title: string;
  slug: string;
  question: string;
  description: string | null;
  // Deep, optional long-form briefing as Markdown (0.8.1).
  background: string | null;
  status: ProjectStatus;
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
