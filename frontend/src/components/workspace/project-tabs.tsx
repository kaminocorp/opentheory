"use client";

import { useRef } from "react";

import { cn } from "@/lib/cn";
import { PROJECT_TAB_IDS, type ProjectTabId } from "@/lib/use-project-tab";

const TAB_LABELS: Record<ProjectTabId, string> = {
  research: "Research",
  instruments: "Instruments",
  crew: "Crew",
  funding: "Funding",
  overview: "Overview",
};

/** Stable ids so each tab and its panel can point at each other (ARIA). */
export const projectTabDomId = (tab: ProjectTabId) => `project-tab-${tab}`;
export const projectPanelDomId = (tab: ProjectTabId) => `project-panel-${tab}`;

export type ProjectTabBadges = Partial<
  Record<ProjectTabId, { count: number; tone?: "mute" | "fail" } | null>
>;

type ProjectTabsProps = {
  active: ProjectTabId;
  onSelect: (tab: ProjectTabId) => void;
  /** Counts rendered beside a label; derived from queries the orchestrator already holds. */
  badges?: ProjectTabBadges;
  className?: string;
};

/**
 * The project section tablist (0.14.0) — the one nav surface inside a project.
 *
 * Quiet underline tabs: sans labels, the active tab marked by a 2px `--signal`
 * bottom edge plus text colour — never a filled pill. Because the marker is
 * structural, the active tab still reads in grayscale.
 *
 * Tabs are buttons, not links: the ARIA tab pattern owns the interaction and the
 * URL update is a side effect of `onSelect` (the CommandRail uses `<Link>` to the
 * same `?tab=`, so both converge on one source of truth).
 */
export function ProjectTabs({ active, onSelect, badges, className }: ProjectTabsProps) {
  const tabRefs = useRef(new Map<ProjectTabId, HTMLButtonElement | null>());

  // Roving tabindex: only the active tab is in the sequential tab order, and
  // ←/→/Home/End move *and* activate (automatic activation — sound here because
  // every panel is either already mounted or cheap to mount).
  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const last = PROJECT_TAB_IDS.length - 1;
    const index = PROJECT_TAB_IDS.indexOf(active);
    let next: ProjectTabId | undefined;

    if (event.key === "ArrowRight") next = PROJECT_TAB_IDS[index === last ? 0 : index + 1];
    else if (event.key === "ArrowLeft") next = PROJECT_TAB_IDS[index === 0 ? last : index - 1];
    else if (event.key === "Home") next = PROJECT_TAB_IDS[0];
    else if (event.key === "End") next = PROJECT_TAB_IDS[last];
    if (!next) return;

    event.preventDefault();
    onSelect(next);
    tabRefs.current.get(next)?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label="Project sections"
      onKeyDown={handleKeyDown}
      // Scrolls horizontally rather than wrapping or collapsing to a menu — five
      // short labels fit every viewport worth supporting.
      className={cn("flex items-stretch gap-1 overflow-x-auto", className)}
      style={{ borderBottom: "1px solid var(--hairline)" }}
    >
      {PROJECT_TAB_IDS.map((tab) => {
        const isActive = tab === active;
        const badge = badges?.[tab];

        return (
          <button
            key={tab}
            ref={(node) => {
              tabRefs.current.set(tab, node);
            }}
            id={projectTabDomId(tab)}
            type="button"
            role="tab"
            aria-selected={isActive}
            aria-controls={projectPanelDomId(tab)}
            tabIndex={isActive ? 0 : -1}
            onClick={() => onSelect(tab)}
            className={cn(
              "relative shrink-0 whitespace-nowrap px-3 py-2.5 text-[13px] font-medium transition-colors",
              isActive ? "text-text" : "text-text-mute hover:text-text",
            )}
          >
            {TAB_LABELS[tab]}
            {badge && badge.count > 0 ? (
              <span
                className={cn(
                  "ml-1.5 tabular-nums",
                  badge.tone === "fail" ? "text-state-fail" : "text-text-faint",
                )}
              >
                {badge.count}
              </span>
            ) : null}
            {isActive ? (
              <span aria-hidden className="absolute inset-x-2 bottom-0 h-0.5 bg-signal" />
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
