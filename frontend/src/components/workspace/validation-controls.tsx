"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  CircleHelp,
  RefreshCw,
  XCircle,
} from "lucide-react";
import type { ComponentType } from "react";
import { useState } from "react";

import { createValidation } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useDevActor } from "@/providers/dev-actor-provider";
import type { ValidationOutcome, ValidationTargetType } from "@/types/research";

// Outcome → label, icon, and palette (the app's signal/ember/ink/paper tokens). Shared by
// the claim and checkpoint validation surfaces so the vocabulary reads identically.
export const OUTCOME_META: Record<
  ValidationOutcome,
  { label: string; icon: ComponentType<{ className?: string }>; className: string }
> = {
  passed: { label: "passed", icon: CheckCircle2, className: "bg-signal/10 text-signal" },
  failed: { label: "failed", icon: XCircle, className: "bg-ember/10 text-ember" },
  inconclusive: { label: "inconclusive", icon: CircleHelp, className: "bg-paper text-ink/60" },
  needs_reproduction: {
    label: "needs repro",
    icon: RefreshCw,
    className: "bg-paper text-ink/70",
  },
  contradicts: { label: "contradicts", icon: AlertTriangle, className: "bg-ember/15 text-ember" },
  retract: { label: "retract", icon: Ban, className: "bg-paper text-ink/45" },
};

export const VALIDATION_OUTCOMES = Object.keys(OUTCOME_META) as ValidationOutcome[];

// Outcomes that signal a claim is contested (used for the contradiction indicator).
export const CONTRADICTION_OUTCOMES: ValidationOutcome[] = ["contradicts", "failed"];

export function OutcomeBadge({ outcome }: { outcome: ValidationOutcome }) {
  const meta = OUTCOME_META[outcome];
  const Icon = meta.icon;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-semibold ${meta.className}`}
    >
      <Icon className="size-3" aria-hidden="true" />
      {meta.label}
    </span>
  );
}

type RecordValidationFormProps = {
  projectId: string;
  targetType: ValidationTargetType;
  targetId: string;
  // Invalidate the per-target validation history (e.g. a claim's) on success, if any.
  invalidateKey?: readonly unknown[];
  onDone?: () => void;
  compact?: boolean;
};

export function RecordValidationForm({
  projectId,
  targetType,
  targetId,
  invalidateKey,
  onDone,
  compact = false,
}: RecordValidationFormProps) {
  const { actorId, hydrated } = useDevActor();
  const queryClient = useQueryClient();
  const [outcome, setOutcome] = useState<ValidationOutcome>("passed");
  const [notes, setNotes] = useState("");

  const mutation = useMutation({
    mutationFn: (actor: string) =>
      createValidation(
        projectId,
        { target_type: targetType, target_id: targetId, outcome, notes: notes.trim() || null },
        actor,
      ),
    onSuccess: () => {
      if (invalidateKey) queryClient.invalidateQueries({ queryKey: invalidateKey });
      // A validation mints a checkpoint and bumps the project's checkpoint count.
      queryClient.invalidateQueries({ queryKey: queryKeys.checkpoints(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.overview(projectId) });
      setNotes("");
      onDone?.();
    },
  });

  const canSubmit = Boolean(actorId);
  const field = compact ? "h-8 text-xs" : "h-9 text-sm";

  return (
    <form
      className="mt-2 grid gap-2 rounded-md border border-line bg-paper/60 p-2.5"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSubmit && !mutation.isPending) mutation.mutate(actorId!);
      }}
    >
      <select
        value={outcome}
        onChange={(event) => setOutcome(event.target.value as ValidationOutcome)}
        className={`${field} rounded-md border border-line bg-white/80 px-2 capitalize outline-none focus:border-signal`}
      >
        {VALIDATION_OUTCOMES.map((o) => (
          <option key={o} value={o}>
            {OUTCOME_META[o].label}
          </option>
        ))}
      </select>
      <input
        value={notes}
        onChange={(event) => setNotes(event.target.value)}
        placeholder="Notes (optional)"
        className={`${field} rounded-md border border-line bg-white/80 px-2 outline-none focus:border-signal`}
      />
      {!actorId && hydrated ? (
        <p className="text-[11px] text-ember">Select an actor (top right) to record validations.</p>
      ) : null}
      {mutation.isError ? (
        <p className="text-[11px] text-ember">{(mutation.error as Error).message}</p>
      ) : null}
      <button
        type="submit"
        disabled={!canSubmit || mutation.isPending}
        className={`${compact ? "h-8 text-xs" : "h-9 text-sm"} inline-flex items-center justify-center rounded-md bg-ink px-3 font-semibold text-paper disabled:opacity-50`}
      >
        {mutation.isPending ? "Recording…" : "Record validation"}
      </button>
    </form>
  );
}
