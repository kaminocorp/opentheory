/**
 * Project deepdive view contract (0.14.0 + 0.24.0 + 0.31.0).
 *
 * Five tab ids, frozen for v1 — do not add a sixth until a real surface forces it.
 * Declaration order is tab order, keyboard (←/→, Home/End) order, and rail order.
 *
 * `?tab=` is the single source of truth for the surface: the in-page strip, deep
 * links, and the CommandRail all derive active state from it. Unknown / missing
 * values fall back to Research so a bad URL never invents a sixth surface.
 *
 * `?thread=` / `?branch=` (0.31.0) are shareable Research selection. They are
 * UUIDs of rows already on the project. Unknown, malformed, or absent ids fall
 * back to the workspace defaults (no thread; the main line) — never an error.
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

export const PROJECT_VIEW_THREAD_PARAM = "thread";
export const PROJECT_VIEW_BRANCH_PARAM = "branch";

/** Ledger ids are UUID strings. Anything else is not a selection — ignore it. */
const PROJECT_REF_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function normalizeProjectRefId(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const trimmed = raw.trim();
  return PROJECT_REF_ID.test(trimmed) ? trimmed.toLowerCase() : null;
}

export function projectRefIdsEqual(a: string, b: string): boolean {
  return a.toLowerCase() === b.toLowerCase();
}

/** Pick the known row id, or null when the param is missing / unknown. */
export function resolveProjectRefId(
  raw: string | null | undefined,
  knownIds: readonly string[] | null | undefined,
): string | null {
  const wanted = normalizeProjectRefId(raw);
  if (!wanted || !knownIds) return null;
  return knownIds.find((id) => projectRefIdsEqual(id, wanted)) ?? null;
}

export type ProjectViewPatch = {
  tab?: ProjectTabId;
  /** `null` clears the param (default: no thread / main line). Omit to leave it. */
  thread?: string | null;
  branch?: string | null;
};

function searchParamsFrom(currentSearch: string): URLSearchParams {
  const raw = currentSearch.startsWith("?") ? currentSearch.slice(1) : currentSearch;
  return new URLSearchParams(raw);
}

function hrefWithSearch(pathname: string, params: URLSearchParams): string {
  const qs = params.toString();
  return qs ? `${pathname}?${qs}` : pathname;
}

/**
 * Drop malformed `thread` / `branch` immediately. Once the matching list has
 * loaded, also drop unknown ids so a stale share link degrades to defaults
 * instead of pinning a selection that is not on this project.
 *
 * `knownIds === null` means "list not loaded (or failed) — do not judge yet".
 */
export function sanitizeProjectViewSearch(
  currentSearch: string,
  known: {
    threadIds?: readonly string[] | null;
    branchIds?: readonly string[] | null;
  } = {},
): URLSearchParams {
  const params = searchParamsFrom(currentSearch);
  sanitizeRefParam(params, PROJECT_VIEW_THREAD_PARAM, known.threadIds);
  sanitizeRefParam(params, PROJECT_VIEW_BRANCH_PARAM, known.branchIds);
  return params;
}

function sanitizeRefParam(
  params: URLSearchParams,
  key: string,
  knownIds: readonly string[] | null | undefined,
): void {
  if (!params.has(key)) return;
  const normalized = normalizeProjectRefId(params.get(key));
  if (!normalized) {
    params.delete(key);
    return;
  }
  if (knownIds && !knownIds.some((id) => projectRefIdsEqual(id, normalized))) {
    params.delete(key);
    return;
  }
  if (params.get(key) !== normalized) params.set(key, normalized);
}

/**
 * Build a project view URL. `tab` is always written when provided; `thread` /
 * `branch` are written or cleared only when present on the patch. Sibling
 * params are preserved.
 */
export function projectViewHref(
  pathname: string,
  next: ProjectViewPatch,
  currentSearch = "",
): string {
  const params = searchParamsFrom(currentSearch);
  if (next.tab !== undefined) params.set("tab", next.tab);
  if ("thread" in next) {
    const id = normalizeProjectRefId(next.thread);
    if (id) params.set(PROJECT_VIEW_THREAD_PARAM, id);
    else params.delete(PROJECT_VIEW_THREAD_PARAM);
  }
  if ("branch" in next) {
    const id = normalizeProjectRefId(next.branch);
    if (id) params.set(PROJECT_VIEW_BRANCH_PARAM, id);
    else params.delete(PROJECT_VIEW_BRANCH_PARAM);
  }
  return hrefWithSearch(pathname, params);
}

/**
 * Build `?tab=<id>` on the current project path. Other params (`?thread=` /
 * `?branch=` and anything else) are preserved, never dropped.
 */
export function projectTabHref(pathname: string, tab: ProjectTabId, currentSearch = ""): string {
  return projectViewHref(pathname, { tab }, currentSearch);
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
