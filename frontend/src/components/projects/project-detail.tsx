"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, AlertCircle, ArrowLeft, GitCommitHorizontal, ListChecks } from "lucide-react";
import Link from "next/link";

import { getProject } from "@/lib/api";

type ProjectDetailProps = {
  projectId: string;
};

export function ProjectDetail({ projectId }: ProjectDetailProps) {
  const projectQuery = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId),
  });

  if (projectQuery.isLoading) {
    return (
      <div className="grid min-h-80 place-items-center rounded-lg border border-line bg-white/70">
        <div className="flex items-center gap-3 text-sm text-ink/65">
          <Activity className="size-4 animate-pulse text-signal" aria-hidden="true" />
          Loading project
        </div>
      </div>
    );
  }

  if (projectQuery.isError) {
    return (
      <div className="grid min-h-80 place-items-center rounded-lg border border-ember/30 bg-white/75 p-6 text-center">
        <div className="max-w-sm">
          <AlertCircle className="mx-auto mb-3 size-6 text-ember" aria-hidden="true" />
          <h1 className="text-lg font-semibold">Project unavailable</h1>
          <p className="mt-2 text-sm leading-6 text-ink/65">The requested project could not be loaded.</p>
        </div>
      </div>
    );
  }

  const project = projectQuery.data;

  if (!project) {
    return null;
  }

  return (
    <div className="grid gap-6">
      <Link href="/" className="inline-flex w-fit items-center gap-2 text-sm font-medium text-ink/65 hover:text-ink">
        <ArrowLeft className="size-4" aria-hidden="true" />
        Projects
      </Link>

      <section className="grid gap-5 rounded-lg border border-line bg-white/75 p-6 shadow-panel">
        <div>
          <p className="mb-3 text-sm font-semibold uppercase tracking-[0.14em] text-signal">{project.status}</p>
          <h1 className="text-balance text-3xl font-semibold sm:text-4xl">{project.title}</h1>
          <p className="mt-4 max-w-3xl text-base leading-7 text-ink/70">{project.question}</p>
        </div>

        {project.description ? <p className="max-w-3xl text-sm leading-6 text-ink/65">{project.description}</p> : null}

        <div className="grid gap-3 border-t border-line pt-5 md:grid-cols-2">
          <div className="rounded-md border border-line bg-paper/70 p-4">
            <GitCommitHorizontal className="mb-3 size-5 text-signal" aria-hidden="true" />
            <h2 className="font-semibold">Checkpoint Ledger</h2>
            <p className="mt-2 text-sm leading-6 text-ink/65">Research state changes will collect here.</p>
          </div>
          <div className="rounded-md border border-line bg-paper/70 p-4">
            <ListChecks className="mb-3 size-5 text-signal" aria-hidden="true" />
            <h2 className="font-semibold">Claims and Evidence</h2>
            <p className="mt-2 text-sm leading-6 text-ink/65">Validated claims will link to artifacts and evidence.</p>
          </div>
        </div>
      </section>
    </div>
  );
}
