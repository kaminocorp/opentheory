"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, AlertCircle, Plus } from "lucide-react";

import { listProjects } from "@/lib/api";

import { ProjectCard } from "./project-card";

export function ProjectList() {
  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
  });

  if (projectsQuery.isLoading) {
    return (
      <div className="grid min-h-72 place-items-center rounded-lg border border-line bg-white/65">
        <div className="flex items-center gap-3 text-sm text-ink/65">
          <Activity className="size-4 animate-pulse text-signal" aria-hidden="true" />
          Loading projects
        </div>
      </div>
    );
  }

  if (projectsQuery.isError) {
    return (
      <div className="grid min-h-72 place-items-center rounded-lg border border-ember/30 bg-white/75 p-6 text-center">
        <div className="max-w-sm">
          <AlertCircle className="mx-auto mb-3 size-6 text-ember" aria-hidden="true" />
          <h2 className="text-lg font-semibold">Project index unavailable</h2>
          <p className="mt-2 text-sm leading-6 text-ink/65">
            The backend did not return project data.
          </p>
        </div>
      </div>
    );
  }

  const projects = projectsQuery.data ?? [];

  if (projects.length === 0) {
    return (
      <div className="grid min-h-72 place-items-center rounded-lg border border-line bg-white/75 p-6 text-center">
        <div className="max-w-sm">
          <Plus className="mx-auto mb-3 size-6 text-signal" aria-hidden="true" />
          <h2 className="text-lg font-semibold">No projects yet</h2>
          <p className="mt-2 text-sm leading-6 text-ink/65">
            New research projects will appear here once they are created.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {projects.map((project) => (
        <ProjectCard key={project.id} project={project} />
      ))}
    </div>
  );
}
