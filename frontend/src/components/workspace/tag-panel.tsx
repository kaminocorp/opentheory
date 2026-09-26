"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Tag, X } from "lucide-react";
import { useState } from "react";

import { Action, Bay, BayHeader, Icon, Input, Select } from "@/components/console";
import { createTag, listCheckpoints, listTags } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useProjectWriteAccess } from "@/lib/use-project-write-access";
import type { TagKind } from "@/types/research";

import { PanelEmpty, PanelError, PanelLoading } from "./panel-state";

const KIND_LABEL: Record<TagKind, string> = {
  milestone: "milestone",
  validated: "validated",
  retraction: "retraction",
};

type TagPanelProps = {
  projectId: string;
};

export function TagPanel({ projectId }: TagPanelProps) {
  const { canWrite } = useProjectWriteAccess(projectId);
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);

  const tagsQuery = useQuery({
    queryKey: queryKeys.tags(projectId),
    queryFn: () => listTags(projectId),
  });
  const tags = tagsQuery.data ?? [];

  function invalidateAfterTagWrite() {
    queryClient.invalidateQueries({ queryKey: queryKeys.tags(projectId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.checkpoints(projectId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.overview(projectId) });
  }

  return (
    <Bay density="none" className="flex flex-col">
      <BayHeader
        label={
          <span className="inline-flex items-center gap-1.5">
            <Icon icon={Tag} size={14} />
            Tags
          </span>
        }
        count={tagsQuery.data ? tags.length : undefined}
        divider
        actions={
          canWrite ? (
            <button
              type="button"
              onClick={() => setAdding((v) => !v)}
              className="grid size-7 place-items-center rounded-full text-text-mute transition-colors hover:text-text"
              style={{ border: "1px solid var(--hairline-strong)" }}
              aria-label={adding ? "Cancel new tag" : "New tag"}
              title={adding ? "Cancel" : "New tag"}
            >
              <Icon icon={adding ? X : Plus} size={14} />
            </button>
          ) : undefined
        }
      />

      <div className="flex flex-col gap-3 px-4 pb-4 pt-3">
        {adding && canWrite ? (
          <CreateTagForm
            projectId={projectId}
            onCreated={() => {
              invalidateAfterTagWrite();
              setAdding(false);
            }}
          />
        ) : null}

        {tagsQuery.isLoading ? (
          <PanelLoading label="Loading tags" />
        ) : tagsQuery.isError ? (
          <PanelError label="Could not load tags" />
        ) : tags.length === 0 ? (
          <PanelEmpty>No tags yet. Pin a named milestone, validated result, or retraction.</PanelEmpty>
        ) : (
          <ol className="grid gap-2">
            {tags.map((tag) => (
              <li
                key={tag.id}
                className="rounded-built bg-panel-2 p-3"
                style={{ border: "1px solid var(--hairline)" }}
              >
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <span className="text-[14px] font-medium text-text">{tag.name}</span>
                  <span
                    className="rounded-full bg-panel px-2 py-0.5 text-[11px] capitalize text-text-mute"
                    style={{ border: "1px solid var(--hairline)" }}
                  >
                    {KIND_LABEL[tag.kind]}
                  </span>
                </div>
                {tag.notes ? (
                  <p className="mt-1 text-[13px] leading-5 text-text-soft">{tag.notes}</p>
                ) : null}
                <p className="mt-2 font-mono text-[11px] tabular-nums text-text-faint">
                  → {tag.checkpoint_id.slice(0, 8)}
                  {tag.author ? ` · ${tag.author.display_name}` : ""}
                </p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </Bay>
  );
}

function CreateTagForm({
  projectId,
  onCreated,
}: {
  projectId: string;
  onCreated: () => void;
}) {
  const { canWrite } = useProjectWriteAccess(projectId);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<TagKind>("milestone");
  const [notes, setNotes] = useState("");
  const [checkpointId, setCheckpointId] = useState("");

  const checkpointsQuery = useQuery({
    queryKey: queryKeys.checkpoints(projectId),
    queryFn: () => listCheckpoints(projectId),
  });
  const checkpoints = checkpointsQuery.data ?? [];

  const mutation = useMutation({
    mutationFn: () =>
      createTag(projectId, {
        checkpoint_id: checkpointId || checkpoints[0]?.id,
        name: name.trim(),
        kind,
        notes: notes.trim() || null,
      }),
    onSuccess: () => {
      setName("");
      setNotes("");
      onCreated();
    },
  });

  const effectiveCheckpoint = checkpointId || checkpoints[0]?.id || "";
  const canSubmit = canWrite && name.trim().length > 0 && Boolean(effectiveCheckpoint);

  if (!checkpointsQuery.isLoading && checkpoints.length === 0) {
    return (
      <p
        className="rounded-built bg-panel-2 p-2.5 text-[12px] text-text-mute"
        style={{ border: "1px dashed var(--hairline)" }}
      >
        Record a checkpoint first — a tag points at an existing commit.
      </p>
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
      <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Tag name" />
      <Select
        aria-label="Tag kind"
        value={kind}
        onChange={(event) => setKind(event.target.value as TagKind)}
      >
        <option value="milestone">milestone</option>
        <option value="validated">validated result</option>
        <option value="retraction">retraction</option>
      </Select>
      <Select
        aria-label="Tag checkpoint"
        value={effectiveCheckpoint}
        onChange={(event) => setCheckpointId(event.target.value)}
      >
        {checkpoints.map((checkpoint) => (
          <option key={checkpoint.id} value={checkpoint.id}>
            {checkpoint.summary.slice(0, 48)}
          </option>
        ))}
      </Select>
      <Input
        value={notes}
        onChange={(event) => setNotes(event.target.value)}
        placeholder="Notes (optional)"
      />
      {mutation.isError ? (
        <p className="text-[12px] text-state-fail">{(mutation.error as Error).message}</p>
      ) : null}
      <Action
        type="submit"
        disabled={!canSubmit || mutation.isPending}
        pending={mutation.isPending}
        className="w-full"
      >
        <Icon icon={Plus} size={16} />
        {mutation.isPending ? "Pinning…" : "Pin tag"}
      </Action>
    </form>
  );
}
