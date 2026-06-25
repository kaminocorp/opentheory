"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ListChecks, Paperclip, Plus, ShieldCheck, X } from "lucide-react";
import { useState } from "react";

import {
  Action,
  Bay,
  BayHeader,
  Icon,
  Input,
  ReadoutLabel,
  Select,
  StatusPill,
  type StateTone,
} from "@/components/console";
import { attachEvidence, createClaim, listClaims, listEvidence } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useActingIdentity } from "@/lib/use-identity";
import type { Claim, ClaimKind, RelationKind } from "@/types/research";

import { PanelEmpty, PanelError, PanelLoading } from "./panel-state";
import { OutcomeBadge, RecordValidationForm } from "./validation-controls";

const CLAIM_KINDS: ClaimKind[] = [
  "hypothesis",
  "assumption",
  "constraint",
  "observation",
  "objection",
  "result",
  "retraction",
];

const RELATION_KINDS: RelationKind[] = ["support", "weaken", "context"];

// Evidence relation → a state tone. support strengthens (ok), weaken contests
// (fail), context is neutral (mute). Glyph + label carry it under grayscale.
const RELATION_TONE: Record<RelationKind, StateTone> = {
  support: "ok",
  weaken: "fail",
  context: "mute",
};

type ClaimListPanelProps = {
  projectId: string;
  threadId: string | null;
};

export function ClaimListPanel({ projectId, threadId }: ClaimListPanelProps) {
  if (!threadId) {
    return (
      <Bay density="none" className="grid min-h-64 place-items-center">
        <PanelEmpty>Select a thread</PanelEmpty>
      </Bay>
    );
  }
  return <ClaimListPanelInner projectId={projectId} threadId={threadId} />;
}

function ClaimListPanelInner({ projectId, threadId }: { projectId: string; threadId: string }) {
  const { canWrite, hydrated, signInHint } = useActingIdentity();
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [kind, setKind] = useState<ClaimKind>("hypothesis");
  const [statement, setStatement] = useState("");

  const claimsQuery = useQuery({
    queryKey: queryKeys.claims(threadId),
    queryFn: () => listClaims(threadId),
  });

  const createMutation = useMutation({
    mutationFn: () => createClaim(threadId, { kind, statement: statement.trim() }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.claims(threadId) });
      // the thread list shows a claim count, and the header shows aggregate counts
      queryClient.invalidateQueries({ queryKey: queryKeys.threads(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.overview(projectId) });
      setStatement("");
      setAdding(false);
    },
  });

  const claims = claimsQuery.data ?? [];
  const canSubmit = canWrite && statement.trim().length > 0;

  return (
    <Bay density="none" className="flex flex-col">
      <BayHeader
        label={
          <span className="inline-flex items-center gap-1.5">
            <Icon icon={ListChecks} size={14} />
            Claims &amp; Evidence
          </span>
        }
        count={claimsQuery.data ? claims.length : undefined}
        band
        actions={
          <button
            type="button"
            onClick={() => setAdding((v) => !v)}
            className="grid size-7 place-items-center rounded-full text-text-mute transition-colors hover:text-text"
            style={{ border: "0.5px solid var(--hairline-strong)" }}
            aria-label={adding ? "Cancel new claim" : "New claim"}
            title={adding ? "Cancel" : "New claim"}
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
            <Select
              value={kind}
              onChange={(event) => setKind(event.target.value as ClaimKind)}
              className="capitalize"
            >
              {CLAIM_KINDS.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </Select>
            <Input
              value={statement}
              onChange={(event) => setStatement(event.target.value)}
              placeholder="Claim statement"
            />
            {!canWrite && hydrated ? (
              <p className="text-[11px] text-state-warn">{signInHint} to record claims.</p>
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
              {createMutation.isPending ? "Recording…" : "Record claim"}
            </Action>
          </form>
        ) : null}

        {claimsQuery.isLoading ? (
          <PanelLoading label="Loading claims" />
        ) : claimsQuery.isError ? (
          <PanelError label="Could not load claims" />
        ) : claims.length === 0 ? (
          <PanelEmpty>No claims in this thread</PanelEmpty>
        ) : (
          <ul className="grid gap-3">
            {claims.map((claim) => (
              // Square claim sub-bay on --panel-2 (raised out of the panel column).
              <li
                key={claim.id}
                className="rounded-built bg-panel-2 p-3"
                style={{ border: "0.5px solid var(--hairline)" }}
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="text-[14px] leading-6 text-text">{claim.statement}</p>
                  {claim.confidence != null ? (
                    <span
                      className="shrink-0 rounded-inset bg-panel px-2 py-0.5 font-mono text-[12px] tabular-nums text-text-soft"
                      style={{ border: "0.5px solid var(--hairline)" }}
                    >
                      {Math.round(claim.confidence * 100)}%
                    </span>
                  ) : null}
                </div>
                <p className="mt-1.5 font-mono text-[11px] uppercase tracking-[0.1em] text-text-mute">
                  {claim.kind} · {claim.status}
                </p>
                <ClaimEvidence projectId={projectId} claimId={claim.id} />
                <ClaimValidations projectId={projectId} threadId={threadId} claim={claim} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </Bay>
  );
}

function ClaimEvidence({ projectId, claimId }: { projectId: string; claimId: string }) {
  const { canWrite, hydrated, signInHint } = useActingIdentity();
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState("");
  const [sourceType, setSourceType] = useState("note");
  const [uri, setUri] = useState("");
  const [relationKind, setRelationKind] = useState<RelationKind>("support");

  const evidenceQuery = useQuery({
    queryKey: queryKeys.evidence(claimId),
    queryFn: () => listEvidence(claimId),
  });

  const attachMutation = useMutation({
    mutationFn: () =>
      attachEvidence(claimId, {
        title: title.trim(),
        source_type: sourceType.trim() || "note",
        uri: uri.trim() || null,
        relation_kind: relationKind,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.evidence(claimId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.overview(projectId) });
      setTitle("");
      setUri("");
      setAdding(false);
    },
  });

  const canSubmit = canWrite && title.trim().length > 0;
  const evidence = evidenceQuery.data ?? [];

  return (
    <div className="mt-3 pt-3" style={{ borderTop: "0.5px solid var(--hairline)" }}>
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-text-mute">
          <Icon icon={Paperclip} size={14} />
          <ReadoutLabel>Evidence</ReadoutLabel>
        </span>
        <button
          type="button"
          onClick={() => setAdding((v) => !v)}
          className="text-[12px] font-medium text-text-mute transition-colors hover:text-signal"
        >
          {adding ? "Cancel" : "Attach"}
        </button>
      </div>

      {evidenceQuery.isLoading ? (
        <p className="mt-2 text-[12px] text-text-mute">Loading evidence…</p>
      ) : evidenceQuery.isError ? (
        <p className="mt-2 text-[12px] text-state-fail">Could not load evidence.</p>
      ) : evidence.length === 0 ? (
        <p className="mt-2 text-[12px] text-text-faint">No evidence attached.</p>
      ) : (
        <ul className="mt-2 grid gap-1.5">
          {evidence.map((item) => (
            <li key={item.link_id} className="flex items-center justify-between gap-2 text-[12px]">
              <span className="min-w-0 truncate">
                {item.uri ? (
                  <a href={item.uri} target="_blank" rel="noreferrer" className="console-link">
                    {item.title}
                  </a>
                ) : (
                  <span className="text-text-soft">{item.title}</span>
                )}
                <span className="ml-1.5 font-mono text-text-mute">· {item.source_type}</span>
              </span>
              <StatusPill
                tone={RELATION_TONE[item.relation_kind]}
                label={item.relation_kind}
                className="shrink-0"
              />
            </li>
          ))}
        </ul>
      )}

      {adding ? (
        <form
          className="mt-2 grid gap-2 rounded-built bg-panel-2 p-2.5"
          style={{ border: "0.5px solid var(--hairline)" }}
          onSubmit={(event) => {
            event.preventDefault();
            if (canSubmit && !attachMutation.isPending) attachMutation.mutate();
          }}
        >
          <Input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Evidence title"
          />
          <div className="flex gap-2">
            <Input
              value={sourceType}
              onChange={(event) => setSourceType(event.target.value)}
              placeholder="source (e.g. paper)"
              className="min-w-0 flex-1"
            />
            <Select
              value={relationKind}
              onChange={(event) => setRelationKind(event.target.value as RelationKind)}
              className="capitalize"
            >
              {RELATION_KINDS.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </Select>
          </div>
          <Input
            mono
            value={uri}
            onChange={(event) => setUri(event.target.value)}
            placeholder="URI (optional)"
          />
          {!canWrite && hydrated ? (
            <p className="text-[11px] text-state-warn">{signInHint} to attach evidence.</p>
          ) : null}
          {attachMutation.isError ? (
            <p className="text-[11px] text-state-fail">{(attachMutation.error as Error).message}</p>
          ) : null}
          <Action
            type="submit"
            disabled={!canSubmit || attachMutation.isPending}
            pending={attachMutation.isPending}
            className="w-full"
          >
            <Icon icon={Plus} size={16} />
            {attachMutation.isPending ? "Attaching…" : "Attach evidence"}
          </Action>
        </form>
      ) : null}
    </div>
  );
}

function ClaimValidations({
  projectId,
  threadId,
  claim,
}: {
  projectId: string;
  threadId: string;
  claim: Claim;
}) {
  const [recording, setRecording] = useState(false);

  // History and signal are embedded in the claim read (0.4.4) — no separate fetch. The
  // contradiction indicator uses the server-derived signal.
  const validations = claim.validations;
  const contested = claim.signal === "contested";

  return (
    <div className="mt-3 pt-3" style={{ borderTop: "0.5px solid var(--hairline)" }}>
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1.5 text-text-mute">
          <Icon icon={ShieldCheck} size={14} />
          <ReadoutLabel>Validations</ReadoutLabel>
          {/* Honesty (§1): contested shows at full pill weight, never softer than
              validated — glyph + label carry it, colour only reinforces. */}
          {contested ? (
            <StatusPill tone="fail" glyph="▲" label="contested" />
          ) : claim.signal === "validated" ? (
            <StatusPill tone="ok" label="validated" />
          ) : null}
        </span>
        <button
          type="button"
          onClick={() => setRecording((v) => !v)}
          className="shrink-0 text-[12px] font-medium text-text-mute transition-colors hover:text-signal"
        >
          {recording ? "Cancel" : "Validate"}
        </button>
      </div>

      {validations.length === 0 ? (
        <p className="mt-2 text-[12px] text-text-faint">Not yet validated.</p>
      ) : (
        <ul className="mt-2 grid gap-1.5">
          {validations.map((v) => (
            <li key={v.id} className="flex items-center gap-2 text-[12px]">
              <OutcomeBadge outcome={v.outcome} />
              {v.notes ? (
                <span className="min-w-0 flex-1 truncate text-text-soft">{v.notes}</span>
              ) : (
                <span className="flex-1" />
              )}
              {v.actor ? <span className="shrink-0 text-text-mute">{v.actor.display_name}</span> : null}
            </li>
          ))}
        </ul>
      )}

      {recording ? (
        <RecordValidationForm
          projectId={projectId}
          targetType="claim"
          targetId={claim.id}
          invalidateKey={queryKeys.claims(threadId)}
          onDone={() => setRecording(false)}
          compact
        />
      ) : null}
    </div>
  );
}
