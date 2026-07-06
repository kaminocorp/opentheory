"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import {
  ActionText,
  LiveDot,
  MetricReadout,
  StatusPill,
  type StateTone,
} from "@/components/console";
import { getAgentRun } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import type { AgentRunRead, AgentRunStatus, AgentRunStep, AgentRunSummary } from "@/types/agent-run";

import { outcomeMeta } from "../toolbench/outcome";

const short = (id: string | null | undefined, n = 8): string => (id ? id.slice(0, n) : "—");

// Pass lifecycle → a console state tone (glyph + colour survive grayscale, §1). Running is the only
// live state — it also carries a pulsing LiveDot to signal the poll.
const STATUS_TONE: Record<AgentRunStatus, StateTone> = {
  running: "run",
  completed: "ok",
  failed: "fail",
};

/** The pass-status atom, reused by the trace header and the history rows (one tone map). */
export function AgentRunStatusPill({ status, live = false }: { status: AgentRunStatus; live?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <StatusPill tone={STATUS_TONE[status] ?? "mute"} label={status.toUpperCase()} />
      {live && status === "running" ? <LiveDot /> : null}
    </span>
  );
}

// A small mono chip (ids, machine tokens) — matches the toolbench provenance readouts.
function Chip({ children, title }: { children: React.ReactNode; title?: string }) {
  return (
    <span
      className="rounded-full px-2 py-[2px] font-mono text-[11px] text-text-faint"
      style={{ border: "0.5px solid var(--hairline)" }}
      title={title}
    >
      {children}
    </span>
  );
}

/**
 * One landed step — the honest outcome vocabulary reused from the toolbench (`refuted` = fail,
 * `undecided` = warn, never a pass), plus a link-by-id to the checkpoint (its full result card
 * renders in the timeline below — the step itself does not carry the blame tuple to re-render it).
 */
function LandedStep({ step }: { step: AgentRunStep }) {
  const meta = outcomeMeta(step.outcome ?? undefined);
  return (
    <div className="grid gap-1.5 rounded-built bg-panel-2 p-3" style={{ border: "0.5px solid var(--hairline)" }}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[12px] text-text">{step.instrument}</span>
        <StatusPill tone={meta.tone} label={meta.label.toUpperCase()} />
      </div>
      {step.rationale ? (
        <p className="text-[12px] leading-[1.5] text-text-soft">{step.rationale}</p>
      ) : null}
      <div className="flex flex-wrap gap-1.5 pt-0.5">
        {step.checkpoint_id ? (
          <Chip title={step.checkpoint_id}>checkpoint {short(step.checkpoint_id)}</Chip>
        ) : null}
        {step.evidence_id ? <Chip title={step.evidence_id}>evidence {short(step.evidence_id)}</Chip> : null}
        {step.claim_id ? (
          <Chip title={step.claim_id}>
            claim {short(step.claim_id)}
            {step.relation_kind ? ` · ${step.relation_kind}` : ""}
          </Chip>
        ) : null}
      </div>
    </div>
  );
}

/**
 * A failed step — reached `run_instrument` and errored, so it minted nothing (the failure split).
 * Marked with a state-fail edge tick; the error is shown verbatim, never softened.
 */
function FailedStep({ step }: { step: AgentRunStep }) {
  return (
    <div
      className="relative grid gap-1 rounded-built bg-panel-2 p-3 pl-4"
      style={{ border: "0.5px solid var(--hairline)" }}
    >
      <span aria-hidden className="absolute inset-y-0 left-0 w-0.5 bg-state-fail" />
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[12px] text-text">{step.instrument}</span>
        <StatusPill tone="fail" label="FAILED" />
      </div>
      {step.error ? <p className="text-[12px] leading-[1.5] text-text-mute">{step.error}</p> : null}
    </div>
  );
}

// A dropped (planner-rejected, never ran) or budget-skipped step — a faint, hatched note. It is not
// an error and not a mint; the reason (e.g. `max_runs`, `unknown_instrument`) is shown as-is.
function InertStep({ step, label }: { step: AgentRunStep; label: string }) {
  return (
    <div
      className="hatch flex flex-wrap items-center gap-2 rounded-built bg-panel p-2.5"
      style={{ border: "0.5px dashed var(--hairline)" }}
    >
      <span className="font-mono text-[12px] text-text-mute">{step.instrument}</span>
      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-text-faint">
        {label}
        {step.reason ? ` · ${step.reason}` : ""}
      </span>
    </div>
  );
}

function StepRow({ step }: { step: AgentRunStep }) {
  switch (step.status) {
    case "landed":
      return <LandedStep step={step} />;
    case "failed":
      return <FailedStep step={step} />;
    case "skipped":
      return <InertStep step={step} label="skipped" />;
    default:
      // `dropped_invalid` and any future/lenient status degrade to the inert note.
      return <InertStep step={step} label="dropped" />;
  }
}

/**
 * One agent pass's trace. Polls `GET /agent-runs/{id}` while `running` (stopping on
 * `completed`/`failed`), renders the plan's per-step outcomes with the honest toolbench vocabulary,
 * and — once a pass settles on a branch — offers a route to that line where the shipped branch-bar
 * (reject = close as dead-end, branch further = fork) and claim validation (accept) already live.
 * On the `running → terminal` transition it refreshes the ledger surfaces the pass touched.
 */
export function AgentRunTrace({
  runId,
  projectId,
  initial,
  onSelectBranch,
}: {
  runId: string;
  projectId: string;
  // The list-row summary, shown immediately while the full trace loads.
  initial?: AgentRunSummary;
  onSelectBranch: (branchId: string | null) => void;
}) {
  const queryClient = useQueryClient();

  const query = useQuery<AgentRunRead>({
    queryKey: queryKeys.agentRun(runId),
    queryFn: () => getAgentRun(runId),
    placeholderData: initial ? { ...initial, plan: {}, steps: [] } : undefined,
    // Poll while the pass is running; stop the moment it settles.
    refetchInterval: (q) => (q.state.data?.status === "running" ? 2000 : false),
  });
  const run = query.data;

  // On the running → terminal transition, refresh what the pass changed: the timeline (landed
  // checkpoints), the overview counts, and the branch bar (a freshly forked agent line).
  const prevStatus = useRef<AgentRunStatus | undefined>(undefined);
  useEffect(() => {
    const status = run?.status;
    if (status && prevStatus.current === "running" && status !== "running") {
      queryClient.invalidateQueries({ queryKey: queryKeys.checkpoints(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.overview(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.branches(projectId) });
    }
    prevStatus.current = status;
  }, [run?.status, projectId, queryClient]);

  if (!run) {
    return <p className="text-[12px] text-text-mute">Loading trace…</p>;
  }

  const steps = run.steps ?? [];
  const landedOnBranch = run.status === "completed" && run.branch_id !== null;

  return (
    <div className="grid gap-3 rounded-built bg-panel p-4" style={{ border: "0.5px solid var(--hairline)" }}>
      {/* Status line: the pass verdict + role/model, with a live pulse while running. */}
      <div className="flex flex-wrap items-center gap-2">
        <AgentRunStatusPill status={run.status} live />
        <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-text-mute">
          {run.role.replaceAll("_", " ")}
        </span>
        {run.model ? <span className="font-mono text-[11px] text-text-faint">{run.model}</span> : null}
      </div>

      {/* Effort readouts: what actually ran vs. what was planned, and the planning-call token spend. */}
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <MetricReadout label="Runs" value={`${run.ran_count}/${run.planned_count}`} />
        <MetricReadout label="Tokens" value={run.tokens_used.toLocaleString()} />
        <MetricReadout label="Steps" value={steps.length} />
      </dl>

      {/* Pass-level failure (unassigned role, planner error, unexpected) — honest, never softened. */}
      {run.status === "failed" && run.error ? (
        <div className="relative rounded-built bg-panel-2 p-3 pl-4">
          <span aria-hidden className="absolute inset-y-0 left-0 w-0.5 bg-state-fail" />
          <p className="text-[12px] leading-[1.5] text-state-fail">{run.error}</p>
        </div>
      ) : null}

      {/* The plan, step by step. */}
      {steps.length > 0 ? (
        <ol className="grid gap-2">
          {steps.map((step, i) => (
            <li key={`${step.index}-${step.instrument}-${i}`}>
              <StepRow step={step} />
            </li>
          ))}
        </ol>
      ) : run.status === "running" ? (
        <p className="text-[12px] text-text-mute">Planning…</p>
      ) : run.status === "completed" ? (
        <p className="text-[12px] text-text-mute">
          Nothing to run — the planner proposed no applicable instrument.
        </p>
      ) : null}

      {/* Route to the shipped write paths: landing on a branch, the human reviews it on its line —
          where reject (close as dead-end) and branch further (fork) live; accept validates a claim
          from the claim panel. We don't duplicate those write flows here. */}
      {landedOnBranch ? (
        <div className="grid gap-1 border-t pt-2" style={{ borderColor: "var(--hairline)" }}>
          <ActionText size="sm" onClick={() => onSelectBranch(run.branch_id)} className="w-fit">
            Review on its line
          </ActionText>
          <p className="text-[11px] leading-[1.5] text-text-faint">
            Accept (validate a claim), reject (close the line as a dead end), or branch further from the
            line selector above.
          </p>
        </div>
      ) : run.status === "completed" && run.branch_id === null ? (
        <p className="text-[11px] text-text-faint">Landed on the project main line.</p>
      ) : null}
    </div>
  );
}
