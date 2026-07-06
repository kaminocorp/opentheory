"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, ChevronDown, ChevronRight, Play } from "lucide-react";
import { useEffect, useState } from "react";

import { Action, AwaitingState, Bay, Icon, ReadoutLabel, Select } from "@/components/console";
import { isAgentLoopDisabled, listAgentRuns, triggerAgentPass } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useActingIdentity } from "@/lib/use-identity";
import type { AgentModels, AgentRole } from "@/types/project";

import { AgentRunStatusPill, AgentRunTrace } from "./agent-run-trace";

// The four Research-crew roles a pass can be commissioned as (order = display order). Mirrors the
// backend AGENT_ROLE_FIELDS; `researcher` is the sensible default (the role that runs instruments).
const ROLES: { key: AgentRole; label: string }[] = [
  { key: "research_lead", label: "Research Lead" },
  { key: "thread_manager", label: "Thread Manager" },
  { key: "researcher", label: "Researcher" },
  { key: "research_assistant", label: "Research Assistant" },
];

/**
 * The agent-pass surface (0.12.4): commission one bounded pass on the selected thread and watch its
 * trace. The trigger is member-gated (the backend still authorizes) and disabled when the chosen
 * role has no model assigned in Research crew, or when the loop is dark for this deployment
 * (feature-detected via a 404 on the list). The pass runs on the backend; the trace polls until it
 * settles, landing real checkpoints on a durable agent branch — the same ledger a human's instrument
 * run lands on, one layer down.
 */
export function AgentPassPanel({
  projectId,
  selectedThreadId,
  canRun,
  agentModels,
  onSelectBranch,
}: {
  projectId: string;
  selectedThreadId: string | null;
  canRun: boolean;
  agentModels: AgentModels;
  onSelectBranch: (branchId: string | null) => void;
}) {
  const [open, setOpen] = useState(true);
  const [role, setRole] = useState<AgentRole>("researcher");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const { isAuthed, hydrated } = useActingIdentity();
  const queryClient = useQueryClient();

  // A stale active-run selection must not survive a thread change (its trace belongs to the old
  // thread). Reset it; the active run then falls back to the newest pass on the new thread.
  useEffect(() => {
    setActiveRunId(null);
  }, [selectedThreadId]);

  // Feature-detect + list this thread's passes, newest first. A 404 means the loop is dark for this
  // deployment (`agent_loop_enabled` off) — don't retry, and disable the trigger below.
  const runsQuery = useQuery({
    queryKey: queryKeys.agentRuns(selectedThreadId ?? ""),
    queryFn: () => listAgentRuns(projectId, selectedThreadId as string),
    enabled: Boolean(selectedThreadId),
    retry: false,
  });
  const featureDisabled = isAgentLoopDisabled(runsQuery.error);
  const runs = runsQuery.data ?? [];

  const roleModel = agentModels?.[role] ?? null;
  const roleLabel = ROLES.find((r) => r.key === role)?.label ?? role;

  const trigger = useMutation({
    mutationFn: () => triggerAgentPass(projectId, selectedThreadId as string, { role }),
    onSuccess: (run) => {
      setActiveRunId(run.id);
      // Seed the poll cache so the trace renders instantly, then refresh the list.
      queryClient.setQueryData(queryKeys.agentRun(run.id), run);
      queryClient.invalidateQueries({ queryKey: queryKeys.agentRuns(selectedThreadId ?? "") });
    },
  });

  const runnable =
    canRun &&
    Boolean(selectedThreadId) &&
    Boolean(roleModel) &&
    !featureDisabled &&
    !trigger.isPending;

  const gateHint = !isAuthed
    ? "Sign in to run an agent pass."
    : !canRun
      ? "You must be a project member to run an agent pass."
      : !roleModel
        ? `Assign a model to ${roleLabel} in Research crew above to run this role.`
        : "";

  // The shown run: the just-triggered one (via activeRunId), else the newest pass.
  const activeId = activeRunId ?? runs[0]?.id ?? null;
  const activeSummary = runs.find((r) => r.id === activeId);
  const history = runs.filter((r) => r.id !== activeId);

  return (
    <Bay density="narrative" className="grid gap-4">
      <header className="flex items-center justify-between">
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
          className="flex items-center gap-2 text-text-mute transition-colors hover:text-text"
        >
          <Icon icon={open ? ChevronDown : ChevronRight} size={14} />
          <Icon icon={Bot} size={15} />
          <ReadoutLabel>Agent pass · Research crew</ReadoutLabel>
        </button>
        {runs.length > 0 ? (
          <span className="font-mono text-[11px] tabular-nums text-text-mute">{runs.length}</span>
        ) : null}
      </header>

      {open ? (
        !selectedThreadId ? (
          <AwaitingState variant="empty" label="select a thread to commission an agent pass" />
        ) : runsQuery.isLoading ? (
          <AwaitingState variant="loading" label="loading agent passes" />
        ) : featureDisabled ? (
          <p className="text-[12px] leading-[1.5] text-text-mute">
            Agent passes are not enabled for this deployment yet.
          </p>
        ) : runsQuery.isError ? (
          <AwaitingState variant="error" label="agent passes unavailable" />
        ) : (
          <div className="grid gap-4">
            {/* Trigger: pick a role (its model shown inline), then commission the pass. */}
            <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
              <label className="grid gap-1.5">
                <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-text-mute">
                  Role
                </span>
                <Select
                  value={role}
                  onChange={(event) => setRole(event.target.value as AgentRole)}
                  aria-label="Research-crew role to commission"
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
              <Action
                type="button"
                onClick={() => runnable && trigger.mutate()}
                disabled={!runnable}
                pending={trigger.isPending}
              >
                <Icon icon={Play} size={15} />
                {trigger.isPending ? "Commissioning…" : "Run agent pass"}
              </Action>
            </div>
            {gateHint && hydrated ? <p className="text-[12px] text-state-warn">{gateHint}</p> : null}
            {trigger.isError ? (
              <p role="alert" className="text-[12px] text-state-fail">
                {(trigger.error as Error).message}
              </p>
            ) : null}

            {/* The active pass's trace (polls while running). */}
            {activeId ? (
              <AgentRunTrace
                key={activeId}
                runId={activeId}
                projectId={projectId}
                initial={activeSummary}
                onSelectBranch={onSelectBranch}
              />
            ) : (
              <div
                className="grid min-h-24 place-items-center rounded-built bg-panel-2"
                style={{ border: "0.5px solid var(--hairline)" }}
              >
                <AwaitingState variant="empty" label="no passes yet — run one to see its trace" />
              </div>
            )}

            {/* Earlier passes on this thread — click to inspect one. */}
            {history.length > 0 ? (
              <div className="grid gap-1.5">
                <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-text-mute">
                  Earlier passes
                </span>
                {history.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => setActiveRunId(r.id)}
                    className="flex flex-wrap items-center gap-2 rounded-built bg-panel-2 px-3 py-2 text-left transition-colors hover:bg-panel"
                    style={{ border: "0.5px solid var(--hairline)" }}
                  >
                    <AgentRunStatusPill status={r.status} />
                    <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-text-mute">
                      {r.role.replaceAll("_", " ")}
                    </span>
                    <span className="font-mono text-[11px] tabular-nums text-text-faint">
                      {r.ran_count}/{r.planned_count} runs
                    </span>
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        )
      ) : null}
    </Bay>
  );
}
