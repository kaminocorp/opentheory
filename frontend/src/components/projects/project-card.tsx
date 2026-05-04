import { ArrowUpRight, GitBranch, Landmark, ShieldCheck } from "lucide-react";

import type { Project } from "@/types/project";

const statusLabels: Record<Project["status"], string> = {
  draft: "Draft",
  active: "Active",
  paused: "Paused",
  completed: "Completed",
  archived: "Archived",
};

type ProjectCardProps = {
  project: Project;
};

export function ProjectCard({ project }: ProjectCardProps) {
  return (
    <article className="grid gap-4 rounded-lg border border-line bg-white/75 p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-signal">
            {statusLabels[project.status]}
          </p>
          <h3 className="text-balance text-xl font-semibold">{project.title}</h3>
        </div>
        <a
          href={`/projects/${project.id}`}
          className="grid size-9 shrink-0 place-items-center rounded-md border border-line text-ink/60 hover:border-ink/30 hover:text-ink"
          aria-label={`Open ${project.title}`}
          title={`Open ${project.title}`}
        >
          <ArrowUpRight className="size-4" aria-hidden="true" />
        </a>
      </div>

      <p className="text-sm leading-6 text-ink/70">{project.question}</p>

      {project.description ? (
        <p className="line-clamp-3 text-sm leading-6 text-ink/60">{project.description}</p>
      ) : null}

      <div className="grid grid-cols-3 gap-2 border-t border-line pt-4 text-xs text-ink/60">
        <span className="flex items-center gap-1.5">
          <GitBranch className="size-3.5" aria-hidden="true" />
          Threads
        </span>
        <span className="flex items-center gap-1.5">
          <ShieldCheck className="size-3.5" aria-hidden="true" />
          Validation
        </span>
        <span className="flex items-center gap-1.5">
          <Landmark className="size-3.5" aria-hidden="true" />
          Funding
        </span>
      </div>
    </article>
  );
}
