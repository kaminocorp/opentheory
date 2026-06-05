"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GitBranch, GitFork, Plus, X } from "lucide-react";
import { useState } from "react";

import { closeBranch, createBranch, listBranches, listCheckpoints } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useDevActor } from "@/providers/dev-actor-provider";
import type { BranchCloseOutcome, BranchStatus } from "@/types/research";

const BRANCH_STATUS_META: Record<BranchStatus, { label: string; className: string }> = {
  open: { label: "open", className: "bg-signal/10 text-signal" },
  dead_end: { label: "dead end", className: "bg-ember/10 text-ember" },
  closed: { label: "closed", className: "bg-paper text-ink/55" },
  merged: { label: "merged", className: "bg-paper text-ink/55" },
};

const CLOSE_OUTCOMES: BranchCloseOutcome[] = ["dead_end", "closed"];

type BranchBarProps = {
  projectId: string;
  selectedBranchId: string | null;
  onSelectBranch: (branchId: string | null) => void;
};

export function BranchBar({ projectId, selectedBranchId, onSelectBranch }: BranchBarProps) {
  const { actorId, hydrated } = useDevActor();
  const queryClient = useQueryClient();
  const [forking, setForking] = useState(false);
  const [closing, setClosing] = useState(false);

  const branchesQuery = useQuery({
    queryKey: queryKeys.branches(projectId),
    queryFn: () => listBranches(projectId),
  });
  const branches = branchesQuery.data ?? [];
  const selectedBranch = branches.find((b) => b.id === selectedBranchId) ?? null;

  function invalidateAfterBranchWrite() {
    queryClient.invalidateQueries({ queryKey: queryKeys.branches(projectId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.checkpoints(projectId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.overview(projectId) });
  }

  return (
    <section className="grid gap-3 rounded-lg border border-line bg-white/70 p-3 shadow-panel">
      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.1em] text-ink/55">
          <GitBranch className="size-4 text-signal" aria-hidden="true" />
          Line
        </span>

        <button
          type="button"
          onClick={() => onSelectBranch(null)}
          className={`rounded-md border px-2.5 py-1 text-xs font-medium ${
            selectedBranchId === null
              ? "border-signal bg-signal/10 text-signal"
              : "border-line text-ink/65 hover:text-ink"
          }`}
        >
          Main line
        </button>

        {branchesQuery.isLoading ? (
          <span className="text-xs text-ink/45">Loading branches…</span>
        ) : branchesQuery.isError ? (
          <span className="text-xs text-ember">Could not load branches.</span>
        ) : (
          branches.map((branch) => {
            const meta = BRANCH_STATUS_META[branch.status];
            const selected = branch.id === selectedBranchId;
            return (
              <button
                key={branch.id}
                type="button"
                onClick={() => onSelectBranch(branch.id)}
                className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium ${
                  selected ? "border-signal bg-signal/10 text-signal" : "border-line text-ink/65 hover:text-ink"
                } ${branch.status === "dead_end" ? "line-through decoration-ember/60" : ""}`}
                title={branch.reason ?? undefined}
              >
                {branch.name}
                <span className="text-[10px] tabular-nums text-ink/45">{branch.checkpoint_count}</span>
                <span className={`rounded px-1 py-0.5 text-[10px] font-semibold ${meta.className}`}>
                  {meta.label}
                </span>
              </button>
            );
          })
        )}

        <button
          type="button"
          onClick={() => {
            setForking((v) => !v);
            setClosing(false);
          }}
          className="ml-auto inline-flex items-center gap-1 rounded-md border border-line px-2 py-1 text-xs font-medium text-ink/65 hover:text-ink"
        >
          {forking ? <X className="size-3.5" aria-hidden="true" /> : <GitFork className="size-3.5" aria-hidden="true" />}
          {forking ? "Cancel" : "Fork"}
        </button>

        {selectedBranch && selectedBranch.status === "open" ? (
          <button
            type="button"
            onClick={() => {
              setClosing((v) => !v);
              setForking(false);
            }}
            className="inline-flex items-center gap-1 rounded-md border border-line px-2 py-1 text-xs font-medium text-ink/65 hover:text-ember"
          >
            {closing ? "Cancel" : "Close branch"}
          </button>
        ) : null}
      </div>

      {selectedBranch ? (
        <p className="text-xs leading-5 text-ink/55">
          Viewing <span className="font-semibold text-ink/75">{selectedBranch.name}</span>
          {selectedBranch.reason ? ` — ${selectedBranch.reason}` : ""} · {selectedBranch.checkpoint_count}{" "}
          checkpoint{selectedBranch.checkpoint_count === 1 ? "" : "s"}
          {selectedBranch.forked_from_checkpoint_id
            ? ` · forked from ${selectedBranch.forked_from_checkpoint_id.slice(0, 8)}`
            : ""}
          . {selectedBranch.status === "open" ? "New checkpoints record on this branch." : "This line is closed."}
        </p>
      ) : (
        <p className="text-xs text-ink/45">Viewing the main line. Fork to explore a competing path without overwriting it.</p>
      )}

      {forking ? (
        <ForkBranchForm
          projectId={projectId}
          onCreated={(branchId) => {
            invalidateAfterBranchWrite();
            onSelectBranch(branchId);
            setForking(false);
          }}
        />
      ) : null}

      {closing && selectedBranch ? (
        <CloseBranchForm
          branchId={selectedBranch.id}
          branchName={selectedBranch.name}
          onClosed={() => {
            invalidateAfterBranchWrite();
            setClosing(false);
          }}
        />
      ) : null}

      {!actorId && hydrated ? (
        <p className="text-[11px] text-ember">Select an actor (top right) to fork or close branches.</p>
      ) : null}
    </section>
  );
}

function ForkBranchForm({
  projectId,
  onCreated,
}: {
  projectId: string;
  onCreated: (branchId: string) => void;
}) {
  const { actorId } = useDevActor();
  const [name, setName] = useState("");
  const [reason, setReason] = useState("");
  const [fromCheckpointId, setFromCheckpointId] = useState("");

  // Fork point picker: any existing checkpoint in the project.
  const checkpointsQuery = useQuery({
    queryKey: queryKeys.checkpoints(projectId),
    queryFn: () => listCheckpoints(projectId),
  });
  const checkpoints = checkpointsQuery.data ?? [];

  const mutation = useMutation({
    mutationFn: (actor: string) =>
      createBranch(
        projectId,
        {
          from_checkpoint_id: fromCheckpointId || checkpoints[0]?.id,
          name: name.trim(),
          reason: reason.trim() || null,
        },
        actor,
      ),
    onSuccess: (branch) => {
      setName("");
      setReason("");
      onCreated(branch.id);
    },
  });

  const effectiveFork = fromCheckpointId || checkpoints[0]?.id || "";
  const canSubmit = Boolean(actorId) && name.trim().length > 0 && Boolean(effectiveFork);

  if (!checkpointsQuery.isLoading && checkpoints.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-line bg-white/50 p-2.5 text-xs text-ink/55">
        Record a checkpoint first — a branch forks from an existing checkpoint.
      </p>
    );
  }

  return (
    <form
      className="grid gap-2 rounded-md border border-line bg-paper/60 p-3 sm:grid-cols-2"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSubmit && !mutation.isPending) mutation.mutate(actorId!);
      }}
    >
      <input
        value={name}
        onChange={(event) => setName(event.target.value)}
        placeholder="Branch name"
        className="h-9 rounded-md border border-line bg-white/80 px-2 text-sm outline-none focus:border-signal"
      />
      <select
        value={effectiveFork}
        onChange={(event) => setFromCheckpointId(event.target.value)}
        className="h-9 rounded-md border border-line bg-white/80 px-2 text-sm outline-none focus:border-signal"
      >
        {checkpoints.map((c) => (
          <option key={c.id} value={c.id}>
            from: {c.summary.slice(0, 48)}
          </option>
        ))}
      </select>
      <input
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        placeholder="Reason (optional)"
        className="h-9 rounded-md border border-line bg-white/80 px-2 text-sm outline-none focus:border-signal sm:col-span-2"
      />
      {mutation.isError ? (
        <p className="text-xs text-ember sm:col-span-2">{(mutation.error as Error).message}</p>
      ) : null}
      <button
        type="submit"
        disabled={!canSubmit || mutation.isPending}
        className="inline-flex h-9 items-center justify-center gap-1 rounded-md bg-ink px-3 text-sm font-semibold text-paper disabled:opacity-50 sm:col-span-2"
      >
        <Plus className="size-4" aria-hidden="true" />
        {mutation.isPending ? "Forking…" : "Fork branch"}
      </button>
    </form>
  );
}

function CloseBranchForm({
  branchId,
  branchName,
  onClosed,
}: {
  branchId: string;
  branchName: string;
  onClosed: () => void;
}) {
  const { actorId } = useDevActor();
  const [outcome, setOutcome] = useState<BranchCloseOutcome>("dead_end");
  const [reason, setReason] = useState("");

  const mutation = useMutation({
    mutationFn: (actor: string) =>
      closeBranch(branchId, { outcome, reason: reason.trim() || null }, actor),
    onSuccess: () => {
      setReason("");
      onClosed();
    },
  });

  const canSubmit = Boolean(actorId) && reason.trim().length > 0;

  return (
    <form
      className="grid gap-2 rounded-md border border-ember/30 bg-white/70 p-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSubmit && !mutation.isPending) mutation.mutate(actorId!);
      }}
    >
      <p className="text-xs text-ink/60">
        Closing <span className="font-semibold">{branchName}</span> preserves its reasoning — it is recorded, not deleted.
      </p>
      <div className="flex gap-2">
        <select
          value={outcome}
          onChange={(event) => setOutcome(event.target.value as BranchCloseOutcome)}
          className="h-9 rounded-md border border-line bg-white/80 px-2 text-sm capitalize outline-none focus:border-signal"
        >
          {CLOSE_OUTCOMES.map((o) => (
            <option key={o} value={o}>
              {o === "dead_end" ? "dead end" : "closed"}
            </option>
          ))}
        </select>
        <input
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="Reason (required)"
          className="h-9 min-w-0 flex-1 rounded-md border border-line bg-white/80 px-2 text-sm outline-none focus:border-signal"
        />
      </div>
      {mutation.isError ? (
        <p className="text-xs text-ember">{(mutation.error as Error).message}</p>
      ) : null}
      <button
        type="submit"
        disabled={!canSubmit || mutation.isPending}
        className="inline-flex h-9 items-center justify-center rounded-md bg-ember px-3 text-sm font-semibold text-paper disabled:opacity-50"
      >
        {mutation.isPending ? "Closing…" : "Close branch"}
      </button>
    </form>
  );
}
