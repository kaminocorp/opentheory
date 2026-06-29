"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import { type FormEvent, useState } from "react";

import { Action, Bay, Input, ReadoutLabel, Select, Textarea } from "@/components/console";
import { updateProject } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import type { Project, ProjectStatus } from "@/types/project";

// The rich-text editor is heavy (TipTap + ProseMirror); load it only when an owner/admin opens the
// edit form, client-side only. A plain box stands in while it loads.
const RichTextEditor = dynamic(
  () => import("./rich-text-editor").then((m) => m.RichTextEditor),
  {
    ssr: false,
    loading: () => (
      <div className="field-input min-h-32 w-full px-2.5 py-2 text-[13px] text-text-faint">
        Loading editor…
      </div>
    ),
  },
);

// The settable project statuses — the full backend ProjectStatus enum (draft/active/paused/
// archived). Kept explicit so the select can only ever offer values the backend accepts.
const STATUS_OPTIONS: ProjectStatus[] = ["draft", "active", "paused", "archived"];

type ProjectEditFormProps = {
  project: Project;
  onDone: () => void;
};

export function ProjectEditForm({ project, onDone }: ProjectEditFormProps) {
  const queryClient = useQueryClient();

  const [title, setTitle] = useState(project.title);
  const [question, setQuestion] = useState(project.question);
  const [description, setDescription] = useState(project.description ?? "");
  const [background, setBackground] = useState(project.background ?? "");
  const [status, setStatus] = useState<ProjectStatus>(
    STATUS_OPTIONS.includes(project.status) ? project.status : "draft",
  );

  const mutation = useMutation({
    mutationFn: () =>
      updateProject(project.id, {
        title: title.trim(),
        question: question.trim(),
        description: description.trim() || null,
        background: background.trim() || null,
        status,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.project(project.id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.overview(project.id) });
      onDone();
    },
  });

  const canSubmit = title.trim().length > 0 && question.trim().length > 0;

  return (
    <Bay
      as="form"
      density="narrative"
      className="grid gap-4"
      onSubmit={(event: FormEvent) => {
        event.preventDefault();
        if (canSubmit && !mutation.isPending) mutation.mutate();
      }}
    >
      <label className="grid gap-1.5">
        <ReadoutLabel>Title</ReadoutLabel>
        <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Project title" />
      </label>

      <label className="grid gap-1.5">
        <ReadoutLabel>Research question</ReadoutLabel>
        <Textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="The tightly-scoped research question"
          rows={2}
        />
      </label>

      <label className="grid gap-1.5">
        <ReadoutLabel>Description (optional)</ReadoutLabel>
        <Textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="A short public summary"
          rows={2}
        />
      </label>

      <div className="grid gap-1.5">
        <ReadoutLabel>Background / Context (optional)</ReadoutLabel>
        <RichTextEditor
          value={background}
          onChange={setBackground}
          placeholder="A deeper, long-form briefing on the research question…"
          ariaLabel="Background / Context"
        />
      </div>

      <label className="grid gap-1.5">
        <ReadoutLabel>Status</ReadoutLabel>
        <Select
          aria-label="Project status"
          value={status}
          onChange={(e) => setStatus(e.target.value as ProjectStatus)}
          className="capitalize"
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </Select>
      </label>

      {mutation.isError ? (
        <p className="text-[12px] text-state-fail">{(mutation.error as Error).message}</p>
      ) : null}

      <div className="flex items-center gap-2">
        <Action type="submit" disabled={!canSubmit || mutation.isPending} pending={mutation.isPending}>
          {mutation.isPending ? "Saving…" : "Save changes"}
        </Action>
        <Action variant="ghost" onClick={onDone} disabled={mutation.isPending}>
          Cancel
        </Action>
      </div>
    </Bay>
  );
}
