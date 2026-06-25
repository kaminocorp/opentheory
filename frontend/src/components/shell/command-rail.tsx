"use client";

import { Bot, CircleDollarSign, LayoutGrid, Microscope, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Icon, LiveDot } from "@/components/console";
import { cn } from "@/lib/cn";

interface RailZone {
  key: string;
  label: string;
  icon: LucideIcon;
  /** Navigation target, or null when the zone is contextual-off / inert. */
  href: string | null;
  /** The current route lives in this zone (exactly one is active per route). */
  active: boolean;
  /** Contextual zone that needs a project context which isn't present here. */
  disabled?: boolean;
  /** Not built yet (Agents → 0.7.0): honest hatched "coming soon" treatment. */
  inert?: boolean;
}

/**
 * The left command rail (§4.1, Decision 1). Adapted to OpenTheory's real zones —
 * Projects (index), Workspace + Funding (contextual, live inside a project), and a
 * hatched, inert Agents zone honest about what doesn't exist yet (0.7.0).
 *
 * The active zone is marked by a 2px `--signal` edge tick + a round live dot —
 * never a filled block (§4.1/§9.2). Collapses to icon-only width ≤1024 (§4.3).
 */
export function CommandRail() {
  const pathname = usePathname() ?? "/";
  const onProject = pathname.startsWith("/projects/");
  const onIndex = pathname === "/";

  const zones: RailZone[] = [
    { key: "projects", label: "Projects", icon: LayoutGrid, href: "/", active: onIndex },
    {
      key: "workspace",
      label: "Workspace",
      icon: Microscope,
      href: onProject ? pathname : null,
      active: onProject,
      disabled: !onProject,
    },
    {
      key: "funding",
      label: "Funding",
      icon: CircleDollarSign,
      href: onProject ? `${pathname}#funding` : null,
      active: false,
      disabled: !onProject,
    },
    { key: "agents", label: "Agents", icon: Bot, href: null, active: false, inert: true },
  ];

  return (
    <nav
      aria-label="Primary"
      className="sticky top-12 z-20 flex h-[calc(100dvh-3rem)] w-12 shrink-0 flex-col items-stretch gap-1 self-start bg-panel py-3 lg:w-14"
      style={{ borderRight: "0.5px solid var(--hairline)" }}
    >
      {zones.map((zone) => (
        <RailItem key={zone.key} zone={zone} />
      ))}
    </nav>
  );
}

function RailItem({ zone }: { zone: RailZone }) {
  const tone = zone.active
    ? "text-text"
    : zone.disabled || zone.inert
      ? "text-text-faint"
      : "text-text-mute hover:text-text";

  // The Icon's aria-label is the zone's accessible name; for unavailable zones, fold the
  // reason into it (the `title` tooltip below is for sighted hover and isn't reliably
  // announced to assistive tech).
  const accessibleLabel = zone.inert
    ? `${zone.label}, coming soon`
    : zone.disabled
      ? `${zone.label}, open a project first`
      : zone.label;

  const glyph = (
    <span
      className={cn(
        "relative mx-auto flex h-11 w-11 items-center justify-center rounded-built transition-colors",
        zone.inert && "hatch",
        tone,
      )}
    >
      <Icon icon={zone.icon} size={18} aria-label={accessibleLabel} />
      {/* The "alive" marker: a pulsing signal dot on the active zone. */}
      {zone.active && <LiveDot tone="signal" pulse size={6} className="absolute right-1.5 top-1.5" />}
    </span>
  );

  return (
    <div className="relative px-0.5" title={zone.inert ? `${zone.label} — coming soon` : zone.label}>
      {zone.href ? (
        <Link href={zone.href} aria-current={zone.active ? "page" : undefined} className="block">
          {glyph}
        </Link>
      ) : (
        <span aria-disabled className="block cursor-default">
          {glyph}
        </span>
      )}
      {/* 2px signal edge tick on the rail edge — the active marker, never a fill. */}
      {zone.active && (
        <span aria-hidden className="absolute inset-y-2 right-0 w-0.5 bg-signal" />
      )}
    </div>
  );
}
