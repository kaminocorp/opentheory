import { Search } from "lucide-react";
import type { ReactNode } from "react";

import { Icon } from "@/components/console";
import { AuthMenu } from "@/components/shell/auth-menu";
import { BrandLockup } from "@/components/shell/brand-lockup";
import { CommandRail } from "@/components/shell/command-rail";
import { InvitationInbox } from "@/components/shell/invitation-inbox";

/**
 * The OpenTheory app shell: a fixed 48px header and a fixed left nav rail frame
 * a full-bleed `<main>`. Flat surfaces separated by hairline borders — no
 * texture, no ornament.
 */
export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen">
      <ShellHeader />
      <div className="flex">
        <CommandRail />
        {/* Gutter steps with the viewport: mobile 16px → 24px from sm up. */}
        <main className="min-w-0 flex-1 px-4 py-5 sm:px-6 sm:py-6">{children}</main>
      </div>
    </div>
  );
}

function ShellHeader() {
  return (
    <header className="sticky top-0 z-30 flex h-12 items-center gap-4 px-4">
      {/* The header surface lives on its own background layer so dropdowns that
          overflow below the header are never clipped. */}
      <div
        aria-hidden
        className="absolute inset-0 -z-10 border-b border-[color:var(--hairline)] bg-ground/90 backdrop-blur"
      />

      {/* Brand lockup: mark + wordmark — the constant identity, plus the click
          "jingle" easter egg (the mark re-assembles on click). */}
      <BrandLockup />

      {/* Inert search (out of scope): a quiet pill, not wired. */}
      <div className="hidden min-w-0 flex-1 justify-center md:flex">
        <div
          aria-hidden
          className="flex h-8 w-full max-w-md items-center gap-2 rounded-full border border-[color:var(--hairline)] bg-white/[0.03] px-3.5 text-text-mute"
        >
          <Icon icon={Search} size={16} className="text-text-mute" />
          <span className="truncate text-[13px]">Search projects, claims, evidence</span>
        </div>
      </div>

      {/* Right slot: the invitation bell (signed-in only — it self-hides otherwise) then global
          identity. Real (Supabase) sign-in is the only identity path. */}
      <div className="flex shrink-0 items-center gap-2">
        <InvitationInbox />
        <AuthMenu />
      </div>
    </header>
  );
}
