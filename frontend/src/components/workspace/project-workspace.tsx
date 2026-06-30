"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeft, ChevronDown, ChevronRight, Pencil, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import {
  ActionGhost,
  AwaitingState,
  Bay,
  Icon,
  MetricReadout,
  ReadoutLabel,
  StatusPill,
  type StateTone,
} from "@/components/console";
import { getProject, getProjectOverview, listBranches, listProjectMembers } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useActingIdentity } from "@/lib/use-identity";
import type { Project } from "@/types/project";

import { BranchBar } from "./branch-bar";
import { CheckpointTimelinePanel } from "./checkpoint-timeline-panel";
import { ClaimListPanel } from "./claim-list-panel";
import { Collaborators } from "./collaborators-panel";
import { FundingPanel } from "./funding-panel";
import { Markdown } from "./markdown";
import { ProjectEditForm } from "./project-edit-form";
import { ResearchCrewPanel } from "./research-crew-panel";
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
  archived: "faint",
};

export function ProjectWorkspace({ projectId }: ProjectWorkspaceProps) {
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  // null = the project main line; a branch id scopes the checkpoint timeline + new
  // checkpoints to that line (0.4.2/0.4.3).
  const [selectedBranchId, setSelectedBranchId] = useState<string | null>(null);
  // Project stewardship (0.8.1): the metadata edit form + the background collapsible.
  const [editing, setEditing] = useState(false);
  const [backgroundOpen, setBackgroundOpen] = useState(true);

  const { isAuthed, me } = useActingIdentity();

  const projectQuery = useQuery({
    queryKey: queryKeys.project(projectId),
    queryFn: () => getProject(projectId),
  });

  // Membership drives the client-side capability gate (the backend still authorizes every write):
  // an actor can manage iff its account holds a membership row. Public read, so it loads for anyone.
  const membersQuery = useQuery({
    queryKey: queryKeys.members(projectId),
    queryFn: () => listProjectMembers(projectId),
  });
  const canManageProject =
    isAuthed && (membersQuery.data ?? []).some((m) => m.account.id === me?.account?.id);

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
        <div className="flex items-start justify-between gap-3">
          <StatusPill tone={projectStatusTone[project.status]} label={project.status} />
          {/* Collaborators (avatar stack → modal) sit beside the Edit control; the stack is public,
              the Edit write affordance is owner/admin only (the backend still authorizes the PATCH). */}
          <div className="flex items-center gap-3">
            <Collaborators projectId={projectId} />
            {canManageProject ? (
              <ActionGhost size="sm" onClick={() => setEditing((v) => !v)}>
                <Icon icon={editing ? X : Pencil} size={14} />
                {editing ? "Cancel" : "Edit"}
              </ActionGhost>
            ) : null}
          </div>
        </div>
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

      {/* Metadata edit form (0.8.1) — owner/admin only, toggled from the header. */}
      {editing && canManageProject ? (
        <ProjectEditForm project={project} onDone={() => setEditing(false)} />
      ) : null}

      {/* Research crew (0.8.10): which model powers each research role. High in the page — it is
          project configuration, read-only for visitors and assignable by owner/admin. */}
      <ResearchCrewPanel
        projectId={projectId}
        agentModels={project.agent_models}
        canManage={canManageProject}
      />

      {/* Background / Context (0.8.1): a collapsible Bay rendering the stored Markdown. Only shown
          when present; the editor lives in the edit form, the read path uses the light renderer. */}
      {project.background ? (
        <Bay density="narrative" className="grid gap-3">
          <button
            type="button"
            aria-expanded={backgroundOpen}
            onClick={() => setBackgroundOpen((v) => !v)}
            className="flex items-center gap-2 text-text-mute transition-colors hover:text-text"
          >
            <Icon icon={backgroundOpen ? ChevronDown : ChevronRight} size={14} />
            <ReadoutLabel>Background / Context</ReadoutLabel>
          </button>
          {backgroundOpen ? <Markdown>{project.background}</Markdown> : null}
        </Bay>
      ) : null}

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
