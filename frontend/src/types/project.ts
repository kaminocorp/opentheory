export type ProjectStatus = "draft" | "active" | "paused" | "completed" | "archived";

export type Project = {
  id: string;
  title: string;
  slug: string;
  question: string;
  description: string | null;
  status: ProjectStatus;
  created_at: string;
  updated_at: string;
};
