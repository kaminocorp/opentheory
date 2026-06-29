import { Search } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { BrandMark, Icon } from "@/components/console";
import { AuthMenu } from "@/components/shell/auth-menu";
import { CommandRail } from "@/components/shell/command-rail";

/**
 * The Kamino app shell (§4.1) — the structural signature. A fixed 6u header and a
 * fixed 7u left command rail frame a full-bleed `<main>` that lays bays on the
 * measured field (the field shows through `<main>`, which paints nothing of its
 * own; the opaque header + rail cover it). Replaces the old centered, header-only
 * page so the console "uses its glass" instead of letterboxing to a column.
 */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen">
      <ShellHeader />
      <div className="flex">
        <CommandRail />
        {/* Gutter steps with the field (§4.3): mobile 16px → 24px from sm up. */}
        <main className="min-w-0 flex-1 px-4 py-5 sm:px-6 sm:py-6">{children}</main>
      </div>
    </div>
  );
}

function ShellHeader() {
  return (
    <header className="sticky top-0 z-30 flex h-12 items-center gap-4 px-4">
      {/* The chamfered, bordered panel lives on its own background layer: the
          clip-path must shape ONLY the surface, never clip the account / sign-in
          dropdowns that overflow below the header. */}
      <div
        aria-hidden
        className="bay-chamfer absolute inset-0 -z-10 bg-panel"
        style={{ borderBottom: "0.5px solid var(--hairline)" }}
      />

      {/* Brand lockup (§8): mark + wordmark, Sans 15/500. The constant identity. */}
      <Link href="/" className="flex shrink-0 items-center gap-2.5 text-text">
        <BrandMark size={22} />
        <span className="text-[15px] font-medium tracking-[-0.01em]">OpenTheory</span>
      </Link>

      {/* Inert search (out of scope): restyled to a square hairline field, not wired. */}
      <div className="hidden min-w-0 flex-1 justify-center md:flex">
        <div
          aria-hidden
          className="flex h-8 w-full max-w-md items-center gap-2 rounded-built bg-ground px-3 text-text-mute"
          style={{ border: "0.5px solid var(--hairline)" }}
        >
          <Icon icon={Search} size={16} className="text-text-mute" />
          <span className="truncate text-[13px]">Search projects, claims, evidence</span>
        </div>
      </div>

      {/* Right slot: global identity. Real (Supabase) sign-in is the only identity path. */}
      <div className="flex shrink-0 items-center gap-2">
        <AuthMenu />
      </div>
    </header>
  );
}
