"use client";

import { Bot, CircleDollarSign, LayoutGrid, Microscope, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Icon } from "@/components/console";
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
  /** Not built yet (Agents): honest "coming soon" treatment. */
  inert?: boolean;
}

/**
 * The left nav rail. Zones: Projects (index), Workspace + Funding (contextual,
 * live inside a project), and an inert Agents zone honest about what doesn't
 * exist yet.
 *
 * The active zone is a filled rounded tile — quiet, no pulse, no edge tick.
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
      className="sticky top-12 z-20 flex h-[calc(100dvh-3rem)] w-12 shrink-0 flex-col items-stretch gap-1 self-start border-r border-[color:var(--hairline)] py-3 lg:w-14"
    >
      {zones.map((zone) => (
        <RailItem key={zone.key} zone={zone} />
      ))}
    </nav>
  );
}

function RailItem({ zone }: { zone: RailZone }) {
  const tone = zone.active
    ? "bg-white/[0.07] text-text"
    : zone.disabled || zone.inert
      ? "text-text-faint"
      : "text-text-mute hover:bg-white/[0.04] hover:text-text";

  // The accessible name lives on the focusable wrapper (Link, or the inert span made
  // focusable below), not the decorative icon — so a screen-reader user reaches it
  // whether navigating linearly or by control. Unavailable zones fold the reason in
  // (the `title` tooltip is sighted-hover only and isn't reliably announced).
  const accessibleLabel = zone.inert
    ? `${zone.label}, coming soon`
    : zone.disabled
      ? `${zone.label}, open a project first`
      : zone.label;

  const glyph = (
    <span
      className={cn(
        "relative mx-auto flex h-10 w-10 items-center justify-center rounded-control transition-colors",
        tone,
      )}
    >
      <Icon icon={zone.icon} size={18} />
    </span>
  );

  return (
    <div className="relative px-1" title={zone.inert ? `${zone.label} — coming soon` : zone.label}>
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
        // Unavailable (contextual-off / inert): kept focusable + named so it stays in
        // the accessibility tree (`aria-disabled`, not the `disabled` attribute, is the
        // "present but inactive" contract), but never actionable — there is no href/handler.
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
