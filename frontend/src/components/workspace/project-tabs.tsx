"use client";

import { useRef } from "react";

import { LiveDot } from "@/components/console";
import { cn } from "@/lib/cn";
import { PROJECT_TAB_IDS, PROJECT_TAB_LABELS, type ProjectTabId } from "@/lib/project-tab";

/** Stable ids so each tab and its panel can point at each other (ARIA). */
export const projectTabDomId = (tab: ProjectTabId) => `project-tab-${tab}`;
export const projectPanelDomId = (tab: ProjectTabId) => `project-panel-${tab}`;

export type ProjectTabBadge = {
  count?: number;
  tone?: "mute" | "fail";
  /** Instruments: a pass is actually running. Never colour-only for the active tab. */
  live?: boolean;
} | null;

export type ProjectTabBadges = Partial<Record<ProjectTabId, ProjectTabBadge>>;

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
 * same `?tab=`, so both converge on one source of truth — 0.24.0).
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
        const count = badge?.count ?? 0;
        const live = Boolean(badge?.live);
        const label = PROJECT_TAB_LABELS[tab];
        const announced =
          live && count > 0
            ? `${label}, ${count}, pass running`
            : live
              ? `${label}, pass running`
              : count > 0
                ? `${label}, ${count}`
                : undefined;

        return (
          <button
            key={tab}
            ref={(node) => {
              tabRefs.current.set(tab, node);
            }}
            id={projectTabDomId(tab)}
            type="button"
            role="tab"
            aria-label={announced}
            aria-selected={isActive}
            aria-controls={projectPanelDomId(tab)}
            tabIndex={isActive ? 0 : -1}
            onClick={() => onSelect(tab)}
            className={cn(
              "relative shrink-0 whitespace-nowrap px-3 py-2.5 text-[13px] font-medium transition-colors",
              isActive ? "text-text" : "text-text-mute hover:text-text",
            )}
          >
            {label}
            {count > 0 ? (
              <span
                className={cn(
                  "ml-1.5 tabular-nums",
                  badge?.tone === "fail" ? "text-state-fail" : "text-text-faint",
                )}
              >
                {count}
              </span>
            ) : null}
            {live ? <LiveDot tone="signal" pulse className="ml-1.5 align-middle" /> : null}
            {isActive ? (
              <span aria-hidden className="absolute inset-x-2 bottom-0 h-0.5 bg-signal" />
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
