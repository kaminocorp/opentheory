"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect } from "react";

import {
  normalizeProjectRefId,
  normalizeProjectTab,
  projectViewHref,
  sanitizeProjectViewSearch,
  type ProjectTabId,
  type ProjectViewPatch,
} from "@/lib/project-tab";

export { DEFAULT_PROJECT_TAB, PROJECT_TAB_IDS, type ProjectTabId } from "@/lib/project-tab";

export type ProjectViewKnownIds = {
  threadIds?: readonly string[] | null;
  branchIds?: readonly string[] | null;
};

/**
 * The single source of truth for the project workspace view: `?tab=`, and from
 * 0.31.0 `?thread=` / `?branch=`. One source (not component state) because the
 * tab strip, shareable Research deep links, and the CommandRail (0.24.0) all
 * have to agree.
 *
 * `router.replace` — not `push` — so flipping tabs or selection doesn't fill
 * the back stack with intra-page steps; `{ scroll: false }` so the viewport
 * holds position.
 *
 * CALLER REQUIREMENT: `useSearchParams()` forces any consuming tree under a
 * `<Suspense>` boundary or `next build` fails the static-generation deopt check.
 * The workspace boundary lives in `app/projects/[projectId]/page.tsx`; the rail
 * wraps itself.
 */
export function useProjectView(known?: ProjectViewKnownIds) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const search = searchParams.toString();

  const tab = normalizeProjectTab(searchParams.get("tab"));
  const threadParam = normalizeProjectRefId(searchParams.get("thread"));
  const branchParam = normalizeProjectRefId(searchParams.get("branch"));

  const replaceView = useCallback(
    (next: ProjectViewPatch) => {
      router.replace(projectViewHref(pathname, next, search), { scroll: false });
    },
    [pathname, router, search],
  );

  const setTab = useCallback(
    (next: ProjectTabId) => {
      replaceView({ tab: next });
    },
    [replaceView],
  );

  // Leftover bookmarks that still carry the pre-0.14 `#funding` hash: a hash
  // never reaches `useSearchParams`, so rewrite it once to `?tab=funding`. The
  // rail itself no longer emits the hash (0.24.0).
  useEffect(() => {
    if (window.location.hash !== "#funding") return;
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    setTab("funding");
  }, [setTab]);

  // Malformed ids drop immediately. Unknown ids drop only after the matching
  // list has loaded — a failed list must not erase a share link we couldn't
  // confirm. Never throw; the workspace stays on defaults.
  const threadIds = known?.threadIds ?? null;
  const branchIds = known?.branchIds ?? null;
  const threadKey = threadIds == null ? "pending" : threadIds.join("\0").toLowerCase();
  const branchKey = branchIds == null ? "pending" : branchIds.join("\0").toLowerCase();

  useEffect(() => {
    const next = sanitizeProjectViewSearch(search, { threadIds, branchIds }).toString();
    if (next === search) return;
    router.replace(next ? `${pathname}?${next}` : pathname, { scroll: false });
    // threadKey / branchKey stand in for list identity so a fresh `.map()`
    // array does not retrigger after every render.
  }, [branchIds, branchKey, pathname, router, search, threadIds, threadKey]);

  return { tab, setTab, threadParam, branchParam, replaceView };
}

/** Tab-only slice — same `?tab=` contract as 0.14.0 / 0.24.0. */
export function useProjectTab() {
  const { tab, setTab } = useProjectView();
  return { tab, setTab };
}
