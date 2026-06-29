"use client";

import Link from "next/link";
import { useState } from "react";

import { BrandMark } from "@/components/console";

/**
 * The header brand lockup (§8): mark + wordmark, the constant identity — plus the
 * §5.9 click "jingle" easter egg. Clicking replays a one-shot assemble of the
 * mark (the four nodes pop up the diagonal and land, with a crimson spark) while
 * the `<Link>` still navigates home.
 *
 * The animation is replayed by remounting `BrandMark` via a changing `key`: each
 * click bumps `runId`, React tears down and rebuilds the SVG, and the one-shot
 * CSS animation plays fresh — no `animationend` cleanup. It is steady on first
 * load (`assembling` is false at `runId === 0`); the easter egg is intentional,
 * never an unprompted intro on every navigation. Frozen under reduced-motion by
 * the CSS (the mark resolves straight to its steady state).
 */
export function BrandLockup() {
  const [runId, setRunId] = useState(0);
  return (
    <Link
      href="/"
      onClick={() => setRunId((n) => n + 1)}
      className="flex shrink-0 items-center gap-2.5 text-text"
    >
      <BrandMark key={runId} size={22} assembling={runId > 0} />
      <span className="text-[15px] font-medium tracking-[-0.01em]">OpenTheory</span>
    </Link>
  );
}
