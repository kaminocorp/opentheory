import { FlaskConical, Search } from "lucide-react";
import Link from "next/link";

import { DevActorSwitcher } from "@/components/shell/dev-actor-switcher";

export function SiteHeader() {
  return (
    <header className="border-b border-line/80 bg-paper/90 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        <Link href="/" className="flex min-w-0 items-center gap-3">
          <span className="grid size-9 shrink-0 place-items-center rounded-md bg-ink text-paper">
            <FlaskConical className="size-5" aria-hidden="true" />
          </span>
          <span className="truncate text-lg font-semibold tracking-normal">OpenTheory</span>
        </Link>

        <div className="hidden min-w-0 flex-1 justify-center md:flex">
          <label className="flex h-10 w-full max-w-md items-center gap-2 rounded-md border border-line bg-white/70 px-3 text-sm text-ink/55">
            <Search className="size-4 shrink-0" aria-hidden="true" />
            <span className="truncate">Search projects, claims, evidence</span>
          </label>
        </div>

        <nav className="flex shrink-0 items-center gap-2">
          <Link
            href="/"
            className="hidden rounded-md px-3 py-2 text-sm font-medium text-ink/70 hover:bg-white/60 hover:text-ink sm:block"
          >
            Projects
          </Link>
          <DevActorSwitcher />
        </nav>
      </div>
    </header>
  );
}
