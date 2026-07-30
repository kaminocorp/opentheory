"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect } from "react";

/**
 * The project deepdive tab set (0.14.0). Frozen at five for v1 — do not add a
 * sixth until a real surface forces it (e.g. an agent-run history browser).
 * Declaration order is also tab order and keyboard (←/→, Home/End) order.
 */
export const PROJECT_TAB_IDS = ["research", "instruments", "crew", "funding", "overview"] as const;

export type ProjectTabId = (typeof PROJECT_TAB_IDS)[number];

/** Research is the default surface: the ledger, not the configuration. */
export const DEFAULT_PROJECT_TAB: ProjectTabId = "research";

function normalizeTab(raw: string | null): ProjectTabId {
  // `find` rather than `includes(raw as ProjectTabId)` so an unknown/absent
  // param narrows without a cast — a bad `?tab=` silently falls back.
  return PROJECT_TAB_IDS.find((id) => id === raw) ?? DEFAULT_PROJECT_TAB;
}

/**
 * The single source of truth for which project tab is active: the `?tab=` search
 * param. One source (not component state) because the tab strip, deep links, and
 * the CommandRail (0.14.1) all have to agree, and retrofitting that later would
 * re-touch every setter.
 *
 * `router.replace` — not `push` — so flipping between tabs doesn't fill the back
 * stack with intra-page steps; `{ scroll: false }` so the viewport holds position.
 *
 * CALLER REQUIREMENT: `useSearchParams()` forces any consuming tree under a
 * `<Suspense>` boundary or `next build` fails the static-generation deopt check.
 * The boundary lives in `app/projects/[projectId]/page.tsx`.
 */
export function useProjectTab() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const tab = normalizeTab(searchParams.get("tab"));

  const setTab = useCallback(
    (next: ProjectTabId) => {
      // Preserve any other params (a future ?thread=/?branch= deep link) rather
      // than rebuilding the query string from just the tab.
      const params = new URLSearchParams(searchParams.toString());
      params.set("tab", next);
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  // Legacy `#funding` (the pre-0.14 CommandRail target): a hash never reaches
  // `useSearchParams`, so normalize it client-side to `?tab=funding` once. One
  // release of grace — the rail stops emitting it in 0.14.1.
  useEffect(() => {
    if (window.location.hash !== "#funding") return;
    // Drop the hash first so this can't re-fire after the replace lands.
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    setTab("funding");
  }, [setTab]);

  return { tab, setTab };
}
