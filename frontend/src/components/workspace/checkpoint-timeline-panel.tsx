"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GitCommitHorizontal, Plus, X } from "lucide-react";
import { useState } from "react";

import { createCheckpoint, listCheckpoints } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useDevActor } from "@/providers/dev-actor-provider";

import { PanelEmpty, PanelError, PanelLoading } from "./panel-state";

type CheckpointTimelinePanelProps = {
  projectId: string;
  selectedThreadId: string | null;
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

export function CheckpointTimelinePanel({
  projectId,
  selectedThreadId,
}: CheckpointTimelinePanelProps) {
  const { actorId, hydrated } = useDevActor();
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [summary, setSummary] = useState("");
  const [notes, setNotes] = useState("");

  const checkpointsQuery = useQuery({
    queryKey: queryKeys.checkpoints(projectId),
    queryFn: () => listCheckpoints(projectId),
  });

  const createMutation = useMutation({
    mutationFn: (actor: string) =>
      createCheckpoint(
        projectId,
        {
          thread_id: selectedThreadId,
          summary: summary.trim(),
          notes: notes.trim() || null,
        },
        actor,
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.checkpoints(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.overview(projectId) });
      setSummary("");
      setNotes("");
      setAdding(false);
    },
  });

  const canSubmit = Boolean(actorId) && summary.trim().length > 0;

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-line bg-white/70 p-4 shadow-panel">
      <header className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.1em] text-ink/70">
          <GitCommitHorizontal className="size-4 text-signal" aria-hidden="true" />
          Checkpoints
        </h2>
        <button
          type="button"
          onClick={() => setAdding((v) => !v)}
          className="grid size-7 place-items-center rounded-md border border-line text-ink/65 hover:text-ink"
          aria-label={adding ? "Cancel new checkpoint" : "New checkpoint"}
          title={adding ? "Cancel" : "New checkpoint"}
        >
          {adding ? <X className="size-4" aria-hidden="true" /> : <Plus className="size-4" aria-hidden="true" />}
        </button>
      </header>

      {adding ? (
        <form
          className="grid gap-2 rounded-md border border-line bg-paper/60 p-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (canSubmit && !createMutation.isPending) createMutation.mutate(actorId!);
          }}
        >
          <p className="text-xs text-ink/55">
            {selectedThreadId ? "Scoped to the selected thread." : "Project-level checkpoint."}
          </p>
          <input
            value={summary}
            onChange={(event) => setSummary(event.target.value)}
            placeholder="Checkpoint summary"
            className="h-9 rounded-md border border-line bg-white/80 px-2 text-sm outline-none focus:border-signal"
          />
          <textarea
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            placeholder="Notes (optional)"
            rows={2}
            className="rounded-md border border-line bg-white/80 px-2 py-1.5 text-sm outline-none focus:border-signal"
          />
          {!actorId && hydrated ? (
            <p className="text-xs text-ember">Select an actor (top right) to record checkpoints.</p>
          ) : null}
          {createMutation.isError ? (
            <p className="text-xs text-ember">{(createMutation.error as Error).message}</p>
          ) : null}
          <button
            type="submit"
            disabled={!canSubmit || createMutation.isPending}
            className="inline-flex h-9 items-center justify-center gap-1 rounded-md bg-ink px-3 text-sm font-semibold text-paper disabled:opacity-50"
          >
            {createMutation.isPending ? "Recording…" : "Record checkpoint"}
          </button>
        </form>
      ) : null}

      {checkpointsQuery.isLoading ? (
        <PanelLoading label="Loading checkpoints" />
      ) : checkpointsQuery.isError ? (
        <PanelError label="Could not load checkpoints." />
      ) : (checkpointsQuery.data ?? []).length === 0 ? (
        <PanelEmpty icon={<GitCommitHorizontal className="size-5" aria-hidden="true" />}>
          No checkpoints yet. Record one after a meaningful move — proposing a hypothesis,
          attaching evidence, or validating a result — to mark it in the ledger.
        </PanelEmpty>
      ) : (
        <ol className="grid gap-2">
          {(checkpointsQuery.data ?? []).map((checkpoint) => (
            <li
              key={checkpoint.id}
              className="relative rounded-md border border-line bg-white/60 p-3 pl-4"
            >
              <span className="absolute inset-y-3 left-0 w-0.5 rounded bg-signal/50" aria-hidden="true" />
              <p className="text-sm font-medium leading-6">{checkpoint.summary}</p>
              {checkpoint.notes ? (
                <p className="mt-1 line-clamp-2 text-xs leading-5 text-ink/55">{checkpoint.notes}</p>
              ) : null}

              {checkpoint.refs.length > 0 ? (
                <ul className="mt-2 grid gap-1">
                  {checkpoint.refs.map((ref) => (
                    <li key={ref.id} className="flex items-baseline gap-1.5 text-xs leading-5">
                      <span className="shrink-0 font-semibold text-signal">{ref.role}</span>
                      <span className="min-w-0 truncate text-ink/70">
                        {ref.label ?? `${ref.target_type} ${ref.target_id.slice(0, 8)}`}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}

              {checkpoint.contribution_kind ? (
                <p className="mt-2 text-[11px] font-medium text-ink/55">
                  <span className="rounded bg-signal/10 px-1.5 py-0.5 font-semibold uppercase tracking-[0.08em] text-signal">
                    {checkpoint.contribution_kind.replace(/_/g, " ")}
                  </span>
                  {checkpoint.author ? <span className="ml-1.5">by {checkpoint.author.display_name}</span> : null}
                </p>
              ) : null}

              <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-ink/45">
                <span>{formatTimestamp(checkpoint.created_at)}</span>
                {!checkpoint.contribution_kind && checkpoint.author ? (
                  <span>· by {checkpoint.author.display_name}</span>
                ) : null}
                {checkpoint.stage ? (
                  <span className="rounded bg-paper px-1.5 py-0.5 font-semibold uppercase tracking-[0.08em]">
                    {checkpoint.stage}
                  </span>
                ) : null}
                {checkpoint.thread_id ? <span>· thread-scoped</span> : null}
                {checkpoint.parent_ids.length > 0 ? (
                  <span>· {checkpoint.parent_ids.length} parent{checkpoint.parent_ids.length === 1 ? "" : "s"}</span>
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
