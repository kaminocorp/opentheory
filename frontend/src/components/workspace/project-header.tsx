"use client";

import { AlertTriangle, ArrowLeft, Pencil, X } from "lucide-react";
import Link from "next/link";

import { ActionGhost, Bay, Icon, StatusPill, type StateTone } from "@/components/console";
import { cn } from "@/lib/cn";
import type { ContradictionItem, ProjectCounts } from "@/types/research";
import type { Project } from "@/types/project";

// Project status → a state tone (glyph + colour survive grayscale).
const projectStatusTone: Record<Project["status"], StateTone> = {
  draft: "mute",
  active: "run",
  paused: "warn",
  archived: "faint",
};

// The three counts that answer "how much work is here?" at a glance. The full
// six-metric grid is reference material and lives on Overview (0.14.0 D3).
const COMPACT_COUNTS: { key: keyof ProjectCounts; label: string }[] = [
  { key: "threads", label: "threads" },
  { key: "claims", label: "claims" },
  { key: "checkpoints", label: "checkpoints" },
];

type ProjectHeaderProps = {
  project: Project;
  canManage: boolean;
  editing: boolean;
  /** Opens/closes the edit form (which renders on Overview — the handler routes there). */
  onToggleEdit: () => void;
  counts: ProjectCounts | null;
  countsError: boolean;
  contradictions: ContradictionItem[];
  /** Contested claims live on Research; the strip is a way in. */
  onShowContested: () => void;
};

/**
 * Persistent project chrome (0.14.0 §3.1): identity, the honesty surface, and a
 * compact scale readout — everything that must stay true regardless of which tab
 * is open. Rendered *above* the tablist so contested claims are never reachable
 * "only inside Research".
 *
 * Owns no state. `editing` is lifted to the orchestrator because the form itself
 * renders inside the Overview panel while its toggle lives up here.
 */
export function ProjectHeader({
  project,
  canManage,
  editing,
  onToggleEdit,
  counts,
  countsError,
  contradictions,
  onShowContested,
}: ProjectHeaderProps) {
  return (
    <div className="grid gap-3">
      {/* Back link — the ActionText register (text → signal on hover), with a ←. */}
      <Link
        href="/"
        className="inline-flex w-fit items-center gap-1.5 text-[13px] font-medium text-text-mute transition-colors hover:text-signal"
      >
        <Icon icon={ArrowLeft} size={14} />
        Projects
      </Link>

      <Bay as="header" bracketed chamfer density="narrative" className="grid gap-3">
        <div className="flex items-start justify-between gap-3">
          <StatusPill tone={projectStatusTone[project.status]} label={project.status} />
          {/* Owner/admin only (the backend still authorizes the PATCH). */}
          {canManage ? (
            <ActionGhost size="sm" onClick={onToggleEdit}>
              <Icon icon={editing ? X : Pencil} size={14} />
              {editing ? "Cancel" : "Edit"}
            </ActionGhost>
          ) : null}
        </div>

        <h1 className="text-balance text-2xl font-medium leading-snug text-text">{project.title}</h1>
        <p className="max-w-3xl text-[14px] leading-[1.55] text-text-soft">{project.question}</p>
        {/* One line only: the question is the identity, the description is context.
            The untruncated copy — and the Background essay — live on Overview. */}
        {project.description ? (
          <p className="max-w-3xl truncate text-[13px] leading-[1.5] text-text-mute">
            {project.description}
          </p>
        ) : null}

        {/* Honesty surface: contested claims sit above the counts, marked by a
            state-fail edge tick + glyph + label — never softened, never collapsed. */}
        {contradictions.length > 0 ? (
          <button
            type="button"
            onClick={onShowContested}
            // No hover *surface* shift: `--panel-2` is already the lightest structural
            // step, so interactivity reads from the statement text lifting instead.
            className="group relative w-full rounded-built bg-panel-2 p-3 pl-4 text-left"
          >
            <span aria-hidden className="absolute inset-y-0 left-0 w-0.5 bg-state-fail" />
            <span className="flex items-center gap-1.5">
              <Icon icon={AlertTriangle} size={14} className="text-state-fail" />
              <span className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-state-fail">
                {contradictions.length} contested claim{contradictions.length === 1 ? "" : "s"}
              </span>
            </span>
            <span className="mt-2 grid gap-1">
              {contradictions.map((item) => (
                <span
                  key={item.claim_id}
                  className="truncate text-[13px] leading-[1.5] text-text-soft transition-colors group-hover:text-text"
                >
                  {item.statement}
                </span>
              ))}
            </span>
          </button>
        ) : null}

        {/* Compact scale readout — replaces the six-tile grid that used to push the
            workspace below the fold. Loading and error fall back exactly as the
            MetricReadout tiles did (shimmer, then "—"). */}
        <dl className="flex flex-wrap items-center gap-x-2 gap-y-1 pt-1 font-mono text-[11px] tabular-nums">
          {COMPACT_COUNTS.map(({ key, label }, index) => (
            <div key={key} className="flex items-center gap-1.5">
              {index > 0 ? (
                <span aria-hidden className="text-text-faint">
                  ·
                </span>
              ) : null}
              <dt className="font-medium uppercase tracking-[0.14em] text-text-mute">{label}</dt>
              <dd className={cn("font-medium", counts ? "text-text" : "text-text-mute")}>
                {counts ? (
                  counts[key]
                ) : countsError ? (
                  "—"
                ) : (
                  <span
                    aria-hidden
                    className="inline-block h-3 w-4 animate-pulse rounded-inset bg-text-faint/25 align-middle"
                  />
                )}
              </dd>
            </div>
          ))}
        </dl>
      </Bay>
    </div>
  );
}
