"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GitBranch, GitFork, GitMerge, Plus, X } from "lucide-react";
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
import { closeBranch, createBranch, listBranches, listCheckpoints, mergeBranches } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useActingIdentity } from "@/lib/use-identity";
import { cn } from "@/lib/cn";
import type { BranchCloseOutcome, BranchStatus, MergeResolution } from "@/types/research";

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
  const [merging, setMerging] = useState(false);

  const branchesQuery = useQuery({
    queryKey: queryKeys.branches(projectId),
    queryFn: () => listBranches(projectId),
  });
  const branches = branchesQuery.data ?? [];
  const selectedBranch = branches.find((b) => b.id === selectedBranchId) ?? null;
  const openBranches = branches.filter((b) => b.status === "open");

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
                <span className={cn("text-[11px] capitalize", STATE_META[tone].text)}>
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
                setMerging(false);
              }}
              className="h-7"
            >
              <Icon icon={forking ? X : GitFork} size={14} />
              {forking ? "Cancel" : "Fork"}
            </ActionGhost>

            {openBranches.length > 0 ? (
              <ActionGhost
                size="sm"
                onClick={() => {
                  setMerging((v) => !v);
                  setForking(false);
                  setClosing(false);
                }}
                className="h-7"
              >
                <Icon icon={merging ? X : GitMerge} size={14} />
                {merging ? "Cancel" : "Merge"}
              </ActionGhost>
            ) : null}

            {selectedBranch && selectedBranch.status === "open" ? (
              <button
                type="button"
                onClick={() => {
                  setClosing((v) => !v);
                  setForking(false);
                  setMerging(false);
                }}
                className="inline-flex h-7 items-center rounded-full px-3 text-[12px] font-medium text-text-mute transition-colors hover:text-state-fail"
                style={{ border: "1px solid var(--hairline)" }}
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
          .{" "}
          {selectedBranch.status === "open"
            ? "New checkpoints record on this branch."
            : selectedBranch.status === "merged"
              ? "This line is merged — preserved, not extended."
              : "This line is closed."}
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

      {merging ? (
        <MergeBranchesForm
          projectId={projectId}
          openBranches={openBranches}
          selectedBranchId={selectedBranchId}
          onMerged={(targetBranchId) => {
            invalidateAfterBranchWrite();
            onSelectBranch(targetBranchId);
            setMerging(false);
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
        style={{ border: "1px dashed var(--hairline)" }}
      >
        Record a checkpoint first — a branch forks from an existing checkpoint.
      </p>
    );
  }

  return (
    <form
      className="grid gap-2 rounded-built bg-panel-2 p-3 sm:grid-cols-2"
      style={{ border: "1px solid var(--hairline)" }}
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

function MergeBranchesForm({
  projectId,
  openBranches,
  selectedBranchId,
  onMerged,
}: {
  projectId: string;
  openBranches: { id: string; name: string }[];
  selectedBranchId: string | null;
  onMerged: (targetBranchId: string | null) => void;
}) {
  const { canWrite } = useActingIdentity();
  const defaultSource =
    selectedBranchId && openBranches.some((b) => b.id === selectedBranchId)
      ? selectedBranchId
      : (openBranches[0]?.id ?? "");
  const [sourceIds, setSourceIds] = useState<string[]>(defaultSource ? [defaultSource] : []);
  const [targetId, setTargetId] = useState("");
  const [resolution, setResolution] = useState<MergeResolution>("clean");
  const [rationale, setRationale] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      mergeBranches(projectId, {
        source_branch_ids: sourceIds,
        target_branch_id: targetId || null,
        resolution,
        rationale: rationale.trim() || null,
      }),
    onSuccess: (result) => {
      onMerged(result.target_branch_id);
    },
  });

  const targetIsSource = Boolean(targetId) && sourceIds.includes(targetId);
  const needsRationale = resolution === "resolved";
  const canSubmit =
    canWrite &&
    sourceIds.length > 0 &&
    !targetIsSource &&
    (!needsRationale || rationale.trim().length > 0);

  function toggleSource(id: string) {
    setSourceIds((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  }

  return (
    <form
      className="grid gap-2 rounded-built bg-panel-2 p-3"
      style={{ border: "1px solid var(--hairline)" }}
      onSubmit={(event) => {
        event.preventDefault();
        if (canSubmit && !mutation.isPending) mutation.mutate();
      }}
    >
      <p className="text-[12px] leading-5 text-text-mute">
        Combine open lines into one checkpoint with multiple parents. Source lines are marked
        merged and kept — history is not rewritten.
      </p>
      <fieldset className="grid gap-1.5">
        <legend className="text-[11px] text-text-faint">Source lines</legend>
        {openBranches.map((branch) => (
          <label key={branch.id} className="flex items-center gap-2 text-[12px] text-text-soft">
            <input
              type="checkbox"
              checked={sourceIds.includes(branch.id)}
              onChange={() => toggleSource(branch.id)}
              className="accent-[rgb(var(--signal))]"
            />
            {branch.name}
          </label>
        ))}
      </fieldset>
      <Select
        aria-label="Merge into"
        value={targetId}
        onChange={(event) => setTargetId(event.target.value)}
      >
        <option value="">into: main line</option>
        {openBranches
          .filter((branch) => !sourceIds.includes(branch.id))
          .map((branch) => (
            <option key={branch.id} value={branch.id}>
              into: {branch.name}
            </option>
          ))}
      </Select>
      <Select
        aria-label="Merge resolution"
        value={resolution}
        onChange={(event) => setResolution(event.target.value as MergeResolution)}
      >
        <option value="clean">clean — the lines agree</option>
        <option value="resolved">resolved — record the decision</option>
      </Select>
      <Input
        value={rationale}
        onChange={(event) => setRationale(event.target.value)}
        placeholder={needsRationale ? "Rationale (required)" : "Rationale (optional)"}
      />
      {targetIsSource ? (
        <p className="text-[12px] text-state-fail">A source line cannot also be the target.</p>
      ) : null}
      {mutation.isError ? (
        <p className="text-[12px] text-state-fail">{(mutation.error as Error).message}</p>
      ) : null}
      <Action
        type="submit"
        disabled={!canSubmit || mutation.isPending}
        pending={mutation.isPending}
        className="w-full"
      >
        <Icon icon={GitMerge} size={16} />
        {mutation.isPending ? "Merging…" : "Merge lines"}
      </Action>
    </form>
  );
}
