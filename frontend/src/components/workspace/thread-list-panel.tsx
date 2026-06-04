"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GitBranch, Plus, X } from "lucide-react";
import { useState } from "react";

import { createThread, listThreads } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useDevActor } from "@/providers/dev-actor-provider";

import { PanelEmpty, PanelError, PanelLoading } from "./panel-state";

type ThreadListPanelProps = {
  projectId: string;
  selectedThreadId: string | null;
  onSelectThread: (threadId: string) => void;
};

export function ThreadListPanel({
  projectId,
  selectedThreadId,
  onSelectThread,
}: ThreadListPanelProps) {
  const { actorId, hydrated } = useDevActor();
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState("");
  const [question, setQuestion] = useState("");

  const threadsQuery = useQuery({
    queryKey: queryKeys.threads(projectId),
    queryFn: () => listThreads(projectId),
  });

  const createMutation = useMutation({
    // actorId is captured by value at submit time (passed to mutate), not by reference,
    // so switching actors mid-flight can't send a stale/null header.
    mutationFn: (actor: string) =>
      createThread(projectId, { title: title.trim(), question: question.trim() }, actor),
    onSuccess: (thread) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.threads(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.overview(projectId) });
      onSelectThread(thread.id);
      setTitle("");
      setQuestion("");
      setAdding(false);
    },
  });

  const canSubmit = Boolean(actorId) && title.trim().length > 0 && question.trim().length > 0;

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-line bg-white/70 p-4 shadow-panel">
      <header className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.1em] text-ink/70">
          <GitBranch className="size-4 text-signal" aria-hidden="true" />
          Threads
        </h2>
        <button
          type="button"
          onClick={() => setAdding((v) => !v)}
          className="grid size-7 place-items-center rounded-md border border-line text-ink/65 hover:text-ink"
          aria-label={adding ? "Cancel new thread" : "New thread"}
          title={adding ? "Cancel" : "New thread"}
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
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Thread title"
            className="h-9 rounded-md border border-line bg-white/80 px-2 text-sm outline-none focus:border-signal"
          />
          <input
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Sub-question"
            className="h-9 rounded-md border border-line bg-white/80 px-2 text-sm outline-none focus:border-signal"
          />
          {!actorId && hydrated ? (
            <p className="text-xs text-ember">Select an actor (top right) to create threads.</p>
          ) : null}
          {createMutation.isError ? (
            <p className="text-xs text-ember">{(createMutation.error as Error).message}</p>
          ) : null}
          <button
            type="submit"
            disabled={!canSubmit || createMutation.isPending}
            className="inline-flex h-9 items-center justify-center gap-1 rounded-md bg-ink px-3 text-sm font-semibold text-paper disabled:opacity-50"
          >
            {createMutation.isPending ? "Creating…" : "Create thread"}
          </button>
        </form>
      ) : null}

      {threadsQuery.isLoading ? (
        <PanelLoading label="Loading threads" />
      ) : threadsQuery.isError ? (
        <PanelError label="Could not load threads." />
      ) : (threadsQuery.data ?? []).length === 0 ? (
        <PanelEmpty icon={<GitBranch className="size-5" aria-hidden="true" />}>
          No threads yet. Decompose the question into a first thread.
        </PanelEmpty>
      ) : (
        <ul className="grid gap-2">
          {(threadsQuery.data ?? []).map((thread) => {
            const active = thread.id === selectedThreadId;
            return (
              <li key={thread.id}>
                <button
                  type="button"
                  onClick={() => onSelectThread(thread.id)}
                  className={`w-full rounded-md border p-3 text-left transition ${
                    active
                      ? "border-signal/60 bg-signal/5"
                      : "border-line bg-white/60 hover:border-ink/25"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="truncate text-sm font-semibold">{thread.title}</p>
                    <span
                      className="shrink-0 rounded bg-paper px-1.5 py-0.5 text-[11px] font-semibold text-ink/55"
                      title={`${thread.claim_count} claim${thread.claim_count === 1 ? "" : "s"}`}
                    >
                      {thread.claim_count} claim{thread.claim_count === 1 ? "" : "s"}
                    </span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-xs leading-5 text-ink/60">{thread.question}</p>
                  <p className="mt-2 text-[11px] font-medium uppercase tracking-[0.1em] text-ink/45">
                    {thread.stage} · {thread.status.replace("_", " ")}
                  </p>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
