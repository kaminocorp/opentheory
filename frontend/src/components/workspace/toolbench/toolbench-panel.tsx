"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, FlaskConical, Play } from "lucide-react";
import { useEffect, useState } from "react";

import { Action, AwaitingState, Bay, Icon, ReadoutLabel, Select, StatusPill } from "@/components/console";
import { getInstrumentCatalog, listClaims, runInstrument } from "@/lib/api";
import { cn } from "@/lib/cn";
import { queryKeys } from "@/lib/query-keys";
import { useActingIdentity } from "@/lib/use-identity";
import type { Claim } from "@/types/research";
import type { InstrumentDescriptor, ToolRunResult } from "@/types/toolbench";

import { AssumptionsEditor, buildAssumptions, demoAssumptionRows } from "./assumptions-editor";
import { DriveForm } from "./drive-forms";
import { outcomeMeta } from "./outcome";
import { ResultView } from "./result-view";

const truncate = (text: string, n = 60): string => (text.length > n ? `${text.slice(0, n)}…` : text);

/**
 * One instrument's run surface — the two columns of Phase 7: **drive** (the instrument-specific
 * input form + assumptions + optional claim target) and **show** (the result card once it runs). The
 * whole runner is keyed by instrument name in the panel, so switching instruments resets every field
 * to that instrument's demo defaults.
 */
function InstrumentRunner({
  descriptor,
  projectId,
  threadId,
  canRun,
}: {
  descriptor: InstrumentDescriptor;
  projectId: string;
  threadId: string | null;
  canRun: boolean;
}) {
  const { isAuthed, hydrated } = useActingIdentity();
  const queryClient = useQueryClient();

  const [inputs, setInputs] = useState<Record<string, unknown> | null>(null);
  const [assumptions, setAssumptions] = useState<Record<string, unknown>>(() =>
    buildAssumptions(demoAssumptionRows(descriptor.name)),
  );
  const [claimId, setClaimId] = useState<string>("");
  const [result, setResult] = useState<ToolRunResult | null>(null);

  // A claim belongs to a specific thread, so a stale selection must not survive a scope change —
  // otherwise a run could attach Evidence to a claim from a thread it is no longer scoped to.
  useEffect(() => {
    setClaimId("");
  }, [threadId]);

  // Claims of the selected thread — offered as an optional evidence target (a run against a claim
  // mints Evidence linked to it). Only fetched when a thread is in scope.
  const claimsQuery = useQuery({
    queryKey: queryKeys.claims(threadId ?? ""),
    queryFn: () => listClaims(threadId as string),
    enabled: Boolean(threadId),
  });
  const claims: Claim[] = claimsQuery.data ?? [];

  const run = useMutation({
    mutationFn: () =>
      runInstrument(projectId, descriptor.name, {
        inputs: inputs as Record<string, unknown>,
        assumptions,
        thread_id: threadId,
        claim_id: claimId || null,
      }),
    onSuccess: (produced) => {
      setResult(produced);
      // The run landed a checkpoint (+ maybe evidence) in the ledger — refresh what shows it.
      queryClient.invalidateQueries({ queryKey: queryKeys.checkpoints(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.overview(projectId) });
      if (claimId) queryClient.invalidateQueries({ queryKey: queryKeys.evidence(claimId) });
    },
  });

  const runnable = canRun && inputs !== null && !run.isPending;
  const gateHint = !isAuthed
    ? "Sign in to run instruments."
    : "You must be a project member to run instruments.";

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {/* Drive column */}
      <div className="grid content-start gap-4">
        <DriveForm descriptor={descriptor} onInputs={setInputs} disabled={!canRun} />

        <AssumptionsEditor
          initialRows={demoAssumptionRows(descriptor.name)}
          onChange={setAssumptions}
          disabled={!canRun}
        />

        {/* Scope + optional evidence target. A run always records on the ledger; a claim target also
            mints Evidence linked to that claim. */}
        <div className="grid gap-2">
          <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-text-mute">
            {threadId ? "Scoped to the selected thread" : "Records on the project main line"}
          </span>
          {threadId && claims.length > 0 ? (
            <Select
              value={claimId}
              onChange={(event) => setClaimId(event.target.value)}
              aria-label="Attach the result as evidence to a claim"
              disabled={!canRun}
            >
              <option value="">— Don&apos;t attach to a claim —</option>
              {claims.map((claim) => (
                <option key={claim.id} value={claim.id}>
                  {truncate(claim.statement)}
                </option>
              ))}
            </Select>
          ) : null}
        </div>

        <div className="grid gap-2">
          <Action
            type="button"
            onClick={() => runnable && run.mutate()}
            disabled={!runnable}
            pending={run.isPending}
            className="w-full"
          >
            <Icon icon={Play} size={15} />
            {run.isPending ? "Running…" : "Run"}
          </Action>
          {!canRun && hydrated ? <p className="text-[12px] text-state-warn">{gateHint}</p> : null}
          {run.isError ? (
            <p role="alert" className="text-[12px] text-state-fail">
              {(run.error as Error).message}
            </p>
          ) : null}
        </div>
      </div>

      {/* Show column */}
      <div className="grid content-start gap-3">
        {result ? (
          <ResultView descriptor={descriptor} result={result} />
        ) : (
          <div
            className="grid min-h-40 place-items-center rounded-built bg-panel-2"
            style={{ border: "0.5px solid var(--hairline)" }}
          >
            <AwaitingState variant="empty" label="run to see a result" />
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * The toolbench (Phase 7): pick a deterministic maths instrument, run it as a project member, and
 * see the result land in the ledger with its blame tuple + assumptions. The catalog is the public,
 * static Phase-6 endpoint; the run is the membership-gated write. Collapsible, so it stays
 * discoverable without dominating the workspace.
 */
export function ToolbenchPanel({
  projectId,
  selectedThreadId,
  canRun,
}: {
  projectId: string;
  selectedThreadId: string | null;
  canRun: boolean;
}) {
  const [open, setOpen] = useState(true);
  const [selectedName, setSelectedName] = useState<string | null>(null);

  const catalogQuery = useQuery({
    queryKey: queryKeys.instrumentCatalog,
    queryFn: getInstrumentCatalog,
    staleTime: Infinity,
    gcTime: Infinity,
  });
  const catalog = catalogQuery.data ?? [];
  const selected = catalog.find((instrument) => instrument.name === selectedName) ?? catalog[0];

  return (
    <Bay density="narrative" className="grid gap-4">
      <header className="flex items-center justify-between">
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
          className="flex items-center gap-2 text-text-mute transition-colors hover:text-text"
        >
          <Icon icon={open ? ChevronDown : ChevronRight} size={14} />
          <Icon icon={FlaskConical} size={15} />
          <ReadoutLabel>Instruments · Toolbench</ReadoutLabel>
        </button>
        {catalog.length > 0 ? (
          <span className="font-mono text-[11px] tabular-nums text-text-mute">{catalog.length}</span>
        ) : null}
      </header>

      {open ? (
        catalogQuery.isLoading ? (
          <AwaitingState variant="loading" label="loading instruments" />
        ) : catalogQuery.isError || !selected ? (
          <AwaitingState variant="error" label="instruments unavailable" />
        ) : (
          <div className="grid gap-4">
            {/* Instrument picker — a segmented control over the code registry. */}
            <div className="flex flex-wrap gap-2">
              {catalog.map((instrument) => {
                const active = instrument.name === selected.name;
                return (
                  <button
                    key={instrument.name}
                    type="button"
                    onClick={() => setSelectedName(instrument.name)}
                    aria-pressed={active}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-full px-3 py-1 font-mono text-[12px] transition-colors",
                      active ? "bg-panel-2 text-text" : "text-text-mute hover:text-text",
                    )}
                    style={{
                      border: `0.5px solid var(--hairline${active ? "-strong" : ""})`,
                    }}
                  >
                    {active ? <span aria-hidden className="size-1.5 rounded-full bg-signal" /> : null}
                    {instrument.name}
                  </button>
                );
              })}
            </div>

            {/* Selected instrument: description, version/engine, and the self-describing outcome
                contract (so the honesty of "undecided ≠ pass" is stated up front). */}
            <div className="grid gap-2">
              <p className="text-[13px] leading-[1.5] text-text-soft">{selected.description}</p>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="font-mono text-[11px] text-text-faint">
                  {selected.name}@{selected.version} · {selected.engine}@{selected.engine_version}
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {selected.result_contract.map((outcome) => {
                  const meta = outcomeMeta(outcome.status);
                  return (
                    <span key={outcome.status} title={outcome.meaning}>
                      <StatusPill tone={meta.tone} label={outcome.status.toUpperCase()} />
                    </span>
                  );
                })}
              </div>
            </div>

            {/* Keyed by name: switching instruments resets the drive/assumptions/result state. */}
            <InstrumentRunner
              key={selected.name}
              descriptor={selected}
              projectId={projectId}
              threadId={selectedThreadId}
              canRun={canRun}
            />
          </div>
        )
      ) : null}
    </Bay>
  );
}
