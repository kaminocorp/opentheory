"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GitBranch, Plus, X } from "lucide-react";
import { useState } from "react";

import { Action, Bay, BayHeader, Icon, Input } from "@/components/console";
import { createThread, listThreads } from "@/lib/api";
import { cn } from "@/lib/cn";
import { queryKeys } from "@/lib/query-keys";
import { useActingIdentity } from "@/lib/use-identity";

import { PanelEmpty, PanelError, PanelLoading } from "./panel-state";

type ThreadListPanelProps = {
  projectId: string;
  selectedThreadId: string | null;
  onSelectThread: (threadId: string) => void;
};

// D5 re-skin: the threads instrument bay (§5.1). Console tokens + primitives only;
// every hook, the create mutation, and the selection callback below are unchanged.
export function ThreadListPanel({
  projectId,
  selectedThreadId,
  onSelectThread,
}: ThreadListPanelProps) {
  const { canWrite, hydrated, signInHint } = useActingIdentity();
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState("");
  const [question, setQuestion] = useState("");

  const threadsQuery = useQuery({
    queryKey: queryKeys.threads(projectId),
    queryFn: () => listThreads(projectId),
  });

  const createMutation = useMutation({
    // The acting actor rides on the request (bearer token / dev header), resolved server-side.
    mutationFn: () =>
      createThread(projectId, { title: title.trim(), question: question.trim() }),
    onSuccess: (thread) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.threads(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.overview(projectId) });
      onSelectThread(thread.id);
      setTitle("");
      setQuestion("");
      setAdding(false);
    },
  });

  const threads = threadsQuery.data ?? [];
  const canSubmit = canWrite && title.trim().length > 0 && question.trim().length > 0;

  return (
    <Bay density="none" className="flex flex-col">
      <BayHeader
        label={
          <span className="inline-flex items-center gap-1.5">
            <Icon icon={GitBranch} size={14} />
            Threads
          </span>
        }
        count={threadsQuery.data ? threads.length : undefined}
        band
        actions={
          <button
            type="button"
            onClick={() => setAdding((v) => !v)}
            className="grid size-7 place-items-center rounded-full text-text-mute transition-colors hover:text-text"
            style={{ border: "0.5px solid var(--hairline-strong)" }}
            aria-label={adding ? "Cancel new thread" : "New thread"}
            title={adding ? "Cancel" : "New thread"}
          >
            <Icon icon={adding ? X : Plus} size={14} />
          </button>
        }
      />

      <div className="flex flex-col gap-3 px-4 pb-4">
        {adding ? (
          <form
            className="grid gap-2 rounded-built bg-panel-2 p-3"
            style={{ border: "0.5px solid var(--hairline)" }}
            onSubmit={(event) => {
              event.preventDefault();
              if (canSubmit && !createMutation.isPending) createMutation.mutate();
            }}
          >
            <Input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Thread title"
            />
            <Input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Sub-question"
            />
            {!canWrite && hydrated ? (
              <p className="text-[11px] text-state-warn">{signInHint} to create threads.</p>
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
              {createMutation.isPending ? "Creating…" : "Create thread"}
            </Action>
          </form>
        ) : null}

        {threadsQuery.isLoading ? (
          <PanelLoading label="Loading threads" />
        ) : threadsQuery.isError ? (
          <PanelError label="Could not load threads" />
        ) : threads.length === 0 ? (
          <PanelEmpty>No threads yet</PanelEmpty>
        ) : (
          <ul className="grid gap-2">
            {threads.map((thread) => {
              const active = thread.id === selectedThreadId;
              return (
                <li key={thread.id}>
                  {/* Square selectable row (built); active = a signal left edge tick
                      + --panel-2, never a flooded fill (§9.2). */}
                  <button
                    type="button"
                    onClick={() => onSelectThread(thread.id)}
                    className={cn(
                      "relative w-full rounded-built p-3 pl-4 text-left transition-colors",
                      active ? "bg-panel-2" : "hover:bg-panel-2/50",
                    )}
                    style={{ border: "0.5px solid var(--hairline)" }}
                  >
                    {active ? (
                      <span aria-hidden className="absolute inset-y-0 left-0 w-0.5 bg-signal" />
                    ) : null}
                    <div className="flex items-start justify-between gap-2">
                      <p className="truncate text-[14px] font-medium text-text">{thread.title}</p>
                      <span
                        className="shrink-0 font-mono text-[11px] tabular-nums text-text-mute"
                        title={`${thread.claim_count} claim${thread.claim_count === 1 ? "" : "s"}`}
                      >
                        {thread.claim_count}
                      </span>
                    </div>
                    <p className="mt-1 line-clamp-2 text-[13px] leading-5 text-text-soft">
                      {thread.question}
                    </p>
                    <p className="mt-2 font-mono text-[11px] uppercase tracking-[0.1em] text-text-mute">
                      {thread.stage} · {thread.status.replace("_", " ")}
                    </p>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Bay>
  );
}
