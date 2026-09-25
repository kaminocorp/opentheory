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
  cancelCampaign,
  getCampaign,
  isAgentLoopDisabled,
  listCampaigns,
  listOrchestrations,
  triggerCampaign,
} from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useActingIdentity } from "@/lib/use-identity";
import type { ResearchCampaignRead, ResearchCampaignStatus } from "@/types/campaign";
import type { AgentModels, AgentRole } from "@/types/project";

const ROLES: { key: AgentRole; label: string }[] = [
  { key: "research_lead", label: "Research Lead" },
  { key: "thread_manager", label: "Thread Manager" },
  { key: "researcher", label: "Researcher" },
  { key: "research_assistant", label: "Research Assistant" },
];

const STATUS_TONE: Record<ResearchCampaignStatus, StateTone> = {
  running: "run",
  completed: "ok",
  failed: "fail",
};

const STOP_COPY: Record<string, string> = {
  budget_exhausted: "Stopped — project budget exhausted.",
  no_open_work: "Stopped — no open raisable work.",
  max_cycles: "Stopped — cycle cap reached.",
  cancelled: "Stopped — cancelled.",
  error_budget: "Stopped — too many consecutive cycle failures.",
  error: "Stopped — the campaign failed.",
};

function stopLine(campaign: ResearchCampaignRead): string {
  if (campaign.status === "running") {
    if (campaign.cancel_requested) return "Stopping after the current cycle…";
    return `Cycle ${campaign.current_cycle || 1} — researching until the pot is empty.`;
  }
  if (campaign.stop_reason && STOP_COPY[campaign.stop_reason]) {
    return STOP_COPY[campaign.stop_reason];
  }
  if (campaign.error) return campaign.error;
  return "Finished.";
}

/**
 * Quiet Start / Stop continuous research (0.25.0). Lives on Overview next to
 * the one-shot Run research bay. Repeatedly commissions the 0.22.0 orchestrator
 * against the shared ComputeDebit ceiling until the pot is empty, no raisable
 * work remains, the cycle cap is hit, or a member stops it. Same 404
 * feature-detect as a single agent pass.
 */
export function ContinuousResearchBay({
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
    queryKey: queryKeys.campaigns(projectId),
    queryFn: () => listCampaigns(projectId),
    retry: false,
  });
  const featureDisabled = isAgentLoopDisabled(listQuery.error);
  const latest = listQuery.data?.[0] ?? null;
  const campaignId = activeId ?? latest?.id ?? null;

  const orchListQuery = useQuery({
    queryKey: queryKeys.orchestrations(projectId),
    queryFn: () => listOrchestrations(projectId),
    enabled: !featureDisabled,
    retry: false,
  });
  const standaloneOrchRunning = orchListQuery.data?.[0]?.status === "running";

  const campaignQuery = useQuery({
    queryKey: queryKeys.campaign(campaignId ?? ""),
    queryFn: () => getCampaign(campaignId as string),
    enabled: Boolean(campaignId) && !featureDisabled,
    refetchInterval: (query) => (query.state.data?.status === "running" ? 1200 : false),
  });
  const campaign = campaignQuery.data;
  const prevStatus = useRef<ResearchCampaignStatus | undefined>(undefined);
  useEffect(() => {
    const status = campaign?.status;
    if (prevStatus.current === "running" && status && status !== "running") {
      queryClient.invalidateQueries({ queryKey: queryKeys.overview(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.budget(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.funding(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.threads(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.checkpoints(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.branches(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.orchestrations(projectId) });
    }
    prevStatus.current = status;
  }, [campaign?.status, projectId, queryClient]);

  const roleModel = agentModels?.[role] ?? null;
  const roleLabel = ROLES.find((r) => r.key === role)?.label ?? role;
  const inFlight = campaign?.status === "running" || false;

  const trigger = useMutation({
    mutationFn: () => triggerCampaign(projectId, { role }),
    onSuccess: (started) => {
      setActiveId(started.id);
      queryClient.setQueryData(queryKeys.campaign(started.id), started);
      queryClient.invalidateQueries({ queryKey: queryKeys.campaigns(projectId) });
    },
  });

  const cancel = useMutation({
    mutationFn: () => cancelCampaign(campaign?.id as string),
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKeys.campaign(updated.id), updated);
      queryClient.invalidateQueries({ queryKey: queryKeys.campaigns(projectId) });
    },
  });

  const startable =
    canRun && Boolean(roleModel) && !featureDisabled && !inFlight && !standaloneOrchRunning;
  const stoppable = canRun && inFlight && !campaign?.cancel_requested;

  const gateHint = !isAuthed
    ? "Sign in to run continuous research."
    : !canRun
      ? "You must be a project member to run continuous research."
      : !roleModel
        ? `Assign a model to ${roleLabel} in Research crew to run this role.`
        : standaloneOrchRunning
          ? "A one-shot research run is in flight. Wait or let it finish."
          : "";

  return (
    <Bay density="narrative" className="grid gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <ReadoutLabel as="h2">Continuous research</ReadoutLabel>
        {campaign ? (
          <span className="inline-flex items-center gap-1.5">
            <StatusPill tone={STATUS_TONE[campaign.status] ?? "mute"} label={campaign.status} />
            {campaign.status === "running" ? <LiveDot /> : null}
          </span>
        ) : null}
      </div>
      <p className="text-[13px] leading-[1.5] text-text-mute">
        Keep commissioning research cycles until the project budget is empty or
        nothing raisable remains. The loop never validates or merges its own work.
      </p>

      {listQuery.isLoading ? (
        <AwaitingState variant="loading" label="Loading continuous research" />
      ) : featureDisabled ? (
        <p className="text-[12px] leading-[1.5] text-text-mute">
          The research loop is not enabled for this deployment yet.
        </p>
      ) : listQuery.isError ? (
        <AwaitingState variant="error" label="Continuous research unavailable" />
      ) : (
        <div className="grid gap-3">
          <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
            <label className="grid gap-1.5">
              <span className="text-[13px] font-medium text-text-soft">Role</span>
              <Select
                value={role}
                onChange={(event) => setRole(event.target.value as AgentRole)}
                aria-label="Research-crew role for each campaign cycle"
                disabled={inFlight}
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
            {inFlight ? (
              <ActionGhost
                type="button"
                onClick={() => stoppable && cancel.mutate()}
                disabled={!stoppable}
                pending={cancel.isPending}
              >
                <Icon icon={Square} size={15} />
                {campaign?.cancel_requested || cancel.isPending ? "Stopping…" : "Stop"}
              </ActionGhost>
            ) : (
              <Action
                type="button"
                onClick={() => startable && trigger.mutate()}
                disabled={!startable}
                pending={trigger.isPending}
              >
                <Icon icon={Play} size={15} />
                {trigger.isPending ? "Starting…" : "Start"}
              </Action>
            )}
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

          {campaign ? (
            <div className="grid gap-2" aria-live="polite">
              <p className="text-[13px] leading-[1.5] text-text-soft">{stopLine(campaign)}</p>
              <p className="font-mono text-[11px] tabular-nums text-text-faint">
                cycle {campaign.current_cycle}/{campaign.max_cycles}
                {campaign.budget_available_end != null
                  ? ` · ${campaign.budget_available_end} remaining`
                  : ""}
                {campaign.stop_reason ? ` · ${campaign.stop_reason}` : ""}
              </p>
              {campaign.cycles?.length ? (
                <ul className="grid gap-1">
                  {campaign.cycles.map((cycle) => (
                    <li
                      key={`${cycle.cycle}-${cycle.orchestration_id ?? "none"}`}
                      className="flex flex-wrap items-baseline gap-x-2 text-[12px]"
                    >
                      <span className="text-text-soft">Cycle {cycle.cycle}</span>
                      <span className="font-mono text-[11px] text-text-faint">
                        {cycle.passes_completed ?? 0}/{cycle.passes_commissioned ?? 0} passes
                        {cycle.stop_reason ? ` · ${cycle.stop_reason}` : ""}
                        {cycle.budget_remaining ? ` · ${cycle.budget_remaining} left` : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : (
            <p className="text-[12px] text-text-faint">No continuous runs yet.</p>
          )}
        </div>
      )}
    </Bay>
  );
}
