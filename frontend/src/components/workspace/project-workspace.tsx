"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { AwaitingState, Bay, Icon, MetricReadout, StatusPill, type StateTone } from "@/components/console";
import { getProject, getProjectOverview, listBranches } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import type { Project } from "@/types/project";

import { BranchBar } from "./branch-bar";
import { CheckpointTimelinePanel } from "./checkpoint-timeline-panel";
import { ClaimListPanel } from "./claim-list-panel";
import { FundingPanel } from "./funding-panel";
import { ThreadListPanel } from "./thread-list-panel";

type ProjectWorkspaceProps = {
  projectId: string;
};

const COUNT_LABELS: {
  key: "threads" | "claims" | "evidence" | "checkpoints" | "validations" | "branches";
  label: string;
}[] = [
  { key: "threads", label: "Threads" },
  { key: "claims", label: "Claims" },
  { key: "evidence", label: "Evidence" },
  { key: "checkpoints", label: "Checkpoints" },
  { key: "validations", label: "Validations" },
  { key: "branches", label: "Branches" },
];

// Project status → a state tone (glyph + colour survive grayscale).
const projectStatusTone: Record<Project["status"], StateTone> = {
  draft: "mute",
  active: "run",
  paused: "warn",
  completed: "ok",
  archived: "faint",
};

export function ProjectWorkspace({ projectId }: ProjectWorkspaceProps) {
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  // null = the project main line; a branch id scopes the checkpoint timeline + new
  // checkpoints to that line (0.4.2/0.4.3).
  const [selectedBranchId, setSelectedBranchId] = useState<string | null>(null);

  const projectQuery = useQuery({
    queryKey: queryKeys.project(projectId),
    queryFn: () => getProject(projectId),
  });

  const overviewQuery = useQuery({
    queryKey: queryKeys.overview(projectId),
    queryFn: () => getProjectOverview(projectId),
  });

  // Branches drive the line selector (in BranchBar) and tell the timeline whether the
  // selected line is sealed (closed/dead-end) — a sealed line can't receive checkpoints.
  const branchesQuery = useQuery({
    queryKey: queryKeys.branches(projectId),
    queryFn: () => listBranches(projectId),
  });
  const selectedBranch = branchesQuery.data?.find((b) => b.id === selectedBranchId) ?? null;
  const lineSealed = selectedBranch !== null && selectedBranch.status !== "open";

  if (projectQuery.isLoading) {
    return (
      <Bay className="grid min-h-80 place-items-center">
        <AwaitingState variant="loading" label="loading project" />
      </Bay>
    );
  }

  if (projectQuery.isError || !projectQuery.data) {
    return (
      <Bay className="grid min-h-80 place-items-center">
        <AwaitingState variant="error" label="project unavailable" />
      </Bay>
    );
  }

  const project = projectQuery.data;
  const contradictions = overviewQuery.data?.contradictions ?? [];

  return (
    <div className="grid gap-5">
      {/* Back link — the ActionText register (text → signal on hover), with a ←. */}
      <Link
        href="/"
        className="inline-flex w-fit items-center gap-1.5 text-[13px] font-medium text-text-mute transition-colors hover:text-signal"
      >
        <Icon icon={ArrowLeft} size={14} />
        Projects
      </Link>

      <Bay as="header" bracketed chamfer density="narrative" className="grid gap-3">
        <StatusPill tone={projectStatusTone[project.status]} label={project.status} />
        <h1 className="text-balance text-2xl font-medium leading-snug text-text">{project.title}</h1>
        <p className="max-w-3xl text-[14px] leading-[1.55] text-text-soft">{project.question}</p>
        {project.description ? (
          <p className="max-w-3xl text-[14px] leading-[1.5] text-text-mute">{project.description}</p>
        ) : null}

        {/* Honesty surface (§1): contested claims float above the counts at equal
            weight, marked by a state-fail edge tick + glyph + label — never softened. */}
        {contradictions.length > 0 ? (
          <div className="relative rounded-built bg-panel-2 p-3 pl-4">
            <span aria-hidden className="absolute inset-y-0 left-0 w-0.5 bg-state-fail" />
            <p className="flex items-center gap-1.5">
              <Icon icon={AlertTriangle} size={14} className="text-state-fail" />
              <span className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-state-fail">
                {contradictions.length} contested claim{contradictions.length === 1 ? "" : "s"}
              </span>
            </p>
            <ul className="mt-2 grid gap-1">
              {contradictions.map((item) => (
                <li key={item.claim_id} className="truncate text-[13px] leading-[1.5] text-text-soft">
                  {item.statement}
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <dl
          className="grid grid-cols-2 gap-3 pt-1 sm:grid-cols-3 lg:grid-cols-6"
        >
          {COUNT_LABELS.map(({ key, label }) => (
            <MetricReadout
              key={key}
              label={label}
              value={
                overviewQuery.data ? (
                  overviewQuery.data.counts[key]
                ) : overviewQuery.isError ? (
                  "—"
                ) : (
                  <span
                    aria-hidden
                    className="inline-block h-5 w-6 animate-pulse rounded-inset bg-text-faint/25 align-middle"
                  />
                )
              }
            />
          ))}
        </dl>
      </Bay>

      <FundingPanel projectId={projectId} />

      <BranchBar
        projectId={projectId}
        selectedBranchId={selectedBranchId}
        onSelectBranch={setSelectedBranchId}
      />

      <div className="enter-stagger grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)_340px]">
        <ThreadListPanel
          projectId={projectId}
          selectedThreadId={selectedThreadId}
          onSelectThread={setSelectedThreadId}
        />
        <ClaimListPanel projectId={projectId} threadId={selectedThreadId} />
        <CheckpointTimelinePanel
          projectId={projectId}
          selectedThreadId={selectedThreadId}
          selectedBranchId={selectedBranchId}
          lineSealed={lineSealed}
        />
      </div>
    </div>
  );
}
