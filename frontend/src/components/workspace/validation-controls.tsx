"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Action, Input, Select, StatusPill, type StateTone } from "@/components/console";
import { createValidation } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useActingIdentity } from "@/lib/use-identity";
import type { ValidationOutcome, ValidationTargetType } from "@/types/research";

// Outcome → a state tone + label (+ glyph override). Mapping onto the shared
// STATE_META tones (not bespoke colours) is what keeps the vocabulary identical
// across the claim and checkpoint surfaces and grayscale-safe (§1, §9.3): meaning
// rides on glyph + label, colour only reinforces. A `failed`/`contradicts` badge
// is never dimmer or smaller than `passed` — StatusPill enforces equal weight.
export const OUTCOME_META: Record<
  ValidationOutcome,
  { label: string; tone: StateTone; glyph?: string }
> = {
  passed: { label: "passed", tone: "ok" }, // ✓
  failed: { label: "failed", tone: "fail" }, // ■
  inconclusive: { label: "inconclusive", tone: "mute" }, // ▣
  needs_reproduction: { label: "needs repro", tone: "warn" }, // ▲ amber
  // Fail colour, but a triangle to read distinctly from `failed`'s ■ (echoes the
  // overview contradiction marker); label disambiguates from `needs repro`.
  contradicts: { label: "contradicts", tone: "fail", glyph: "▲" },
  retract: { label: "retract", tone: "faint" }, // ·
};

export const VALIDATION_OUTCOMES = Object.keys(OUTCOME_META) as ValidationOutcome[];

// Outcomes that signal a claim is contested (used for the contradiction indicator).
export const CONTRADICTION_OUTCOMES: ValidationOutcome[] = ["contradicts", "failed"];

export function OutcomeBadge({ outcome }: { outcome: ValidationOutcome }) {
  const meta = OUTCOME_META[outcome];
  return <StatusPill tone={meta.tone} label={meta.label} glyph={meta.glyph} />;
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
  const { canWrite, hydrated, signInHint } = useActingIdentity();
  const queryClient = useQueryClient();
  const [outcome, setOutcome] = useState<ValidationOutcome>("passed");
  const [notes, setNotes] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      createValidation(projectId, {
        target_type: targetType,
        target_id: targetId,
        outcome,
        notes: notes.trim() || null,
      }),
    onSuccess: () => {
      if (invalidateKey) queryClient.invalidateQueries({ queryKey: invalidateKey });
      // A validation mints a checkpoint and bumps the project's checkpoint count.
      queryClient.invalidateQueries({ queryKey: queryKeys.checkpoints(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.overview(projectId) });
      setNotes("");
      onDone?.();
    },
  });

  const canSubmit = canWrite;

  return (
    // Nested form tray on --panel-2 so its --panel fields read as recessed wells.
    <form
      className={`mt-2 grid rounded-built bg-panel-2 p-2.5 ${compact ? "gap-1.5" : "gap-2"}`}
      style={{ border: "0.5px solid var(--hairline)" }}
      onSubmit={(event) => {
        event.preventDefault();
        if (canSubmit && !mutation.isPending) mutation.mutate();
      }}
    >
      {/* outcome is an enum token → mono Select; notes are prose → sans Input. */}
      <Select
        aria-label="Validation outcome"
        value={outcome}
        onChange={(event) => setOutcome(event.target.value as ValidationOutcome)}
      >
        {VALIDATION_OUTCOMES.map((o) => (
          <option key={o} value={o}>
            {OUTCOME_META[o].label}
          </option>
        ))}
      </Select>
      <Input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Notes (optional)" />
      {!canWrite && hydrated ? (
        <p className="text-[11px] text-state-warn">{signInHint} to record validations.</p>
      ) : null}
      {mutation.isError ? (
        <p className="text-[11px] text-state-fail">{(mutation.error as Error).message}</p>
      ) : null}
      <Action
        type="submit"
        disabled={!canSubmit || mutation.isPending}
        pending={mutation.isPending}
        className="w-full"
      >
        {mutation.isPending ? "Recording…" : "Record validation"}
      </Action>
    </form>
  );
}
