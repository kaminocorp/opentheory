"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect } from "react";

import { normalizeProjectTab, projectTabHref, type ProjectTabId } from "@/lib/project-tab";

export { DEFAULT_PROJECT_TAB, PROJECT_TAB_IDS, type ProjectTabId } from "@/lib/project-tab";

/**
 * The single source of truth for which project tab is active: the `?tab=` search
 * param. One source (not component state) because the tab strip, deep links, and
 * the CommandRail (0.24.0; historically 0.14.1) all have to agree.
 *
 * `router.replace` — not `push` — so flipping between tabs doesn't fill the back
 * stack with intra-page steps; `{ scroll: false }` so the viewport holds position.
 *
 * CALLER REQUIREMENT: `useSearchParams()` forces any consuming tree under a
 * `<Suspense>` boundary or `next build` fails the static-generation deopt check.
 * The workspace boundary lives in `app/projects/[projectId]/page.tsx`; the rail
 * wraps itself.
 */
export function useProjectTab() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const tab = normalizeProjectTab(searchParams.get("tab"));

  const setTab = useCallback(
    (next: ProjectTabId) => {
      router.replace(projectTabHref(pathname, next, searchParams.toString()), { scroll: false });
    },
    [pathname, router, searchParams],
  );

  // Leftover bookmarks that still carry the pre-0.14 `#funding` hash: a hash
  // never reaches `useSearchParams`, so rewrite it once to `?tab=funding`. The
  // rail itself no longer emits the hash (0.24.0).
  useEffect(() => {
    if (window.location.hash !== "#funding") return;
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    setTab("funding");
  }, [setTab]);

  return { tab, setTab };
}
