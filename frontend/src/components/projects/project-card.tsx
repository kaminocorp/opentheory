import { ArrowUpRight, GitBranch, Landmark, ShieldCheck } from "lucide-react";

import { Bay, Icon, ReadoutLabel, StatusPill, type StateTone } from "@/components/console";
import type { Project } from "@/types/project";

const statusLabels: Record<Project["status"], string> = {
  draft: "Draft",
  active: "Active",
  paused: "Paused",
  archived: "Archived",
};

// Project status → a state tone. Carries glyph + colour; meaning survives grayscale.
const statusTone: Record<Project["status"], StateTone> = {
  draft: "mute", // ▣ queued / not started
  active: "run", // ● in motion
  paused: "warn", // ▲ held
  archived: "faint", // · ambient / closed
};

type ProjectCardProps = {
  project: Project;
};

export function ProjectCard({ project }: ProjectCardProps) {
  return (
    <Bay as="article" bracketed density="narrative" className="grid content-start gap-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <StatusPill tone={statusTone[project.status]} label={statusLabels[project.status]} />
          <h3 className="mt-3 text-balance text-[18px] font-medium leading-snug text-text">
            {project.title}
          </h3>
        </div>
        {/* Open affordance — round (it navigates), ghost ring. */}
        <a
          href={`/projects/${project.id}`}
          className="grid size-9 shrink-0 place-items-center rounded-full text-text-mute transition-colors hover:text-text"
          style={{ border: "0.5px solid var(--hairline-strong)" }}
          aria-label={`Open ${project.title}`}
          title={`Open ${project.title}`}
        >
          <Icon icon={ArrowUpRight} size={16} />
        </a>
      </div>

      <p className="text-[14px] leading-[1.55] text-text-soft">{project.question}</p>

      {project.description ? (
        <p className="line-clamp-3 text-[14px] leading-[1.55] text-text-mute">{project.description}</p>
      ) : null}

      <div
        className="grid grid-cols-3 gap-2 pt-4"
        style={{ borderTop: "0.5px solid var(--hairline)" }}
      >
        <span className="flex items-center gap-1.5 text-text-mute">
          <Icon icon={GitBranch} size={14} />
          <ReadoutLabel>Threads</ReadoutLabel>
        </span>
        <span className="flex items-center gap-1.5 text-text-mute">
          <Icon icon={ShieldCheck} size={14} />
          <ReadoutLabel>Validation</ReadoutLabel>
        </span>
        <span className="flex items-center gap-1.5 text-text-mute">
          <Icon icon={Landmark} size={14} />
          <ReadoutLabel>Funding</ReadoutLabel>
        </span>
      </div>
    </Bay>
  );
}
