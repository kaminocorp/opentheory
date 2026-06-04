"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, AlertCircle, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { getProject, getProjectOverview } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";

import { CheckpointTimelinePanel } from "./checkpoint-timeline-panel";
import { ClaimListPanel } from "./claim-list-panel";
import { ThreadListPanel } from "./thread-list-panel";

type ProjectWorkspaceProps = {
  projectId: string;
};

const COUNT_LABELS: { key: "threads" | "claims" | "evidence" | "checkpoints"; label: string }[] = [
  { key: "threads", label: "Threads" },
  { key: "claims", label: "Claims" },
  { key: "evidence", label: "Evidence" },
  { key: "checkpoints", label: "Checkpoints" },
];

export function ProjectWorkspace({ projectId }: ProjectWorkspaceProps) {
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);

  const projectQuery = useQuery({
    queryKey: queryKeys.project(projectId),
    queryFn: () => getProject(projectId),
  });

  const overviewQuery = useQuery({
    queryKey: queryKeys.overview(projectId),
    queryFn: () => getProjectOverview(projectId),
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

  if (projectQuery.isError || !projectQuery.data) {
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

  return (
    <div className="grid gap-5">
      <Link
        href="/"
        className="inline-flex w-fit items-center gap-2 text-sm font-medium text-ink/65 hover:text-ink"
      >
        <ArrowLeft className="size-4" aria-hidden="true" />
        Projects
      </Link>

      <header className="grid gap-3 rounded-lg border border-line bg-white/75 p-6 shadow-panel">
        <p className="text-sm font-semibold uppercase tracking-[0.14em] text-signal">{project.status}</p>
        <h1 className="text-balance text-2xl font-semibold sm:text-3xl">{project.title}</h1>
        <p className="max-w-3xl text-sm leading-7 text-ink/70">{project.question}</p>
        {project.description ? (
          <p className="max-w-3xl text-sm leading-6 text-ink/60">{project.description}</p>
        ) : null}

        <dl className="mt-1 grid grid-cols-2 gap-3 border-t border-line pt-4 sm:grid-cols-4">
          {COUNT_LABELS.map(({ key, label }) => (
            <div key={key} className="rounded-md border border-line bg-paper/60 px-3 py-2">
              <dt className="text-[11px] font-semibold uppercase tracking-[0.1em] text-ink/50">{label}</dt>
              <dd className="mt-0.5 text-xl font-semibold tabular-nums">
                {overviewQuery.data ? (
                  overviewQuery.data.counts[key]
                ) : overviewQuery.isError ? (
                  "—"
                ) : (
                  <span
                    className="inline-block h-5 w-6 animate-pulse rounded bg-line/70 align-middle"
                    aria-hidden="true"
                  />
                )}
              </dd>
            </div>
          ))}
        </dl>
      </header>

      <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)_340px]">
        <ThreadListPanel
          projectId={projectId}
          selectedThreadId={selectedThreadId}
          onSelectThread={setSelectedThreadId}
        />
        <ClaimListPanel projectId={projectId} threadId={selectedThreadId} />
        <CheckpointTimelinePanel projectId={projectId} selectedThreadId={selectedThreadId} />
      </div>
    </div>
  );
}
