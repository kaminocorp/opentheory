"use client";

import { useQuery } from "@tanstack/react-query";
import { ScanSearch } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Action, Bay, BayHeader, Icon, Select } from "@/components/console";
import { getClaimBlame, listClaims } from "@/lib/api";
import { blameAuthorLine, blameInstrumentLine, blameMovementLine } from "@/lib/blame";
import { queryKeys } from "@/lib/query-keys";
import type { ClaimBlameRead, ClaimBlameStep } from "@/types/research";

import { PanelEmpty, PanelError, PanelLoading } from "./panel-state";

type BlamePanelProps = {
  projectId: string;
  threadId: string | null;
  selectedClaimId: string | null;
};

export function BlamePanel({ projectId, threadId, selectedClaimId }: BlamePanelProps) {
  const claimsQuery = useQuery({
    queryKey: queryKeys.claims(threadId ?? ""),
    queryFn: () => listClaims(threadId as string),
    enabled: Boolean(threadId),
  });

  const claims = useMemo(() => claimsQuery.data ?? [], [claimsQuery.data]);
  const defaultClaimId = selectedClaimId ?? claims[0]?.id ?? "";
  const [pickedClaimId, setPickedClaimId] = useState("");
  const [submittedClaimId, setSubmittedClaimId] = useState<string | null>(null);

  useEffect(() => {
    setPickedClaimId(selectedClaimId ?? "");
    setSubmittedClaimId(selectedClaimId);
  }, [threadId, selectedClaimId]);

  const effectiveClaimId = pickedClaimId || selectedClaimId || defaultClaimId;

  const blameQuery = useQuery({
    queryKey: queryKeys.claimBlame(projectId, submittedClaimId ?? ""),
    queryFn: () => getClaimBlame(projectId, submittedClaimId!),
    enabled: Boolean(submittedClaimId),
  });

  const options = useMemo(
    () =>
      claims.map((claim) => ({
        value: claim.id,
        label: claim.statement.slice(0, 72) || claim.id.slice(0, 8),
      })),
    [claims],
  );

  return (
    <Bay density="none" className="flex flex-col">
      <BayHeader
        label={
          <span className="inline-flex items-center gap-1.5">
            <Icon icon={ScanSearch} size={14} />
            Blame
          </span>
        }
        divider
      />

      <div className="flex flex-col gap-3 px-4 pb-4 pt-3">
        <p className="text-[12px] leading-5 text-text-mute">
          Who produced this claim, on which commits, and with which instruments. Same
          claim always reads the same. Nothing is written.
        </p>

        {!threadId ? (
          <PanelEmpty>Select a thread, or open blame from a claim.</PanelEmpty>
        ) : claimsQuery.isLoading ? (
          <PanelLoading label="Loading claims" />
        ) : claimsQuery.isError ? (
          <PanelError label="Could not load claims" />
        ) : claims.length === 0 ? (
          <PanelEmpty>No claims in this thread. A blame needs a claim on the ledger.</PanelEmpty>
        ) : (
          <form
            className="grid gap-3 rounded-built bg-panel-2 p-3"
            style={{ border: "1px solid var(--hairline)" }}
            onSubmit={(event) => {
              event.preventDefault();
              if (!effectiveClaimId) return;
              setSubmittedClaimId(effectiveClaimId);
            }}
          >
            <label className="grid gap-1.5">
              <span className="text-[12px] text-text-mute">Claim</span>
              <Select
                aria-label="Blame claim"
                value={effectiveClaimId}
                onChange={(event) => setPickedClaimId(event.target.value)}
                mono={false}
              >
                {options.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </label>
            <Action type="submit" disabled={!effectiveClaimId}>
              Show the chain
            </Action>
          </form>
        )}

        {submittedClaimId ? <BlameResult query={blameQuery} /> : null}
      </div>
    </Bay>
  );
}

function BlameResult({
  query,
}: {
  query: {
    isLoading: boolean;
    isError: boolean;
    error: unknown;
    data: ClaimBlameRead | undefined;
  };
}) {
  if (query.isLoading) return <PanelLoading label="Reading blame" />;
  if (query.isError) {
    const message = query.error instanceof Error ? query.error.message : "";
    return <PanelError label={message || "Could not read blame for that claim"} />;
  }
  const blame = query.data;
  if (!blame) return null;

  return (
    <div className="grid gap-3">
      <p className="text-[12px] leading-5 text-text-mute">
        {blame.statement}
        <span className="ml-2 font-mono text-text-faint">
          {blame.current_signal} · {blame.current_grounding}
        </span>
      </p>
      {blame.empty ? (
        <PanelEmpty>
          No checkpoint has touched this claim yet. Opening a claim does not write the
          ledger.
        </PanelEmpty>
      ) : (
        <ol className="grid gap-2">
          {blame.chain.map((row) => (
            <BlameStepRow key={row.checkpoint_id} row={row} />
          ))}
        </ol>
      )}
    </div>
  );
}

function BlameStepRow({ row }: { row: ClaimBlameStep }) {
  const movement = blameMovementLine(row);
  const instruments = blameInstrumentLine(row);
  return (
    <li
      className="rounded-built bg-panel-2 p-3 pl-4"
      style={{ border: "1px solid var(--hairline)" }}
    >
      <p className="text-[14px] font-medium text-text">{row.summary}</p>
      <p className="mt-1 text-[13px] leading-5 text-text-soft">{blameAuthorLine(row)}</p>
      <p className="mt-1 font-mono text-[12px] text-text-mute">
        {row.roles.join(" · ") || "touched"}
        {row.agent_run ? ` · agent pass ${row.agent_run.role}` : ""}
      </p>
      {instruments ? (
        <p className="mt-1 font-mono text-[12px] text-text-soft">{instruments}</p>
      ) : null}
      {movement ? <p className="mt-1 text-[13px] leading-5 text-text-mute">{movement}</p> : null}
    </li>
  );
}
