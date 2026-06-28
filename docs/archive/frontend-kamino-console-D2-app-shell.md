# Frontend — Kamino Console · Phase D2 (App Shell) — Completion

> Implements **Phase D2** of `docs/executing/frontend-kamino-console-redesign.md`:
> replaces the centered, header-only layout with the full-bleed **app shell** (§4.1)
> — a 6u header + a 7u left command rail framing a bay grid on the measured field.
> The structural signature. Presentation-only; **no** backend / schema / API /
> data-flow change, and all auth logic preserved byte-for-byte.

**Status:** complete. `typecheck` / `lint` / `build` green; the shell SSRs (the
prerendered home contains the wordmark, the inert search, and all four rail zones).
Builds against D1's `@/components/console` primitives.

**Version:** still provisional (see the D1 completion doc) — changelog deferred.

---

## What landed, where, and why

### 1. `src/components/shell/app-shell.tsx` (new) — `AppShell` + `ShellHeader`

- **`AppShell`** — a sticky header, then a `flex` row of the `CommandRail` and a
  full-bleed `<main className="min-w-0 flex-1 px-6 py-6">`. The `<main>` paints
  *nothing* of its own, so the body's measured field (D1) shows through it; the
  opaque header + rail cover the field where they sit. `px-6` is the 3u bay gutter.
  No `max-w` letterbox — the console "uses its glass" (§4.1).
- **`ShellHeader`** — the fixed 6u (h-12) header: the brand lockup (`BrandMark` +
  "OpenTheory" wordmark, Sans 15/500/`-0.01em`, linking home), the **inert**
  restyled search (square, hairline, `bg-ground`, not wired — out of scope), and a
  right slot hosting the dev-actor switcher (dev only) + `AuthMenu`. The old
  in-header "Projects" link is gone — that zone moved to the rail.

**Sticky, not fixed (decision).** Header is `sticky top-0 z-30`; the rail is
`sticky top-12`. Sticky keeps the chrome pinned while letting content flow
naturally — no manual `padding-top`/`margin-left` offset math to keep in sync with
the header/rail sizes, and no overlap bugs.

**The chamfer is on a background layer (bug avoided — see below).**

### 2. `src/components/shell/command-rail.tsx` (new) — `CommandRail`

The left command rail (§4.1), adapted to OpenTheory's real zones (**Decision 1** —
*not* Hyperdrive's signal→build→ship→monitor):

| Zone | Icon | Behaviour |
|---|---|---|
| **Projects** | `LayoutGrid` | links `/`; active on the index |
| **Workspace** | `Microscope` | contextual — enabled + active only on a `/projects/*` route; disabled (faint) off-project |
| **Funding** | `CircleDollarSign` | contextual — links `${pathname}#funding` on a project; disabled off-project |
| **Agents** | `Bot` | **inert** — hatched "coming soon" treatment (§5.7), honest about 0.7.0; not a link |

- **Active marker = a 2px `--signal` edge tick on the rail edge + a pulsing
  `LiveDot`** (§4.1/§9.2) — never a filled block. Exactly one zone is active per
  route (Projects on `/`, Workspace inside a project), detected with `usePathname`.
- Glyphs go through the D1 `Icon` wrapper, so the rail shares the data-hairline
  stroke weight (§7).
- **Collapses to icon-only width ≤1024** (§4.3): `w-12` (48px) base, `lg:w-14`
  (56px) at ≥1024. The rail is icon-only at every width, so "collapse" is the width
  step.

### 3. `globals.css` — menu surface + entrance motion (D2's motion slice)

- **`.menu`** — the one sanctioned *non-recess* shadow: a menu *lifting off* the
  field (square, opaque `--panel`, hairline-strong ring, a soft drop shadow), as
  opposed to `.bay`, which is cut *into* the field. Used by every dropdown.
- **`@keyframes menu-pop` + `.menu-pop`** — the §6 menu entrance (fade + 4px slide,
  0.18s), registered in the `prefers-reduced-motion: reduce` freeze alongside the
  D1 liveness keyframes.

### 4. `auth-menu.tsx` + `dev-actor-switcher.tsx` — re-skinned in place

Console tokens + primitives throughout: the trigger buttons are **round** ghost
affordances (`rounded-full`, hairline-strong ring); dropdowns use `.menu .menu-pop`;
forms use the D1 `Input` + a round primary submit; the "Acting actor" header is a
mono `ReadoutLabel`; list rows are square with a `--panel-2` hover; the `Check` /
`ShieldCheck` badges go through `Icon`. The "Sign in" trigger is a primary `Action`.

**Logic is byte-for-byte unchanged.** Every hook (`useAuth`, `useActingIdentity`,
`useDevActor`, the `useQuery`/`useMutation` for actors), all `useState`, the
outside-click `useEffect`, `handleSignOut`/`handleEmailSignIn`, the
`queryClient.clear()`/`invalidateQueries`, and every conditional return are
identical to 0.6.2 — only `className`/markup changed.

### 5. Pages — `src/app/page.tsx`, `src/app/projects/[projectId]/page.tsx`

Both now render their content inside `<AppShell>`; the old `<main class=min-h-screen>`
+ `<SiteHeader/>` + centered `max-w-7xl` section are gone. The index's hero/metric
markup is **deliberately left as the pre-Kamino markup** (flagged with a comment) —
D3 converts it; D2 only re-homes it inside the obsidian shell. Inner content caps
(`max-w-3xl` on the hero copy) stay, which is on-spec (§4.1 "bays cap their own
content"; only the whole-console letterbox was removed).

### 6. Deleted `src/components/shell/site-header.tsx`

Its contents moved into `ShellHeader`; it had no importers beyond the two pages
(verified before deletion), and none remain after.

---

## Decisions & deviations (with rationale)

1. **Chamfer on a `-z-10` background layer, not the `<header>` itself.** Putting
   `.bay-chamfer` (a `clip-path`) on the header would clip its **entire subtree** to
   the polygon — and the account / sign-in / dev-switcher dropdowns are absolutely
   positioned children that overflow *below* the 48px header, so they'd be clipped
   to invisibility (a functional regression). The chamfer now lives on an
   `absolute inset-0 -z-10 bg-panel` layer, so it shapes only the surface; the
   header keeps `overflow: visible` and the menus render. This is the kind of bug a
   green build does not catch — called out for reviewers.
2. **Funding links to `#funding`** — the anchor target (the funding panel's `id`)
   lands in **D4**; until then the link is harmless (scrolls nowhere). Noted so it
   isn't mistaken for a dead link.
3. **Signal-seldom, pre-emptively applied to the chrome.** The account/switcher
   `UserCircle` trigger icon was demoted from the old teal-signal to `--text-mute`;
   `--signal` in the shell now appears only on the active rail tick + dot, the
   primary "Sign in"/submit actions, and the legitimate `ShieldCheck` internal-role
   badge. (The full signal audit is a D6 gate, but the shell is built to pass it.)
4. **Email input set to `mono`** — an email is an identifier/value, which is Mono by
   the §3.1 data/prose split.
5. **§4.3 ≤768 "header actions → overflow" only partially done.** The center search
   is already `hidden md:flex`; a full small-screen overflow menu for the right slot
   is left to **D6**'s responsive polish (per the plan, D6 owns the responsive
   audit). The field-grid-hidden-≤768 rule was already shipped in D1.

## Explicitly NOT touched (scope discipline)

No query key, mutation, route, `useActingIdentity`/`useAuth`/`useDevActor` call, or
read-schema field changed. The workspace panels, project card, and the index
hero/metrics still carry pre-Kamino markup and render transitional inside the shell
— the planned D2 end-state (chrome is Kamino; inner content converts in D3–D5).

---

## Verification (reproduced)

- **`npm run typecheck`** → clean. **`npm run lint`** → clean.
- **`npm run build`** (and a second run with `NEXT_PUBLIC_AUTH_DEV=true` to exercise
  the dev-switcher branch) → success; all 6 routes generated; no runtime throw from
  the shell's client subcomponents during prerender.
- **Shell SSRs** — the prerendered `/` HTML contains the shell structure: the
  `OpenTheory` wordmark, the inert "Search projects…" field, and the rail
  (`aria-label="Primary"`) with all four zones (`Projects`, `Workspace`, `Funding`,
  `Agents`). So `AppShell` + `CommandRail` render and aren't silently empty.
- **No dangling `SiteHeader` references** after deletion.

> Not done here (belongs to later phases / manual pass): a live visual check of the
> sticky rail at the ≤1024 collapse breakpoint, the dropdown `menu-pop` motion, and
> the grayscale spot-check of the chrome — quick to eyeball with
> `NEXT_PUBLIC_AUTH_DEV=true npm run dev`.

## What D3 can rely on

The shell is in place: both routes render full-bleed on the field, the chrome
(header, rail, identity menus) is Kamino, and the inner content region (`<main>`
with 3u gutters) is the next conversion target. D3 converts the index surface (hero
→ a modest console title, the metric tiles → metric-readout bays, the project grid
→ bracketed `Bay` cards, the panel states → `AwaitingState`).
