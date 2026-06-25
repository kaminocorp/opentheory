"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { Action, ActionGhost, Bay, Icon, Input, ReadoutLabel, Textarea } from "@/components/console";
import { createProject } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useActingIdentity } from "@/lib/use-identity";

import { ProjectList } from "./project-list";

// Derive a backend-valid slug (^[a-z0-9]+(?:-[a-z0-9]+)*$) from the title so the user never
// has to know the pattern exists; the field stays editable for collisions (slug is unique).
function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

const SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

// D3 re-skin: console tokens + primitives only. Every hook, state, the slug logic,
// the create mutation, and the write-gating below are unchanged — presentation, not behaviour.
export function ProjectsSection() {
  const { canWrite, hydrated, signInHint } = useActingIdentity();
  const queryClient = useQueryClient();
  const router = useRouter();

  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [question, setQuestion] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);

  // The slug auto-tracks the title until the user edits it directly.
  const effectiveSlug = slugEdited ? slug : slugify(title);

  const createMutation = useMutation({
    // The acting actor rides on the request (bearer token / dev header), resolved server-side.
    mutationFn: () =>
      createProject({
        title: title.trim(),
        slug: effectiveSlug,
        question: question.trim(),
      }),
    onSuccess: (project) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.projects });
      router.push(`/projects/${project.id}`);
    },
  });

  const canSubmit =
    canWrite &&
    title.trim().length > 0 &&
    question.trim().length > 0 &&
    SLUG_PATTERN.test(effectiveSlug);

  return (
    <section className="grid gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-medium text-text">Projects</h2>
          <p className="mt-1 text-[13px] text-text-soft">
            Live research surfaces backed by the FastAPI ledger.
          </p>
        </div>
        <ActionGhost onClick={() => setOpen((v) => !v)}>
          <Icon icon={open ? X : Plus} size={16} />
          {open ? "Cancel" : "New project"}
        </ActionGhost>
      </div>

      {open ? (
        <Bay
          as="form"
          density="narrative"
          className="grid gap-3"
          onSubmit={(event: FormEvent) => {
            event.preventDefault();
            if (canSubmit && !createMutation.isPending) createMutation.mutate();
          }}
        >
          <Input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Project title"
          />
          <Textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Research question"
            rows={2}
          />
          <label className="grid gap-1.5">
            <ReadoutLabel>Slug (URL id)</ReadoutLabel>
            <Input
              mono
              value={effectiveSlug}
              onChange={(event) => {
                setSlug(event.target.value);
                setSlugEdited(true);
              }}
              placeholder="auto-from-title"
            />
          </label>
          {!canWrite && hydrated ? (
            <p className="text-[12px] text-state-warn">{signInHint} to create a project.</p>
          ) : null}
          {createMutation.isError ? (
            <p className="text-[12px] text-state-fail">{(createMutation.error as Error).message}</p>
          ) : null}
          <Action type="submit" disabled={!canSubmit || createMutation.isPending} pending={createMutation.isPending}>
            {createMutation.isPending ? "Creating…" : "Create project"}
          </Action>
        </Bay>
      ) : null}

      <ProjectList />
    </section>
  );
}
