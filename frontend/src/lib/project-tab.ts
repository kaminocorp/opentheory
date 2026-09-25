/**
 * Project deepdive tab contract (0.14.0 + 0.24.0).
 *
 * Five ids, frozen for v1 — do not add a sixth until a real surface forces it.
 * Declaration order is tab order, keyboard (←/→, Home/End) order, and rail order.
 *
 * `?tab=` is the single source of truth: the in-page strip, deep links, and the
 * CommandRail all derive active state from it. Unknown / missing values fall
 * back to Research so a bad URL never invents a sixth surface.
 */

export const PROJECT_TAB_IDS = ["research", "instruments", "crew", "funding", "overview"] as const;

export type ProjectTabId = (typeof PROJECT_TAB_IDS)[number];

/** Research is the default surface: the ledger, not the configuration. */
export const DEFAULT_PROJECT_TAB: ProjectTabId = "research";

/**
 * Research + Instruments stay mounted across tab switches. Load-bearing: the
 * agent pass holds `activeRunId` in local state and polls from there, so
 * unmounting Instruments would silently kill an in-flight trace.
 */
export const KEEP_ALIVE_TABS = ["research", "instruments"] as const satisfies readonly ProjectTabId[];

export const PROJECT_TAB_LABELS: Record<ProjectTabId, string> = {
  research: "Research",
  instruments: "Instruments",
  crew: "Crew",
  funding: "Funding",
  overview: "Overview",
};

/** A project deepdive path is `/projects/<id>` — not the index, not `/projects`. */
export function isProjectPathname(pathname: string): boolean {
  if (!pathname.startsWith("/projects/")) return false;
  const rest = pathname.slice("/projects/".length);
  return rest.length > 0 && !rest.includes("/");
}

export function normalizeProjectTab(raw: string | null | undefined): ProjectTabId {
  // `find` rather than `includes(raw as ProjectTabId)` so an unknown/absent
  // param narrows without a cast — a bad `?tab=` silently falls back.
  return PROJECT_TAB_IDS.find((id) => id === raw) ?? DEFAULT_PROJECT_TAB;
}

export function projectTabFromSearch(search: string): ProjectTabId {
  const raw = search.startsWith("?") ? search.slice(1) : search;
  return normalizeProjectTab(new URLSearchParams(raw).get("tab"));
}

/**
 * Build `?tab=<id>` on the current project path. Other params (a future
 * `?thread=` / `?branch=` deep link) are preserved, never dropped.
 */
export function projectTabHref(pathname: string, tab: ProjectTabId, currentSearch = ""): string {
  const raw = currentSearch.startsWith("?") ? currentSearch.slice(1) : currentSearch;
  const params = new URLSearchParams(raw);
  params.set("tab", tab);
  return `${pathname}?${params.toString()}`;
}

export type CommandRailZone = {
  key: string;
  label: string;
  href: string | null;
  active: boolean;
  /** Contextual-off: the zone needs a project that isn't open here. */
  disabled: boolean;
};

/**
 * Projects + the five project tabs. No hash targets, no inert "coming soon"
 * zone — Agents was retired in 0.24.0 because the agent surface already lives
 * on Instruments (and project-wide Run research on Overview).
 */
export function buildCommandRailZones(pathname: string, search = ""): CommandRailZone[] {
  const onIndex = pathname === "/";
  const onProject = isProjectPathname(pathname);
  const tab = projectTabFromSearch(search);

  const zones: CommandRailZone[] = [
    {
      key: "projects",
      label: "Projects",
      href: "/",
      active: onIndex,
      disabled: false,
    },
  ];

  for (const id of PROJECT_TAB_IDS) {
    zones.push({
      key: id,
      label: PROJECT_TAB_LABELS[id],
      href: onProject ? projectTabHref(pathname, id, search) : null,
      active: onProject && tab === id,
      disabled: !onProject,
    });
  }

  return zones;
}
