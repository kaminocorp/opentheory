"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, GitCommitHorizontal, Plus, ShieldCheck, X } from "lucide-react";
import { useState } from "react";

import { Action, Bay, BayHeader, Icon, Input, Textarea } from "@/components/console";
import { createCheckpoint, listCheckpoints } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useActingIdentity } from "@/lib/use-identity";

import { PanelEmpty, PanelError, PanelLoading } from "./panel-state";
import { RecordValidationForm } from "./validation-controls";

type CheckpointTimelinePanelProps = {
  projectId: string;
  selectedThreadId: string | null;
  // null = main line; otherwise the branch this timeline is scoped to (0.4.3).
  selectedBranchId: string | null;
  // The selected line is closed/dead-end: it's preserved, not extended, so recording is
  // disabled (the backend would reject a checkpoint on a sealed branch with 400).
  lineSealed?: boolean;
};

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// D5 re-skin: the checkpoint timeline as a §5.3 log/stream of instrument entries.
// These are fetched lists, not a live tail, so the streaming affordances (autoscroll,
// a pulsing tail) are N/A here. Console tokens + primitives only; every hook, the
// create mutation, the line-scoping filter, and the seal gating below are unchanged.
export function CheckpointTimelinePanel({
  projectId,
  selectedThreadId,
  selectedBranchId,
  lineSealed = false,
}: CheckpointTimelinePanelProps) {
  const { canWrite, hydrated, signInHint } = useActingIdentity();
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [summary, setSummary] = useState("");
  const [notes, setNotes] = useState("");
  const [validatingId, setValidatingId] = useState<string | null>(null);

  const checkpointsQuery = useQuery({
    queryKey: queryKeys.checkpoints(projectId),
    queryFn: () => listCheckpoints(projectId),
  });

  // Scope the timeline to the selected line: a checkpoint is on the main line when its
  // branch_id is null, otherwise on its branch (0.4.3).
  const checkpoints = (checkpointsQuery.data ?? []).filter(
    (checkpoint) => (checkpoint.branch_id ?? null) === selectedBranchId,
  );

  const createMutation = useMutation({
    mutationFn: () =>
      createCheckpoint(projectId, {
        thread_id: selectedThreadId,
        branch_id: selectedBranchId,
        summary: summary.trim(),
        notes: notes.trim() || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.checkpoints(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.overview(projectId) });
      setSummary("");
      setNotes("");
      setAdding(false);
    },
  });

  const canSubmit = canWrite && summary.trim().length > 0;

  return (
    <Bay density="none" className="flex flex-col">
      <BayHeader
        label={
          <span className="inline-flex items-center gap-1.5">
            <Icon icon={GitCommitHorizontal} size={14} />
            Checkpoints
          </span>
        }
        count={checkpointsQuery.data ? checkpoints.length : undefined}
        band
        // Write affordance: shown only to a signed-in actor, and never on a sealed line.
        actions={
          !lineSealed && canWrite ? (
            <button
              type="button"
              onClick={() => setAdding((v) => !v)}
              className="grid size-7 place-items-center rounded-full text-text-mute transition-colors hover:text-text"
              style={{ border: "0.5px solid var(--hairline-strong)" }}
              aria-label={adding ? "Cancel new checkpoint" : "New checkpoint"}
              title={adding ? "Cancel" : "New checkpoint"}
            >
              <Icon icon={adding ? X : Plus} size={14} />
            </button>
          ) : undefined
        }
      />

      <div className="flex flex-col gap-3 px-4 pb-4">
        {lineSealed ? (
          // Honest note (§1): a warn-marked, dashed-hairline notice — not hidden, not dimmed.
          <div
            className="flex items-start gap-2 rounded-built bg-panel-2 p-2.5 text-[12px] leading-5 text-text-soft"
            style={{ border: "0.5px dashed var(--hairline)" }}
          >
            <Icon icon={AlertTriangle} size={14} className="mt-0.5 shrink-0 text-state-warn" />
            <span>
              This line is closed — its checkpoints are preserved, not extended. Switch to the main
              line or an open branch to record a new checkpoint.
            </span>
          </div>
        ) : null}

        {adding && !lineSealed ? (
          <form
            className="grid gap-2 rounded-built bg-panel-2 p-3"
            style={{ border: "0.5px solid var(--hairline)" }}
            onSubmit={(event) => {
              event.preventDefault();
              if (canSubmit && !createMutation.isPending) createMutation.mutate();
            }}
          >
            <p className="text-[12px] text-text-mute">
              {selectedBranchId ? "Recorded on the selected branch." : "Recorded on the main line."}
              {selectedThreadId ? " Scoped to the selected thread." : ""}
            </p>
            <Input
              value={summary}
              onChange={(event) => setSummary(event.target.value)}
              placeholder="Checkpoint summary"
            />
            <Textarea
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="Notes (optional)"
              rows={2}
            />
            {!canWrite && hydrated ? (
              <p className="text-[11px] text-state-warn">{signInHint} to record checkpoints.</p>
            ) : null}
            {createMutation.isError ? (
              <p className="text-[11px] text-state-fail">{(createMutation.error as Error).message}</p>
            ) : null}
            <Action
              type="submit"
              disabled={!canSubmit || createMutation.isPending}
              pending={createMutation.isPending}
              className="w-full"
            >
              <Icon icon={Plus} size={16} />
              {createMutation.isPending ? "Recording…" : "Record checkpoint"}
            </Action>
          </form>
        ) : null}

        {checkpointsQuery.isLoading ? (
          <PanelLoading label="Loading checkpoints" />
        ) : checkpointsQuery.isError ? (
          <PanelError label="Could not load checkpoints" />
        ) : checkpoints.length === 0 ? (
          <PanelEmpty>{selectedBranchId ? "No checkpoints on this branch" : "No checkpoints on the main line"}</PanelEmpty>
        ) : (
          <ol className="grid gap-2">
            {checkpoints.map((checkpoint) => (
              // Square log entry on --panel-2; a neutral left rule marks the stream
              // (signal is seldom — none of these is "the live one").
              <li
                key={checkpoint.id}
                className="relative rounded-built bg-panel-2 p-3 pl-4"
                style={{ border: "0.5px solid var(--hairline)" }}
              >
                <span
                  aria-hidden
                  className="absolute inset-y-3 left-0 w-0.5"
                  style={{ backgroundColor: "var(--hairline-strong)" }}
                />
                <p className="text-[14px] font-medium leading-6 text-text">{checkpoint.summary}</p>
                {checkpoint.notes ? (
                  <p className="mt-1 line-clamp-2 text-[13px] leading-5 text-text-soft">
                    {checkpoint.notes}
                  </p>
                ) : null}

                {checkpoint.refs.length > 0 ? (
                  <ul className="mt-2 grid gap-1">
                    {checkpoint.refs.map((ref) => (
                      <li key={ref.id} className="flex items-baseline gap-1.5 text-[12px] leading-5">
                        <span className="shrink-0 font-mono uppercase tracking-[0.08em] text-text-mute">
                          {ref.role}
                        </span>
                        {ref.label ? (
                          <span className="min-w-0 truncate text-text-soft">{ref.label}</span>
                        ) : (
                          <span className="min-w-0 truncate font-mono text-text-mute">
                            {ref.target_type} {ref.target_id.slice(0, 8)}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : null}

                {checkpoint.contribution_kind ? (
                  <p className="mt-2 flex items-center gap-1.5 text-[11px] text-text-mute">
                    <span
                      className="rounded-inset bg-panel px-1.5 py-0.5 font-mono uppercase tracking-[0.08em] text-text-mute"
                      style={{ border: "0.5px solid var(--hairline)" }}
                    >
                      {checkpoint.contribution_kind.replace(/_/g, " ")}
                    </span>
                    {checkpoint.author ? <span>by {checkpoint.author.display_name}</span> : null}
                  </p>
                ) : null}

                <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-text-faint">
                  <span className="font-mono tabular-nums">{formatTimestamp(checkpoint.created_at)}</span>
                  {!checkpoint.contribution_kind && checkpoint.author ? (
                    <span>· by {checkpoint.author.display_name}</span>
                  ) : null}
                  {checkpoint.stage ? (
                    <span
                      className="rounded-inset bg-panel px-1.5 py-0.5 font-mono uppercase tracking-[0.08em]"
                      style={{ border: "0.5px solid var(--hairline)" }}
                    >
                      {checkpoint.stage}
                    </span>
                  ) : null}
                  {checkpoint.thread_id ? <span className="font-mono">· thread-scoped</span> : null}
                  {checkpoint.parent_ids.length > 0 ? (
                    <span className="font-mono tabular-nums">
                      · {checkpoint.parent_ids.length} parent{checkpoint.parent_ids.length === 1 ? "" : "s"}
                    </span>
                  ) : null}
                </div>

                <div className="mt-2">
                  {canWrite ? (
                    <button
                      type="button"
                      onClick={() =>
                        setValidatingId((current) => (current === checkpoint.id ? null : checkpoint.id))
                      }
                      className="inline-flex items-center gap-1.5 text-[12px] font-medium text-text-mute transition-colors hover:text-signal"
                    >
                      <Icon icon={ShieldCheck} size={14} />
                      {validatingId === checkpoint.id ? "Cancel" : "Validate"}
                    </button>
                  ) : null}
                  {validatingId === checkpoint.id ? (
                    <RecordValidationForm
                      projectId={projectId}
                      targetType="checkpoint"
                      targetId={checkpoint.id}
                      onDone={() => setValidatingId(null)}
                      compact
                    />
                  ) : null}
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </Bay>
  );
}
