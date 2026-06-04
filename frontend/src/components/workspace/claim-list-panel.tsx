"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ListChecks, Paperclip, Plus, X } from "lucide-react";
import { useState } from "react";

import { attachEvidence, createClaim, listClaims, listEvidence } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useDevActor } from "@/providers/dev-actor-provider";
import type { ClaimKind, RelationKind } from "@/types/research";

import { PanelEmpty, PanelError, PanelLoading } from "./panel-state";

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

type ClaimListPanelProps = {
  projectId: string;
  threadId: string | null;
};

export function ClaimListPanel({ projectId, threadId }: ClaimListPanelProps) {
  if (!threadId) {
    return (
      <section className="grid min-h-64 place-items-center rounded-lg border border-line bg-white/70 p-6 shadow-panel">
        <PanelEmpty icon={<ListChecks className="size-5" aria-hidden="true" />}>
          Select a thread on the left to view and record its claims and evidence.
        </PanelEmpty>
      </section>
    );
  }
  return <ClaimListPanelInner projectId={projectId} threadId={threadId} />;
}

function ClaimListPanelInner({ projectId, threadId }: { projectId: string; threadId: string }) {
  const { actorId, hydrated } = useDevActor();
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [kind, setKind] = useState<ClaimKind>("hypothesis");
  const [statement, setStatement] = useState("");

  const claimsQuery = useQuery({
    queryKey: queryKeys.claims(threadId),
    queryFn: () => listClaims(threadId),
  });

  const createMutation = useMutation({
    mutationFn: (actor: string) => createClaim(threadId, { kind, statement: statement.trim() }, actor),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.claims(threadId) });
      // the thread list shows a claim count, and the header shows aggregate counts
      queryClient.invalidateQueries({ queryKey: queryKeys.threads(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.overview(projectId) });
      setStatement("");
      setAdding(false);
    },
  });

  const canSubmit = Boolean(actorId) && statement.trim().length > 0;

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-line bg-white/70 p-4 shadow-panel">
      <header className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.1em] text-ink/70">
          <ListChecks className="size-4 text-signal" aria-hidden="true" />
          Claims &amp; Evidence
        </h2>
        <button
          type="button"
          onClick={() => setAdding((v) => !v)}
          className="grid size-7 place-items-center rounded-md border border-line text-ink/65 hover:text-ink"
          aria-label={adding ? "Cancel new claim" : "New claim"}
          title={adding ? "Cancel" : "New claim"}
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
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value as ClaimKind)}
            className="h-9 rounded-md border border-line bg-white/80 px-2 text-sm capitalize outline-none focus:border-signal"
          >
            {CLAIM_KINDS.map((k) => (
              <option key={k} value={k} className="capitalize">
                {k}
              </option>
            ))}
          </select>
          <input
            value={statement}
            onChange={(event) => setStatement(event.target.value)}
            placeholder="Claim statement"
            className="h-9 rounded-md border border-line bg-white/80 px-2 text-sm outline-none focus:border-signal"
          />
          {!actorId && hydrated ? (
            <p className="text-xs text-ember">Select an actor (top right) to record claims.</p>
          ) : null}
          {createMutation.isError ? (
            <p className="text-xs text-ember">{(createMutation.error as Error).message}</p>
          ) : null}
          <button
            type="submit"
            disabled={!canSubmit || createMutation.isPending}
            className="inline-flex h-9 items-center justify-center gap-1 rounded-md bg-ink px-3 text-sm font-semibold text-paper disabled:opacity-50"
          >
            {createMutation.isPending ? "Recording…" : "Record claim"}
          </button>
        </form>
      ) : null}

      {claimsQuery.isLoading ? (
        <PanelLoading label="Loading claims" />
      ) : claimsQuery.isError ? (
        <PanelError label="Could not load claims." />
      ) : (claimsQuery.data ?? []).length === 0 ? (
        <PanelEmpty icon={<ListChecks className="size-5" aria-hidden="true" />}>
          No claims in this thread yet. Record a hypothesis or observation.
        </PanelEmpty>
      ) : (
        <ul className="grid gap-3">
          {(claimsQuery.data ?? []).map((claim) => (
            <li key={claim.id} className="rounded-md border border-line bg-white/60 p-3">
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm leading-6">{claim.statement}</p>
                {claim.confidence != null ? (
                  <span className="shrink-0 rounded bg-paper px-2 py-0.5 text-xs font-semibold text-ink/60">
                    {Math.round(claim.confidence * 100)}%
                  </span>
                ) : null}
              </div>
              <p className="mt-1.5 text-[11px] font-medium uppercase tracking-[0.1em] text-ink/45">
                {claim.kind} · {claim.status}
              </p>
              <ClaimEvidence projectId={projectId} claimId={claim.id} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ClaimEvidence({ projectId, claimId }: { projectId: string; claimId: string }) {
  const { actorId, hydrated } = useDevActor();
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
    mutationFn: (actor: string) =>
      attachEvidence(
        claimId,
        {
          title: title.trim(),
          source_type: sourceType.trim() || "note",
          uri: uri.trim() || null,
          relation_kind: relationKind,
        },
        actor,
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.evidence(claimId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.overview(projectId) });
      setTitle("");
      setUri("");
      setAdding(false);
    },
  });

  const canSubmit = Boolean(actorId) && title.trim().length > 0;
  const evidence = evidenceQuery.data ?? [];

  return (
    <div className="mt-3 border-t border-line pt-3">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.1em] text-ink/50">
          <Paperclip className="size-3.5 text-signal" aria-hidden="true" />
          Evidence
        </span>
        <button
          type="button"
          onClick={() => setAdding((v) => !v)}
          className="text-xs font-medium text-signal hover:text-ink"
        >
          {adding ? "Cancel" : "Attach"}
        </button>
      </div>

      {evidenceQuery.isLoading ? (
        <p className="mt-2 text-xs text-ink/50">Loading evidence…</p>
      ) : evidenceQuery.isError ? (
        <p className="mt-2 text-xs text-ember">Could not load evidence.</p>
      ) : evidence.length === 0 ? (
        <p className="mt-2 text-xs text-ink/45">No evidence attached.</p>
      ) : (
        <ul className="mt-2 grid gap-1.5">
          {evidence.map((item) => (
            <li key={item.link_id} className="flex items-center justify-between gap-2 text-xs">
              <span className="min-w-0 truncate">
                {item.uri ? (
                  <a href={item.uri} target="_blank" rel="noreferrer" className="text-signal hover:underline">
                    {item.title}
                  </a>
                ) : (
                  item.title
                )}
                <span className="ml-1 text-ink/40">· {item.source_type}</span>
              </span>
              <span
                className={`shrink-0 rounded px-1.5 py-0.5 font-semibold ${
                  item.relation_kind === "support"
                    ? "bg-signal/10 text-signal"
                    : item.relation_kind === "weaken"
                      ? "bg-ember/10 text-ember"
                      : "bg-paper text-ink/55"
                }`}
              >
                {item.relation_kind}
              </span>
            </li>
          ))}
        </ul>
      )}

      {adding ? (
        <form
          className="mt-2 grid gap-2 rounded-md border border-line bg-paper/60 p-2.5"
          onSubmit={(event) => {
            event.preventDefault();
            if (canSubmit && !attachMutation.isPending) attachMutation.mutate(actorId!);
          }}
        >
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Evidence title"
            className="h-8 rounded border border-line bg-white/80 px-2 text-xs outline-none focus:border-signal"
          />
          <div className="flex gap-2">
            <input
              value={sourceType}
              onChange={(event) => setSourceType(event.target.value)}
              placeholder="source (e.g. paper)"
              className="h-8 min-w-0 flex-1 rounded border border-line bg-white/80 px-2 text-xs outline-none focus:border-signal"
            />
            <select
              value={relationKind}
              onChange={(event) => setRelationKind(event.target.value as RelationKind)}
              className="h-8 rounded border border-line bg-white/80 px-1 text-xs capitalize outline-none focus:border-signal"
            >
              {RELATION_KINDS.map((r) => (
                <option key={r} value={r} className="capitalize">
                  {r}
                </option>
              ))}
            </select>
          </div>
          <input
            value={uri}
            onChange={(event) => setUri(event.target.value)}
            placeholder="URI (optional)"
            className="h-8 rounded border border-line bg-white/80 px-2 text-xs outline-none focus:border-signal"
          />
          {!actorId && hydrated ? (
            <p className="text-[11px] text-ember">Select an actor to attach evidence.</p>
          ) : null}
          {attachMutation.isError ? (
            <p className="text-[11px] text-ember">{(attachMutation.error as Error).message}</p>
          ) : null}
          <button
            type="submit"
            disabled={!canSubmit || attachMutation.isPending}
            className="inline-flex h-8 items-center justify-center rounded bg-ink px-2.5 text-xs font-semibold text-paper disabled:opacity-50"
          >
            {attachMutation.isPending ? "Attaching…" : "Attach evidence"}
          </button>
        </form>
      ) : null}
    </div>
  );
}
