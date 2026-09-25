"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  Action,
  ActionGhost,
  AwaitingState,
  Bay,
  Icon,
  LiveDot,
  ReadoutLabel,
  Select,
  StatusPill,
  type StateTone,
} from "@/components/console";
import {
  cancelOrchestration,
  getOrchestration,
  isAgentLoopDisabled,
  listCampaigns,
  listOrchestrations,
  triggerOrchestration,
} from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useActingIdentity } from "@/lib/use-identity";
import type { AgentModels, AgentRole } from "@/types/project";
import type { OrchestrationRunRead, OrchestrationRunStatus } from "@/types/orchestration";

const ROLES: { key: AgentRole; label: string }[] = [
  { key: "research_lead", label: "Research Lead" },
  { key: "thread_manager", label: "Thread Manager" },
  { key: "researcher", label: "Researcher" },
  { key: "research_assistant", label: "Research Assistant" },
];

const STATUS_TONE: Record<OrchestrationRunStatus, StateTone> = {
  running: "run",
  completed: "ok",
  failed: "fail",
};

const STOP_COPY: Record<string, string> = {
  budget_exhausted: "Stopped — project budget exhausted.",
  no_open_work: "Stopped — no open raisable work.",
  max_passes: "Stopped — pass cap reached.",
  cancelled: "Stopped — cancelled.",
  error: "Stopped — the loop failed.",
};

function stopLine(run: OrchestrationRunRead): string {
  if (run.status === "running") {
    if (run.cancel_requested) return "Stopping after the current wave…";
    if (run.concurrency > 1) {
      return `Allocating up to ${run.concurrency} passes at a time across open threads…`;
    }
    return "Allocating passes across open threads…";
  }
  if (run.stop_reason && STOP_COPY[run.stop_reason]) return STOP_COPY[run.stop_reason];
  if (run.error) return run.error;
  return "Finished.";
}

function decisionAside(decision: OrchestrationRunRead["decisions"][number]): string {
  const parts = [decision.action];
  if (decision.reason) parts.push(decision.reason);
  if (decision.action === "commissioned" && decision.parallel_with?.length) {
    parts.push("in parallel");
  }
  return parts.join(" · ");
}

/**
 * Quiet project-level "Run research" control (0.22.0). Lives on Overview next to
 * the budget: humans set the question, roster, and pot — then leave. One
 * orchestration commissions capped agent passes across open threads against the
 * shared ComputeDebit ceiling. Dark-launch-aware via the same 404 feature-detect
 * as a single agent pass.
 */
export function RunResearchBay({
  projectId,
  canRun,
  agentModels,
}: {
  projectId: string;
  canRun: boolean;
  agentModels: AgentModels;
}) {
  const [role, setRole] = useState<AgentRole>("researcher");
  const [activeId, setActiveId] = useState<string | null>(null);
  const { isAuthed, hydrated } = useActingIdentity();
  const queryClient = useQueryClient();

  const listQuery = useQuery({
    queryKey: queryKeys.orchestrations(projectId),
    queryFn: () => listOrchestrations(projectId),
    retry: false,
  });
  const featureDisabled = isAgentLoopDisabled(listQuery.error);
  const campaignsQuery = useQuery({
    queryKey: queryKeys.campaigns(projectId),
    queryFn: () => listCampaigns(projectId),
    enabled: !featureDisabled,
    retry: false,
  });
  const campaignRunning = campaignsQuery.data?.[0]?.status === "running";
  const latest = listQuery.data?.[0] ?? null;
  const runId = activeId ?? latest?.id ?? null;

  const runQuery = useQuery({
    queryKey: queryKeys.orchestration(runId ?? ""),
    queryFn: () => getOrchestration(runId as string),
    enabled: Boolean(runId) && !featureDisabled,
    refetchInterval: (query) => (query.state.data?.status === "running" ? 1200 : false),
  });
  const run = runQuery.data;
  const prevStatus = useRef<OrchestrationRunStatus | undefined>(undefined);
  useEffect(() => {
    const status = run?.status;
    if (prevStatus.current === "running" && status && status !== "running") {
      queryClient.invalidateQueries({ queryKey: queryKeys.overview(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.budget(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.funding(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.threads(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.checkpoints(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.branches(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.campaigns(projectId) });
    }
    prevStatus.current = status;
  }, [run?.status, projectId, queryClient]);

  const roleModel = agentModels?.[role] ?? null;
  const roleLabel = ROLES.find((r) => r.key === role)?.label ?? role;

  const trigger = useMutation({
    mutationFn: () => triggerOrchestration(projectId, { role }),
    onSuccess: (started) => {
      setActiveId(started.id);
      queryClient.setQueryData(queryKeys.orchestration(started.id), started);
      queryClient.invalidateQueries({ queryKey: queryKeys.orchestrations(projectId) });
    },
  });
  const cancel = useMutation({
    mutationFn: () => cancelOrchestration(run?.id as string),
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKeys.orchestration(updated.id), updated);
      queryClient.invalidateQueries({ queryKey: queryKeys.orchestrations(projectId) });
    },
  });

  const running = run?.status === "running";
  const inFlight = running || trigger.isPending;
  const stoppable = canRun && running && !run?.cancel_requested;
  const runnable =
    canRun && Boolean(roleModel) && !featureDisabled && !inFlight && !campaignRunning;

  const gateHint = !isAuthed
    ? "Sign in to run research."
    : !canRun
      ? "You must be a project member to run research."
      : !roleModel
        ? `Assign a model to ${roleLabel} in Research crew to run this role.`
        : campaignRunning
          ? "A continuous research campaign is running. Stop it before a one-shot run."
          : "";

  return (
    <Bay density="narrative" className="grid gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <ReadoutLabel as="h2">Run research</ReadoutLabel>
        {run ? (
          <span className="inline-flex items-center gap-1.5">
            <StatusPill tone={STATUS_TONE[run.status] ?? "mute"} label={run.status} />
            {run.status === "running" ? <LiveDot /> : null}
          </span>
        ) : null}
      </div>
      <p className="text-[13px] leading-[1.5] text-text-mute">
        Commission bounded agent passes across open threads, against the project budget.
        Open threads can run a few at a time. The loop never validates its own work.
      </p>

      {listQuery.isLoading ? (
        <AwaitingState variant="loading" label="Loading research loop" />
      ) : featureDisabled ? (
        <p className="text-[12px] leading-[1.5] text-text-mute">
          The research loop is not enabled for this deployment yet.
        </p>
      ) : listQuery.isError ? (
        <AwaitingState variant="error" label="Research loop unavailable" />
      ) : (
        <div className="grid gap-3">
          <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
            <label className="grid gap-1.5">
              <span className="text-[13px] font-medium text-text-soft">Role</span>
              <Select
                value={role}
                onChange={(event) => setRole(event.target.value as AgentRole)}
                aria-label="Research-crew role for each pass"
              >
                {ROLES.map((r) => {
                  const model = agentModels?.[r.key] ?? null;
                  return (
                    <option key={r.key} value={r.key}>
                      {r.label} · {model ?? "unassigned"}
                    </option>
                  );
                })}
              </Select>
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <Action
                type="button"
                onClick={() => runnable && trigger.mutate()}
                disabled={!runnable}
                pending={trigger.isPending}
              >
                <Icon icon={Play} size={15} />
                {trigger.isPending ? "Starting…" : "Run research"}
              </Action>
              {running ? (
                <ActionGhost
                  type="button"
                  onClick={() => stoppable && cancel.mutate()}
                  disabled={!stoppable}
                  pending={cancel.isPending}
                >
                  <Icon icon={Square} size={13} />
                  {run?.cancel_requested || cancel.isPending ? "Stopping…" : "Stop"}
                </ActionGhost>
              ) : null}
            </div>
          </div>
          {gateHint && hydrated ? <p className="text-[12px] text-state-warn">{gateHint}</p> : null}
          {trigger.isError ? (
            <p role="alert" className="text-[12px] text-state-fail">
              {(trigger.error as Error).message}
            </p>
          ) : null}
          {cancel.isError ? (
            <p role="alert" className="text-[12px] text-state-fail">
              {(cancel.error as Error).message}
            </p>
          ) : null}

          {run ? (
            <div className="grid gap-2" aria-live="polite">
              <p className="text-[13px] leading-[1.5] text-text-soft">{stopLine(run)}</p>
              <p className="font-mono text-[11px] tabular-nums text-text-faint">
                {run.passes_completed}/{run.passes_commissioned} passes
                {run.passes_skipped ? ` · ${run.passes_skipped} skipped` : ""}
                {run.concurrency > 1 ? ` · ${run.concurrency} at a time` : ""}
                {run.budget_available_end != null
                  ? ` · ${run.budget_available_end} remaining`
                  : ""}
              </p>
              {run.decisions?.length ? (
                <ul className="grid gap-1">
                  {run.decisions.map((decision) => (
                    <li
                      key={`${decision.thread_id}-${decision.action}-${decision.reason ?? ""}`}
                      className="flex flex-wrap items-baseline gap-x-2 text-[12px]"
                    >
                      <span className="text-text-soft">
                        {decision.thread_title || decision.thread_id.slice(0, 8)}
                      </span>
                      <span className="font-mono text-[11px] text-text-faint">
                        {decisionAside(decision)}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : (
            <p className="text-[12px] text-text-faint">No project runs yet.</p>
          )}
        </div>
      )}
    </Bay>
  );
}
