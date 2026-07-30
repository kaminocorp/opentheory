"use client";

import { useQuery } from "@tanstack/react-query";
import { useRef, useState, type ReactNode } from "react";

import { AwaitingState, Bay, MetricReadout, ReadoutLabel } from "@/components/console";
import {
  getProject,
  getProjectOverview,
  listBranches,
  listProjectMembers,
  listThreads,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { queryKeys } from "@/lib/query-keys";
import { useActingIdentity } from "@/lib/use-identity";
import { useProjectTab, type ProjectTabId } from "@/lib/use-project-tab";
import type { ProjectCounts } from "@/types/research";

import { AgentPassPanel } from "./agent-pass/agent-pass-panel";
import { BranchBar } from "./branch-bar";
import { CheckpointTimelinePanel } from "./checkpoint-timeline-panel";
import { ClaimListPanel } from "./claim-list-panel";
import { Collaborators } from "./collaborators-panel";
import { FundingPanel } from "./funding-panel";
import { Markdown } from "./markdown";
import { ProjectEditForm } from "./project-edit-form";
import { ProjectHeader } from "./project-header";
import { ProjectTabs, projectPanelDomId, projectTabDomId } from "./project-tabs";
import { ResearchCrewPanel } from "./research-crew-panel";
import { ThreadListPanel } from "./thread-list-panel";
import { ToolbenchPanel } from "./toolbench/toolbench-panel";

type ProjectWorkspaceProps = {
  projectId: string;
};

const COUNT_LABELS: { key: keyof ProjectCounts; label: string }[] = [
  { key: "threads", label: "Threads" },
  { key: "claims", label: "Claims" },
  { key: "evidence", label: "Evidence" },
  { key: "checkpoints", label: "Checkpoints" },
  { key: "validations", label: "Validations" },
  { key: "branches", label: "Branches" },
];

/**
 * The project deepdive (0.14.0): a persistent header + five tabs, with **Research**
 * as the default surface.
 *
 * Before this release the page was a flat vertical stack of nine peer bays — crew,
 * collaborators, budget, and the whole toolbench sat *above* the ledger, so the work
 * the page exists for started below the fold. Nothing was rewritten to fix that: the
 * panels are unchanged and simply regrouped, and this component stays what it already
 * was — the owner of the shared queries and the thread/branch selection everything
 * else reads.
 */
export function ProjectWorkspace({ projectId }: ProjectWorkspaceProps) {
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  // null = the project main line; a branch id scopes the checkpoint timeline + new
  // checkpoints to that line (0.4.2/0.4.3).
  const [selectedBranchId, setSelectedBranchId] = useState<string | null>(null);
  // Project stewardship (0.8.1): the metadata edit form, which renders on Overview.
  const [editing, setEditing] = useState(false);

  const { tab, setTab } = useProjectTab();
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

  // Same query key as ThreadListPanel, so TanStack serves both from one cache entry
  // and one request — this exists only to name the selected thread in the Instruments
  // context readout (a tab away from the list that made the selection).
  const threadsQuery = useQuery({
    queryKey: queryKeys.threads(projectId),
    queryFn: () => listThreads(projectId),
  });
  const selectedThread = threadsQuery.data?.find((t) => t.id === selectedThreadId) ?? null;

  // Cold tabs mount on first activation and then stay mounted. Research and
  // Instruments start mounted because they are the hot path and share selection
  // state — and because AgentPassPanel polls a live run from local state, so
  // unmounting Instruments would silently kill an in-flight trace (§5.2).
  const visitedTabs = useRef(new Set<ProjectTabId>(["research", "instruments"]));
  visitedTabs.current.add(tab);

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
  const counts = overviewQuery.data?.counts ?? null;

  // The toggle lives in the header (visible on every tab) but the form renders on
  // Overview — so opening it has to bring Overview with it.
  function handleToggleEdit() {
    const next = !editing;
    setEditing(next);
    if (next) setTab("overview");
  }

  return (
    <div className="grid gap-5">
      <ProjectHeader
        project={project}
        canManage={canManageProject}
        editing={editing}
        onToggleEdit={handleToggleEdit}
        counts={counts}
        countsError={overviewQuery.isError}
        contradictions={contradictions}
        onShowContested={() => setTab("research")}
      />

      <ProjectTabs
        active={tab}
        onSelect={setTab}
        badges={{
          research: contradictions.length ? { count: contradictions.length, tone: "fail" } : null,
          crew: membersQuery.data ? { count: membersQuery.data.length } : null,
        }}
      />

      {/* --- research (default, keep-alive) ------------------------------------ */}
      <TabPanel tab="research" active={tab} mounted>
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
      </TabPanel>

      {/* --- instruments (keep-alive: an agent trace may be polling) ------------ */}
      <TabPanel tab="instruments" active={tab} mounted>
        <InstrumentContext
          threadTitle={selectedThread?.title ?? null}
          branchName={selectedBranch?.name ?? "main line"}
          lineSealed={lineSealed}
        />
        {/* Toolbench (0.9.x): run a deterministic maths instrument and land the result in
            the ledger, scoped to the thread + branch selected on Research. Runs are
            membership-gated; the catalog is public. Produced checkpoints appear on the
            Research timeline. */}
        <ToolbenchPanel
          projectId={projectId}
          selectedThreadId={selectedThreadId}
          selectedBranchId={selectedBranchId}
          lineSealed={lineSealed}
          canRun={canManageProject}
        />
        {/* Agent pass (0.12.4): the Research crew plans + runs a bounded sequence of the
            same instruments on the selected thread, landing attributed checkpoints on a
            durable agent branch. The backend picks that branch, so no branch prop is
            threaded in. Member-gated; dark-launch-aware. */}
        <AgentPassPanel
          projectId={projectId}
          selectedThreadId={selectedThreadId}
          canRun={canManageProject}
          agentModels={project.agent_models}
          onSelectBranch={(branchId) => {
            setSelectedBranchId(branchId);
            setTab("research");
          }}
        />
      </TabPanel>

      {/* --- crew (lazy) -------------------------------------------------------- */}
      <TabPanel tab="crew" active={tab} mounted={visitedTabs.current.has("crew")}>
        <div className="grid gap-4 lg:grid-cols-2">
          <ResearchCrewPanel
            projectId={projectId}
            agentModels={project.agent_models}
            canManage={canManageProject}
          />
          <Collaborators projectId={projectId} />
        </div>
      </TabPanel>

      {/* --- funding (lazy) ----------------------------------------------------- */}
      <TabPanel tab="funding" active={tab} mounted={visitedTabs.current.has("funding")}>
        <FundingPanel projectId={projectId} />
      </TabPanel>

      {/* --- overview (lazy): the reference surface ----------------------------- */}
      <TabPanel tab="overview" active={tab} mounted={visitedTabs.current.has("overview")}>
        {editing && canManageProject ? (
          <ProjectEditForm project={project} onDone={() => setEditing(false)} />
        ) : null}

        {project.description || project.background ? (
          <Bay density="narrative" className="grid gap-3">
            <ReadoutLabel as="h2">Background / Context</ReadoutLabel>
            {project.description ? (
              <p className="max-w-3xl text-[14px] leading-[1.55] text-text-soft">
                {project.description}
              </p>
            ) : null}
            {project.background ? <Markdown>{project.background}</Markdown> : null}
          </Bay>
        ) : null}

        <Bay density="narrative" className="grid gap-3">
          <ReadoutLabel as="h2">Ledger totals</ReadoutLabel>
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {COUNT_LABELS.map(({ key, label }) => (
              <MetricReadout
                key={key}
                label={label}
                value={
                  counts ? (
                    counts[key]
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
      </TabPanel>
    </div>
  );
}

type TabPanelProps = {
  tab: ProjectTabId;
  active: ProjectTabId;
  /** False until the tab is first activated — cold surfaces don't fetch on load. */
  mounted: boolean;
  children: ReactNode;
};

/**
 * One tabpanel. The element always renders (so each tab's `aria-controls` resolves
 * even before its contents mount); only the contents are gated on `mounted`.
 *
 * Visibility is toggled on the *outer* element, which carries no other display
 * class — `cn` is a plain joiner with no tailwind-merge, so pairing `hidden` with
 * `grid` on one element would leave the outcome to CSS source order (the layering
 * footgun fixed in 0.6.6). Layout classes therefore live on the inner wrapper.
 */
function TabPanel({ tab, active, mounted, children }: TabPanelProps) {
  const isHidden = tab !== active;

  return (
    <div
      id={projectPanelDomId(tab)}
      role="tabpanel"
      aria-labelledby={projectTabDomId(tab)}
      tabIndex={isHidden ? -1 : 0}
      hidden={isHidden}
      className={cn(isHidden && "hidden")}
    >
      {mounted ? <div className="grid gap-4">{children}</div> : null}
    </div>
  );
}

/**
 * The Instruments context readout: which thread and line a run will land on. The
 * selection is made on Research, a tab away, so the toolbench has to restate it —
 * otherwise a member can run an instrument without seeing what it attaches to.
 * Read-only by design; BranchBar stays the single branch *selector*.
 */
function InstrumentContext({
  threadTitle,
  branchName,
  lineSealed,
}: {
  threadTitle: string | null;
  branchName: string;
  lineSealed: boolean;
}) {
  return (
    <div
      className="sticky top-12 z-10 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-built bg-panel-2 px-3 py-2 font-mono text-[11px]"
      style={{ border: "0.5px solid var(--hairline)" }}
    >
      <span className="font-medium uppercase tracking-[0.14em] text-text-mute">Thread</span>
      <span className={cn("truncate", threadTitle ? "text-text" : "text-text-faint")}>
        {threadTitle ?? "none selected — pick one on Research"}
      </span>
      <span aria-hidden className="text-text-faint">
        ·
      </span>
      <span className="font-medium uppercase tracking-[0.14em] text-text-mute">Line</span>
      <span className="truncate text-text">{branchName}</span>
      {lineSealed ? (
        <span className="font-medium uppercase tracking-[0.14em] text-state-warn">· sealed</span>
      ) : null}
    </div>
  );
}
