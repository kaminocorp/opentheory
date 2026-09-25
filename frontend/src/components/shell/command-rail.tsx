"use client";

import {
  BookOpen,
  CircleDollarSign,
  FlaskConical,
  LayoutGrid,
  Microscope,
  Users,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, type ReactNode } from "react";

import { Icon } from "@/components/console";
import { cn } from "@/lib/cn";
import {
  PROJECT_TAB_IDS,
  buildCommandRailZones,
  type CommandRailZone,
  type ProjectTabId,
} from "@/lib/project-tab";

const PROJECTS_ICON: LucideIcon = LayoutGrid;

const TAB_ICONS: Record<ProjectTabId, LucideIcon> = {
  research: Microscope,
  instruments: FlaskConical,
  crew: Users,
  funding: CircleDollarSign,
  overview: BookOpen,
};

function zoneIcon(key: string): LucideIcon {
  if (key === "projects") return PROJECTS_ICON;
  if ((PROJECT_TAB_IDS as readonly string[]).includes(key)) {
    return TAB_ICONS[key as ProjectTabId];
  }
  return LayoutGrid;
}

/**
 * The left nav rail. Zones: Projects (index) plus the five project tabs.
 * On a project, each tab is a real `?tab=` link and `active` comes from the
 * URL — the same source the in-page strip uses. Off-project, those five stay
 * in the tree as contextual-off ("open a project first") so they are never a
 * permanently dead item. The pre-0.24 inert Agents hatch is gone: the agent
 * surface is Instruments.
 *
 * The active zone is a filled rounded tile — quiet, no pulse, no edge tick.
 */
export function CommandRail() {
  // useSearchParams() deopts static generation unless a Suspense boundary
  // sits above it. The rail is global chrome, so the boundary lives here
  // rather than in every page.
  return (
    <Suspense fallback={<RailFrame />}>
      <CommandRailInner />
    </Suspense>
  );
}

function CommandRailInner() {
  const pathname = usePathname() ?? "/";
  const searchParams = useSearchParams();
  const zones = buildCommandRailZones(pathname, searchParams.toString());

  return (
    <RailFrame>
      {zones.map((zone) => (
        <RailItem key={zone.key} zone={zone} />
      ))}
    </RailFrame>
  );
}

function RailFrame({ children }: { children?: ReactNode }) {
  return (
    <nav
      aria-label="Primary"
      className="sticky top-12 z-20 flex h-[calc(100dvh-3rem)] w-12 shrink-0 flex-col items-stretch gap-1 self-start border-r border-[color:var(--hairline)] py-3 lg:w-14"
    >
      {children}
    </nav>
  );
}

function RailItem({ zone }: { zone: CommandRailZone }) {
  const tone = zone.active
    ? "bg-white/[0.07] text-text"
    : zone.disabled
      ? "text-text-faint"
      : "text-text-mute hover:bg-white/[0.04] hover:text-text";

  // The accessible name lives on the focusable wrapper (Link, or the
  // contextual-off span), not the decorative icon. Unavailable zones fold
  // the reason in — the `title` tooltip is sighted-hover only.
  const accessibleLabel = zone.disabled ? `${zone.label}, open a project first` : zone.label;

  const glyph = (
    <span
      className={cn(
        "relative mx-auto flex h-10 w-10 items-center justify-center rounded-control transition-colors",
        tone,
      )}
    >
      <Icon icon={zoneIcon(zone.key)} size={18} />
    </span>
  );

  return (
    <div className="relative px-1" title={zone.label}>
      {zone.href ? (
        <Link
          href={zone.href}
          aria-label={accessibleLabel}
          aria-current={zone.active ? "page" : undefined}
          className="block"
        >
          {glyph}
        </Link>
      ) : (
        // Contextual-off: kept focusable + named so it stays in the
        // accessibility tree (`aria-disabled`, not the `disabled` attribute),
        // but never actionable — there is no href/handler.
        <span
          role="link"
          aria-label={accessibleLabel}
          aria-disabled="true"
          tabIndex={0}
          className="block cursor-default"
        >
          {glyph}
        </span>
      )}
    </div>
  );
}
