# `Account` owns `Actor` — Phase 8 Completion (Frontend: types + identity hook)

> Implements **Phase 8** of `docs/executing/account-owns-actor-implementation-plan.md`. Mirrors the
> backend's account-owns-actor shape in the TS types and re-sources the one role read through the
> nested account. The hook's public contract is unchanged, so the consuming components
> (`auth-menu`, `funding-panel`) are insulated — exactly as the plan predicted.

**Status:** ✅ **GATE GREEN.** `npm run typecheck` / `lint` / `build` all clean; **6/6** routes
generate; bundle sizes within noise of `0.6.10` (type-only + one field-name change, no new
dependency).

**Files:** `src/types/research.ts`, `src/lib/use-identity.ts`, `src/lib/api.ts` (comment),
`src/components/workspace/funding-panel.tsx`.

---

## What landed, where, and why

### A8.1 — `types/research.ts`: the account-owns-actor shape

- **`Actor`** loses `external_id` and `roles`; gains `account_id: string | null` (the owning
  principal; null for system/dev/unlinked actors). Mirrors the backend `ActorRead`.
- **New `Account`** (`id`, `external_id`, `display_name`, `email`, `roles`, timestamps) mirroring
  `AccountRead`, and **new `AccountSummary`** (`id`, `display_name`) mirroring the privacy-safe
  funder summary.
- **`Me`** becomes `Actor & { account: Account | null }` — the nested view `/me` serializes
  (`MeRead`).
- **`Funding`** funder moves `actor_id`/`actor: ActorSummary` → `account_id`/`account:
  AccountSummary` (Decision #5). `ActorSummary` is **retained** — it still types checkpoint `author`
  and validation `actor`, both unchanged.

### A8.2 — `use-identity.ts`: roles from the nested account

`const roles = me?.roles ?? []` → `me?.account?.roles ?? []`. The hook's public shape
(`{ displayName, isInternal, canWrite, roles, ... }`) is **byte-identical**, so `isInternal =
roles.includes("internal")` and every consumer keep working without edits. An account-less actor
(dev/unlinked) yields `roles = []` → `isInternal = false`, the correct default.

### A8.3 — funder display + the `api.ts` comment

- `funding-panel.tsx`: the history row funder label reads `item.account?.display_name` (was
  `item.actor`). The funder summary is privacy-safe (no email), matching the backend.
- `lib/api.ts` `getMe` comment updated ("plus its owning account; roles live on the account in
  0.7.0").

### A8.4 — `dev-actor-provider.tsx`: confirmed unaffected (no edit)

It only ever attaches the actor id as `X-Dev-Actor-Id`; it reads no roles/external_id/account. `/me`
resolves the actor **and** its account, so `isInternal` reflects the linked account for free. To
exercise funding locally, bootstrap an internal `Account` via `POST /accounts` and link a dev actor
to it (`account_id`) — the dev path then resolves the role through `actor.account` (as the Phase 7
`internal_funder` fixture does).

## Gate verification (reproduced, not asserted)

```
$ npm run typecheck   → tsc --noEmit, clean
$ npm run lint        → eslint ., clean
$ npm run build       → ✓ 6/6 routes generated; /projects/[projectId] 8.58 kB (196 kB first load)
```

A grep for stale reads (`actor.external_id` / `me.roles` / funding `.actor`) across `src/` is clean;
`ActorSummary` remains referenced only by checkpoint `author` and validation `actor`.

## Owed to Phase 9

- **Live verification** that the deployed frontend reads `me.account.roles` correctly (the internal
  badge for an allowlisted email; the funding panel gated to internal; the funder shown as the
  account in history). The frontend redeploy (Vercel) is part of the A9.2 cutover — `NEXT_PUBLIC_*`
  and these types are baked at build, so it must redeploy after the backend cutover.

## Gate result

**typecheck / lint / build green, 6/6 routes, hook contract unchanged → Phase 8 gate is GREEN.**
Proceed to Phase 9 (round-trip, cutover, changelog).
