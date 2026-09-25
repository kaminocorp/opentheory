"use client";

import { useQuery } from "@tanstack/react-query";
import { GitCompare } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import { Action, Bay, BayHeader, Icon, Select } from "@/components/console";
import { getSemanticDiff, listBranches, listCheckpoints, listTags } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import type {
  ClaimDelta,
  ClaimDiffChange,
  GroundingMove,
  InstrumentOutcome,
  SemanticDiffRead,
} from "@/types/research";

import { PanelEmpty, PanelError, PanelLoading } from "./panel-state";

const CHANGE_LABEL: Record<ClaimDiffChange, string> = {
  added: "opened",
  removed: "left this line",
  status_changed: "signal moved",
};

type ComparePanelProps = {
  projectId: string;
  selectedBranchId: string | null;
};

type RefOption = {
  value: string;
  label: string;
};

function optionLabel(kind: string, name: string): string {
  return `${kind} · ${name}`;
}

export function ComparePanel({ projectId, selectedBranchId }: ComparePanelProps) {
  const checkpointsQuery = useQuery({
    queryKey: queryKeys.checkpoints(projectId),
    queryFn: () => listCheckpoints(projectId),
  });
  const branchesQuery = useQuery({
    queryKey: queryKeys.branches(projectId),
    queryFn: () => listBranches(projectId),
  });
  const tagsQuery = useQuery({
    queryKey: queryKeys.tags(projectId),
    queryFn: () => listTags(projectId),
  });

  const checkpoints = checkpointsQuery.data ?? [];
  const branches = branchesQuery.data ?? [];
  const tags = tagsQuery.data ?? [];

  const options = useMemo<RefOption[]>(() => {
    const rows: RefOption[] = [{ value: "main", label: optionLabel("main", "tip") }];
    for (const branch of branches) {
      rows.push({ value: branch.id, label: optionLabel("line", branch.name) });
    }
    for (const tag of tags) {
      rows.push({ value: tag.name, label: optionLabel("tag", tag.name) });
    }
    for (const checkpoint of checkpoints) {
      const summary = checkpoint.summary.slice(0, 48);
      rows.push({
        value: checkpoint.id,
        label: optionLabel("commit", summary || checkpoint.id.slice(0, 8)),
      });
    }
    return rows;
  }, [branches, tags, checkpoints]);

  const defaultTo = selectedBranchId ?? "main";
  const defaultFrom = useMemo(() => {
    if (selectedBranchId) {
      const onLine = checkpoints.filter((c) => c.branch_id === selectedBranchId);
      const tip = onLine[0];
      const parent = tip?.parent_ids[0];
      return parent ?? "main";
    }
    const mainLine = checkpoints.filter((c) => c.branch_id == null);
    if (mainLine.length >= 2) return mainLine[1].id;
    if (mainLine.length === 1) return mainLine[0].id;
    return "main";
  }, [checkpoints, selectedBranchId]);

  const [fromRef, setFromRef] = useState("");
  const [toRef, setToRef] = useState("");
  const [submittedFrom, setSubmittedFrom] = useState<string | null>(null);
  const [submittedTo, setSubmittedTo] = useState<string | null>(null);

  const effectiveFrom = fromRef || defaultFrom;
  const effectiveTo = toRef || defaultTo;

  const diffQuery = useQuery({
    queryKey: queryKeys.semanticDiff(projectId, submittedFrom ?? "", submittedTo ?? ""),
    queryFn: () => getSemanticDiff(projectId, submittedFrom!, submittedTo!),
    enabled: Boolean(submittedFrom && submittedTo),
  });

  const canCompare = Boolean(effectiveFrom && effectiveTo);

  return (
    <Bay density="none" className="flex flex-col">
      <BayHeader
        label={
          <span className="inline-flex items-center gap-1.5">
            <Icon icon={GitCompare} size={14} />
            Compare
          </span>
        }
        divider
      />

      <div className="flex flex-col gap-3 px-4 pb-4 pt-3">
        <p className="text-[12px] leading-5 text-text-mute">
          What moved between two tips — claims, grounding, instrument results. Same tips
          always read the same. Nothing is written.
        </p>

        {checkpointsQuery.isLoading ? (
          <PanelLoading label="Loading tips" />
        ) : checkpointsQuery.isError ? (
          <PanelError label="Could not load checkpoints" />
        ) : checkpoints.length === 0 ? (
          <PanelEmpty>No checkpoints yet. A compare needs two tips on the ledger.</PanelEmpty>
        ) : (
          <form
            className="grid gap-3 rounded-built bg-panel-2 p-3"
            style={{ border: "1px solid var(--hairline)" }}
            onSubmit={(event) => {
              event.preventDefault();
              if (!canCompare) return;
              setSubmittedFrom(effectiveFrom);
              setSubmittedTo(effectiveTo);
            }}
          >
            <label className="grid gap-1.5">
              <span className="text-[12px] text-text-mute">From</span>
              <Select
                aria-label="Compare from tip"
                value={effectiveFrom}
                onChange={(event) => setFromRef(event.target.value)}
                mono={false}
              >
                {options.map((option) => (
                  <option key={`from-${option.value}`} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </label>
            <label className="grid gap-1.5">
              <span className="text-[12px] text-text-mute">To</span>
              <Select
                aria-label="Compare to tip"
                value={effectiveTo}
                onChange={(event) => setToRef(event.target.value)}
                mono={false}
              >
                {options.map((option) => (
                  <option key={`to-${option.value}`} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </label>
            <Action type="submit" disabled={!canCompare}>
              Show what moved
            </Action>
          </form>
        )}

        {submittedFrom && submittedTo ? <DiffResult query={diffQuery} /> : null}
      </div>
    </Bay>
  );
}

function DiffResult({
  query,
}: {
  query: {
    isLoading: boolean;
    isError: boolean;
    error: unknown;
    data: SemanticDiffRead | undefined;
  };
}) {
  if (query.isLoading) return <PanelLoading label="Comparing tips" />;
  if (query.isError) {
    const message = query.error instanceof Error ? query.error.message : "";
    return <PanelError label={message || "Could not compare those tips"} />;
  }
  const diff = query.data;
  if (!diff) return null;

  return (
    <div className="grid gap-3">
      <AncestryLine diff={diff} />
      {diff.empty ? (
        <PanelEmpty>Nothing moved between these tips.</PanelEmpty>
      ) : (
        <>
          <DeltaList
            title="Claims"
            empty="No claim presence or signal change."
            items={diff.claims}
            render={(row) => <ClaimRow key={row.claim_id} row={row} />}
          />
          <DeltaList
            title="Grounding"
            empty="No evidence-axis move."
            items={diff.grounding}
            render={(row) => <GroundingRow key={row.claim_id} row={row} />}
          />
          <DeltaList
            title="Instruments"
            empty="No instrument result on the interval."
            items={diff.instruments}
            render={(row, index) => <InstrumentRow key={`${row.checkpoint_id}-${index}`} row={row} />}
          />
        </>
      )}
    </div>
  );
}

function AncestryLine({ diff }: { diff: SemanticDiffRead }) {
  const { ancestry, from_ref: fromRef, to_ref: toRef } = diff;
  let copy = `${fromRef.label} → ${toRef.label}`;
  if (fromRef.checkpoint_id === toRef.checkpoint_id) {
    copy = "Same tip.";
  } else if (ancestry.diverged) {
    copy = ancestry.merge_base_id
      ? `Diverged lines; last common commit ${ancestry.merge_base_id.slice(0, 8)}.`
      : "Diverged lines with no common ancestor.";
  } else if (ancestry.from_is_ancestor_of_to) {
    const n = ancestry.interval_checkpoint_ids.length;
    copy = `${n} commit${n === 1 ? "" : "s"} on this line.`;
  }
  return <p className="text-[12px] leading-5 text-text-mute">{copy}</p>;
}

function DeltaList<T>({
  title,
  empty,
  items,
  render,
}: {
  title: string;
  empty: string;
  items: T[];
  render: (item: T, index: number) => ReactNode;
}) {
  return (
    <section className="grid gap-2">
      <h3 className="text-[12px] font-medium text-text-soft">{title}</h3>
      {items.length === 0 ? (
        <p className="text-[13px] leading-5 text-text-mute">{empty}</p>
      ) : (
        <ol className="grid gap-2">{items.map((item, index) => render(item, index))}</ol>
      )}
    </section>
  );
}

function ClaimRow({ row }: { row: ClaimDelta }) {
  return (
    <li
      className="rounded-built bg-panel-2 p-3 pl-4"
      style={{ border: "1px solid var(--hairline)" }}
    >
      <p className="text-[14px] font-medium text-text">{row.statement}</p>
      <p className="mt-1 text-[13px] leading-5 text-text-soft">
        {CHANGE_LABEL[row.change]}
        {row.change === "status_changed"
          ? ` · ${row.from_signal ?? "—"} → ${row.to_signal ?? "—"}`
          : null}
      </p>
    </li>
  );
}

function GroundingRow({ row }: { row: GroundingMove }) {
  return (
    <li
      className="rounded-built bg-panel-2 p-3 pl-4"
      style={{ border: "1px solid var(--hairline)" }}
    >
      <p className="text-[14px] font-medium text-text">{row.statement}</p>
      <p className="mt-1 font-mono text-[12px] text-text-soft">
        {row.from_headline} → {row.to_headline}
        <span className="ml-2 font-sans text-text-mute">{row.movement}</span>
      </p>
    </li>
  );
}

function InstrumentRow({ row }: { row: InstrumentOutcome }) {
  return (
    <li
      className="rounded-built bg-panel-2 p-3 pl-4"
      style={{ border: "1px solid var(--hairline)" }}
    >
      <p className="font-mono text-[13px] text-text">
        {row.instrument}
        <span className="ml-2 text-text-soft">{row.status}</span>
      </p>
      <p className="mt-1 text-[13px] leading-5 text-text-mute">{row.summary}</p>
    </li>
  );
}
