"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GitBranch, GitFork, Plus, X } from "lucide-react";
import { useState } from "react";

import {
  Action,
  ActionDestructive,
  ActionGhost,
  Bay,
  Icon,
  Input,
  ReadoutLabel,
  Select,
  STATE_META,
  type StateTone,
} from "@/components/console";
import { closeBranch, createBranch, listBranches, listCheckpoints } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useActingIdentity } from "@/lib/use-identity";
import { cn } from "@/lib/cn";
import type { BranchCloseOutcome, BranchStatus } from "@/types/research";

// Branch status → a state tone + label. dead_end also keeps a strike-through (below)
// as the honest "recorded, not deleted" mark — meaning survives grayscale via glyph +
// label + strike, not colour.
const branchStatusTone: Record<BranchStatus, StateTone> = {
  open: "run",
  dead_end: "fail",
  closed: "mute",
  merged: "mute",
};
const branchStatusLabel: Record<BranchStatus, string> = {
  open: "open",
  dead_end: "dead end",
  closed: "closed",
  merged: "merged",
};

const CLOSE_OUTCOMES: BranchCloseOutcome[] = ["dead_end", "closed"];

type BranchBarProps = {
  projectId: string;
  selectedBranchId: string | null;
  onSelectBranch: (branchId: string | null) => void;
};

// D4 re-skin: console tokens + primitives only. Every hook, mutation, and the
// fork/close write flows below are unchanged — presentation, not behaviour.
export function BranchBar({ projectId, selectedBranchId, onSelectBranch }: BranchBarProps) {
  const { canWrite } = useActingIdentity();
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
    <Bay density="none" className="grid gap-3 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-1 flex items-center gap-1.5 text-text-mute">
          <Icon icon={GitBranch} size={14} />
          <ReadoutLabel>Line</ReadoutLabel>
        </span>

        {/* Selectable line pills — round (alive). Active = a signal ring + signal
            text, never a flooded block (§9.2). */}
        <LinePill selected={selectedBranchId === null} onClick={() => onSelectBranch(null)}>
          Main line
        </LinePill>

        {branchesQuery.isLoading ? (
          <span className="text-xs text-text-mute">Loading branches…</span>
        ) : branchesQuery.isError ? (
          <span className="text-xs text-state-fail">Could not load branches.</span>
        ) : (
          branches.map((branch) => {
            const tone = branchStatusTone[branch.status];
            const isDeadEnd = branch.status === "dead_end";
            return (
              <LinePill
                key={branch.id}
                selected={branch.id === selectedBranchId}
                onClick={() => onSelectBranch(branch.id)}
                title={branch.reason ?? undefined}
              >
                <span
                  className={isDeadEnd ? "line-through" : undefined}
                  style={isDeadEnd ? { textDecorationColor: "rgb(var(--state-fail))" } : undefined}
                >
                  {branch.name}
                </span>
                <span className="font-mono text-[10px] tabular-nums text-text-faint">
                  {branch.checkpoint_count}
                </span>
                <span className={cn("font-mono text-[10px] uppercase tracking-[0.06em]", STATE_META[tone].text)}>
                  {STATE_META[tone].glyph} {branchStatusLabel[branch.status]}
                </span>
              </LinePill>
            );
          })
        )}

        {/* Write affordances: fork/close are shown only to a signed-in actor (read-only otherwise). */}
        {canWrite ? (
          <div className="ml-auto flex items-center gap-2">
            <ActionGhost
              size="sm"
              onClick={() => {
                setForking((v) => !v);
                setClosing(false);
              }}
              className="h-7"
            >
              <Icon icon={forking ? X : GitFork} size={14} />
              {forking ? "Cancel" : "Fork"}
            </ActionGhost>

            {selectedBranch && selectedBranch.status === "open" ? (
              <button
                type="button"
                onClick={() => {
                  setClosing((v) => !v);
                  setForking(false);
                }}
                className="inline-flex h-7 items-center rounded-full px-3 text-[12px] font-medium text-text-mute transition-colors hover:text-state-fail"
                style={{ border: "0.5px solid var(--hairline)" }}
              >
                {closing ? "Cancel" : "Close branch"}
              </button>
            ) : null}
          </div>
        ) : null}
      </div>

      {selectedBranch ? (
        <p className="text-[12px] leading-5 text-text-mute">
          Viewing <span className="font-medium text-text-soft">{selectedBranch.name}</span>
          {selectedBranch.reason ? ` — ${selectedBranch.reason}` : ""} · {selectedBranch.checkpoint_count}{" "}
          checkpoint{selectedBranch.checkpoint_count === 1 ? "" : "s"}
          {selectedBranch.forked_from_checkpoint_id ? (
            <>
              {" "}
              · forked from{" "}
              <span className="font-mono text-text-faint">
                {selectedBranch.forked_from_checkpoint_id.slice(0, 8)}
              </span>
            </>
          ) : null}
          . {selectedBranch.status === "open" ? "New checkpoints record on this branch." : "This line is closed."}
        </p>
      ) : (
        <p className="text-[12px] text-text-faint">
          Viewing the main line. Fork to explore a competing path without overwriting it.
        </p>
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
    </Bay>
  );
}

// A round selectable line pill. Selected = a signal ring + signal text (marked,
// not flooded); unselected = hairline ring + muted text.
function LinePill({
  selected,
  onClick,
  title,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-pressed={selected}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors",
        // Selection is marked by weight (a non-hue channel — survives grayscale) as well
        // as the signal ring/text, so it never depends on colour alone (§1).
        selected ? "font-semibold text-signal" : "font-medium text-text-mute hover:text-text",
      )}
      style={{ borderColor: selected ? "rgb(var(--signal))" : "var(--hairline)" }}
    >
      {children}
    </button>
  );
}

function ForkBranchForm({
  projectId,
  onCreated,
}: {
  projectId: string;
  onCreated: (branchId: string) => void;
}) {
  const { canWrite } = useActingIdentity();
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
    mutationFn: () =>
      createBranch(projectId, {
        from_checkpoint_id: fromCheckpointId || checkpoints[0]?.id,
        name: name.trim(),
        reason: reason.trim() || null,
      }),
    onSuccess: (branch) => {
      setName("");
      setReason("");
      onCreated(branch.id);
    },
  });

  const effectiveFork = fromCheckpointId || checkpoints[0]?.id || "";
  const canSubmit = canWrite && name.trim().length > 0 && Boolean(effectiveFork);

  if (!checkpointsQuery.isLoading && checkpoints.length === 0) {
    return (
      <p
        className="rounded-built bg-panel-2 p-2.5 text-[12px] text-text-mute"
        style={{ border: "0.5px dashed var(--hairline)" }}
      >
        Record a checkpoint first — a branch forks from an existing checkpoint.
      </p>
    );
  }

  return (
    <form
      className="grid gap-2 rounded-built bg-panel-2 p-3 sm:grid-cols-2"
      style={{ border: "0.5px solid var(--hairline)" }}
      onSubmit={(event) => {
        event.preventDefault();
        if (canSubmit && !mutation.isPending) mutation.mutate();
      }}
    >
      <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Branch name" />
      <Select
        aria-label="Fork from checkpoint"
        value={effectiveFork}
        onChange={(event) => setFromCheckpointId(event.target.value)}
      >
        {checkpoints.map((c) => (
          <option key={c.id} value={c.id}>
            from: {c.summary.slice(0, 48)}
          </option>
        ))}
      </Select>
      <Input
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        placeholder="Reason (optional)"
        className="sm:col-span-2"
      />
      {mutation.isError ? (
        <p className="text-[12px] text-state-fail sm:col-span-2">{(mutation.error as Error).message}</p>
      ) : null}
      <Action
        type="submit"
        disabled={!canSubmit || mutation.isPending}
        pending={mutation.isPending}
        className="w-full sm:col-span-2"
      >
        <Icon icon={Plus} size={16} />
        {mutation.isPending ? "Forking…" : "Fork branch"}
      </Action>
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
  const { canWrite } = useActingIdentity();
  const [outcome, setOutcome] = useState<BranchCloseOutcome>("dead_end");
  const [reason, setReason] = useState("");

  const mutation = useMutation({
    mutationFn: () => closeBranch(branchId, { outcome, reason: reason.trim() || null }),
    onSuccess: () => {
      setReason("");
      onClosed();
    },
  });

  const canSubmit = canWrite && reason.trim().length > 0;

  return (
    // Destructive context is *marked* with a state-fail edge tick, not a flooded
    // red fill (§5.7). The action itself is a ring, below.
    <form
      className="relative grid gap-2 rounded-built bg-panel-2 p-3 pl-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSubmit && !mutation.isPending) mutation.mutate();
      }}
    >
      <span aria-hidden className="absolute inset-y-0 left-0 w-0.5 bg-state-fail" />
      <p className="text-[12px] text-text-mute">
        Closing <span className="font-medium text-text-soft">{branchName}</span> preserves its reasoning —
        it is recorded, not deleted.
      </p>
      <div className="flex gap-2">
        <Select
          aria-label="Close outcome"
          value={outcome}
          onChange={(event) => setOutcome(event.target.value as BranchCloseOutcome)}
        >
          {CLOSE_OUTCOMES.map((o) => (
            <option key={o} value={o}>
              {o === "dead_end" ? "dead end" : "closed"}
            </option>
          ))}
        </Select>
        <Input
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="Reason (required)"
          className="min-w-0 flex-1"
        />
      </div>
      {mutation.isError ? (
        <p className="text-[12px] text-state-fail">{(mutation.error as Error).message}</p>
      ) : null}
      <ActionDestructive
        type="submit"
        disabled={!canSubmit || mutation.isPending}
        pending={mutation.isPending}
      >
        {mutation.isPending ? "Closing…" : "Close branch"}
      </ActionDestructive>
    </form>
  );
}
