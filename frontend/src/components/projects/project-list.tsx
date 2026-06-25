"use client";

import { useQuery } from "@tanstack/react-query";

import { AwaitingState, Bay } from "@/components/console";

import { listProjects } from "@/lib/api";

import { ProjectCard } from "./project-card";

const FRAME = "grid min-h-72 place-items-center";

export function ProjectList() {
  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
  });

  if (projectsQuery.isLoading) {
    return (
      <Bay className={FRAME}>
        <AwaitingState variant="loading" label="loading projects" />
      </Bay>
    );
  }

  if (projectsQuery.isError) {
    // Honest error (§1/§5.9): the mark stops breathing and holds steady at equal
    // weight — "stopped", not a softened or hidden failure.
    return (
      <Bay className={FRAME}>
        <AwaitingState variant="error" label="project index unavailable" />
      </Bay>
    );
  }

  const projects = projectsQuery.data ?? [];

  if (projects.length === 0) {
    return (
      <Bay className={FRAME}>
        <AwaitingState variant="empty" label="no projects yet" />
      </Bay>
    );
  }

  return (
    <div className="enter-stagger grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {projects.map((project) => (
        <ProjectCard key={project.id} project={project} />
      ))}
    </div>
  );
}
