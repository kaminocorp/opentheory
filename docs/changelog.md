# Changelog

## Index

- `0.6.10` — Post-review polish on the `0.6.9` email + password sign-in (no backend, schema, API, or migration). An independent re-audit confirmed the **frontend-only / backend-blind** claim against source — the JWT verifier asserts only signature/audience/`exp`/`sub` and never reads `amr`/`aal`, so a password session is byte-indistinguishable from a magic-link one — and reproduced the build gates, then closed three auth-form hygiene gaps in the new menu markup: the plaintext **password lingered in component state** and re-displayed after sign-out (now cleared on success *and* on sign-out), the primary "Sign in" had **no in-flight guard** (now uses `Action`'s `pending` prop + a re-entry guard, blocking double-submit), and the **error line wasn't announced** to assistive tech (now `role="alert"`, matching the `awaiting-state` a11y idiom). Frontend `typecheck` / `lint` / `build` green (6/6 routes, bundle byte-identical); backend untouched (`9 passed, 47 skipped`).
- `0.6.9` — **Email + password sign-in**, now the primary method. A correct credential signs in **in-band** (no email round-trip, no redirect) by authenticating against existing Supabase `auth.users` rows; magic-link and Google are **retained** below it. Frontend-only: the backend verifies a Supabase session JWT and is blind to *how* the session was obtained, so **no** backend, schema, API, or migration change (the `ActingActor` contract, JIT-provisioning, and `internal`-role logic apply verbatim). Two files change — `auth-provider.tsx` exposes `signInWithPassword`, `auth-menu.tsx` leads with the password form. The only non-code step is the out-of-band Supabase prereq (admin-provision users with passwords). Frontend `typecheck` / `lint` / `build` green (6/6 routes); backend untouched (`9 passed, 47 skipped`).
- `0.6.8` — Post-review hardening on the `0.6.x` auth/funding + Kamino slice (no features, schema, or migration). An independent re-audit verified the security/money core (HS256-pinned JWT, the actor PII gate, native-only/internal-gated funding, single-chokepoint atomicity) sound, then closed the punch-list it surfaced: a **recurrence** of the `cn`-no-`tailwind-merge` footgun in the branch-bar Fork toggle (which falsifies `0.6.7`'s "last footgun closed" claim), the conftest prod-wipe guard's empty/uppercase-host hole, and three untested security controls now defended in the **default DB-free suite** (the actor PII-leak gate had *zero* tests). Adds a hermetic `dbfree_client` fixture so a guard regression fails at the session boundary instead of connecting to the live DB; mutation-tested. (`9 passed, 47 skipped`; frontend `typecheck` / `lint` / `build` green.)
- `0.6.7` — Post-review hardening on the `0.6.4` Kamino Console (no features, schema, or migration). An independent re-audit of the full **D1–D6** conversion confirmed the **presentation-only / data-flow byte-for-byte** claim (diffed against the pre-redesign baseline) and the **Decision-4** opacity-channel contract (re-verified in the *emitted* CSS), then closed a small accessibility/robustness punch-list living in bespoke markup: screen-reader-reachable inert command-rail zones, `aria-pressed` + a non-hue weight cue on the selected line pill, an accessible name for every console field (placeholder→`aria-label` fallback + six named `Select`s), an `Action` `size` prop that retires a `className` padding override (the `cn`-no-`tailwind-merge` footgun), and a `--state-fail` retune so error-red separates from the crimson `--signal` by value, not just name. Frontend `typecheck` / `lint` / `build` green; `md`-button output byte-identical.
- `0.6.6` — Post-review hardening on the `0.6.4` Kamino **primitive library** (no features, schema, or migration). Fixes a token-layering bug in the `Action` primitive that left every **disabled / pending** button's inert styling decided by CSS source order — plain `cn` has no `tailwind-merge`, so the inert override and the variant's own colour utilities both emitted — by splitting each variant into mutually-exclusive **shape** / **skin** (enabled appearance unchanged). Also gives the command-rail's unavailable zones a screen-reader reason, not just a `title`. (`6 passed, 47 skipped`; frontend `typecheck` / `lint` / `build` green.)
- `0.6.5` — Post-review hardening on `4ca8be0` (the commit that bundled `0.6.3` browser project-creation **and** the `0.6.4` Kamino redesign). Adds the missing **direct** regression test for the `0.6.3` auth gate (`POST /projects` unauthenticated → `401`, DB-free so it runs in the default suite), an `aria-live`/`role` announcement on the console error/loading state, and a stale-version comment fix. No features, schema, or migration. (`6 passed, 47 skipped`.)
- `0.6.4` — Frontend redesign to the **Kamino Console** design language: a warm-obsidian command bridge — recessed instrument **bays**, registration brackets, IBM Plex Mono readouts / Plex Sans prose, "square is built / round is alive", hairlines not boxes, themed by a single seldom-used crimson **signal**. Presentation-only (**no** backend / schema / API / data-flow change); shipped as six deployable phases **D1–D6**. Adds the Plex fonts, no new runtime dependency, no migration.
- `0.6.3` — Project creation from the browser + closing the last open write path. A write-gated "New project" form on the index (the first UI to create a project; auto-derived editable slug), and `POST /projects` now requires a verified actor (was unauthenticated). No schema, no migration. (`52 passed`.)
- `0.6.2` — Second pre-prod review hardening on `0.6.0`/`0.6.1` (no features, schema, or migration). Closes the funding write path against `source=stripe` (now native-only until `0.7.0`; `422` otherwise), stops a stale `X-Dev-Actor-Id` leaking in production, and first runs the DB-test gate on a real Postgres (`52 passed`).
- `0.6.1` — Pre-prod review hardening on `0.6.0` (no features, schema, or migration). Two security fixes: closes an unauthenticated PII leak (`GET /actors` exposed every actor's email and roles — now dev-gated) and an open redirect (CWE-601) in `/auth/callback`. Hardens the test harness against a stray `DATABASE_URL` wiping production.
- `0.6.0` — Authentication and funding. A verified Supabase JWT (`Actor.external_id`, JIT-provisioned, queryable `roles`) replaces the unverified `X-Dev-Actor-Id` header, preserving the `ActingActor` contract. Activates `FundingAllocation` as a source-aware, contribution-only write (native gated to `internal`) that mints no checkpoint. Migrations `0004`, `0005`.
- `0.4.8` — First live deployment: the FastAPI backend on Fly.io and the Next.js frontend on Vercel, both against the live Supabase DB, as an open (no-auth) preview. Adds the deploy scaffolding (Dockerfile, `fly.toml`, runbook) and documents the production connection shape. No app code, schema, or migration change.
- `0.4.7` — Developer convenience: a root `Makefile` wrapping the common backend (`uv`) and frontend (`npm`) tasks — `make dev`, `make migrate`, `make test`, `make fe`, etc. No app code, schema, or behavior change.
- `0.4.6` — First live database: provisioned the managed Postgres, applied migrations `0001→0003`, and hardened the connection config for a pooled cloud Postgres (app over the transaction pooler, Alembic over a direct connection). No new features or schema.
- `0.4.5` — Post-`0.4.0` review fixes: order-aware claim `signal` (a contradiction after a retract re-contests), corrected a stale overview-counts test that would have failed on a live DB, sealed-branch recording UX, typed the checkpoint ref validator, and removed dead frontend exports. No new features, schema, or migration.
- `0.4.4` — Read-model enrichment + polish: claim validation history with a derived `signal`, project overview branch/validation counts + contradictions summary, per-branch checkpoint counts, and the workspace surfaces for all of it. Completes `0.4.0`.
- `0.4.3` — Frontend validation + branch surfaces: record validations on claims/checkpoints, a branch bar that forks/closes and scopes the ledger timeline, and contradiction indicators. Third phase of `0.4.0`.
- `0.4.2` — Branch write path: fork from a checkpoint, record checkpoints on a branch, close as dead-end/superseded — all through the checkpoint chokepoint; adds `checkpoints.branch_id` (migration `0003`). Second phase of `0.4.0`.
- `0.4.1` — Validation write path: record an immutable assessment of a claim/checkpoint/branch through the checkpoint chokepoint, attributed by a `validate` contribution. First phase of `0.4.0`.
- `0.3.4` — Enriched ledger read models: project aggregate counts, per-thread claim counts, and a checkpoint timeline showing author, action, and referenced claims/evidence. Completes `0.3.0`.
- `0.3.3` — Three-panel research workspace (threads / claims+evidence / checkpoint timeline) wired to all create/read flows, plus a localStorage-backed dev-actor switcher attached as `X-Dev-Actor-Id`.
- `0.3.2` — Checkpoint service as the sole append-only ledger write path, ORM-enforced append-only on checkpoints/refs/funding, and automatic contribution recording for all four create flows.
- `0.3.1` — Backend write path for threads, claims, and evidence, plus dev actors, two join tables, and the first real Alembic migration.
- `0.2.0` — Added the initial Next.js frontend scaffold with Tailwind, TanStack Query, typed API client, project index, and project detail surfaces.
- `0.1.0` — Added the initial FastAPI backend scaffold, domain model foundation, Alembic setup, and smoke-test tooling.

---

## 0.6.10

A post-review polish pass on the `0.6.9` email + password sign-in, in the lineage of the
`0.6.5`–`0.6.8` hardening passes. An independent re-audit read the two `0.6.9` files and every
file they lean on — the backend JWT verifier (`core/auth.py`), the `Action`/`Input` console
primitives, the `cn` helper, and `use-identity.ts` — and **reproduced** the frontend build gates
rather than trusting the completion doc. The core held: the **frontend-only / backend-blind** claim
is true (the verifier asserts only signature, audience, `exp`, and `sub`, and never reads `amr`/`aal`,
so a password session is byte-indistinguishable from a magic-link one); the `Action className="w-full"`
usage is safe under plain-`clsx` `cn` (no `tailwind-merge`, and neither `BASE` nor `SHAPE` sets a
width, so nothing double-emits); and the password path resolves a session in-band and never touches
the open-redirect-hardened `/auth/callback`. It surfaced three auth-form hygiene gaps — all in the
new `auth-menu.tsx` markup, none a correctness bug — fixed here. **No** backend, schema, API, or
migration change; backend behaviour unchanged.

### Security / hygiene — the secret no longer lingers in component state

- **The plaintext password is cleared on successful sign-in and on sign-out.** `AuthMenu` never
  unmounts, so the `password` state survived a successful sign-in — and because the signed-out
  branch renders `value={password}`, signing out and reopening the menu **pre-filled the previous
  password** (masked, but recoverable via devtools / a field-type toggle), a real hygiene gap on a
  shared machine. `handlePasswordSignIn` now clears it on success and `handleSignOut` clears it on
  the identity change. (`email` is deliberately retained so a sign-out/retry doesn't force a re-type.)

### Robustness — no double-submit on the primary path

- **The "Sign in" submit now reflects its in-flight state and is single-shot.** The button stayed
  enabled during the `await` and the handler wasn't re-entrant, so rapid clicks fired multiple
  `signInWithPassword` calls. Added a `submitting` flag: `handlePasswordSignIn` returns early while a
  request is in flight (re-entry guard, `try/finally`), and the button takes `Action`'s purpose-built
  `pending` prop — the inert hatched fill, which also sets `disabled`. The secondary magic-link /
  Google paths are unchanged (separate flows; a successful submit closes the menu).

### Accessibility — a failed sign-in is heard, not just seen

- **The error line is now a `role="alert"` live region.** It was a plain `<p>`, so a screen-reader
  user got no announcement when the *primary* sign-in path failed. It now carries `role="alert"`
  (which implies `aria-live="assertive"` and is announced on DOM insertion) — matching the exact
  idiom `awaiting-state.tsx` set in `0.6.5` ("`role` implies the matching `aria-live`"), so no
  redundant `aria-live` attribute and no layout cost when there is no error.

### Verification (reproduced, not asserted)

- **Frontend:** `npm run typecheck` / `lint` / `build` all clean; **6/6** routes generate; bundle
  sizes **byte-identical** to `0.6.9` (the edits are state + attributes, no new dependency).
- **Backend:** untouched — no file changed, so the `9 passed, 47 skipped` default DB-free suite and
  the JWT `401`-matrix / JIT-provision coverage remain authoritative and method-agnostic (nothing to
  re-run).
- **Still not done here:** the live in-browser manual acceptance pass (real Supabase + an
  admin-provisioned password user), carried over from `0.6.9` — the one acceptance step that needs a
  browser, and the actual gate on the production push.

### Still gating the production push (unchanged from `0.6.3`–`0.6.9`)

- **Redeploy Vercel** for the sign-in UI (`NEXT_PUBLIC_*` is baked at build). No Fly redeploy is
  required *for this change* (backend untouched), though the `0.6.3`+ backend changes still gate the
  overall push.
- **Confirm Supabase** — password sign-in enabled on the Email provider; target users
  admin-provisioned with confirmed passwords.

---

## 0.6.9

Email + password becomes the **primary** sign-in method, authenticating directly against
existing Supabase `auth.users` rows (GoTrue) via `signInWithPassword`. A correct credential
resolves a session **in-band** — no email round-trip, no redirect — and signs the user in
immediately; magic-link and "Continue with Google" are **retained** as secondary options below
the password form. A small, additive, **frontend-only** feature.

### Why it's frontend-only (no backend change)

`core/auth.py::verify_bearer_token` verifies only a bearer JWT's signature, audience
(`aud="authenticated"`), and expiry, then reads `sub`/`email`/`user_metadata`. Supabase issues
the **same** HS256 session token for every sign-in method, so magic-link, OAuth, and
`signInWithPassword` are indistinguishable to the verifier once a session exists. Adding an
auth *method* on the IdP side is invisible to the backend: `core/auth.py`, `api/deps.py`,
`models/actor.py`, `api/routes/me.py`, and every service are **untouched**, and the
`ActingActor` contract, JIT-provisioning, and `internal`-role logic apply verbatim. No env var,
schema, or migration.

### What changed (two files)

- **`providers/auth-provider.tsx`** — exposes `signInWithPassword(email, password)` on the auth
  context, returning the existing `SignInResult` shape so the menu treats all methods uniformly.
  On success the provider's existing `onAuthStateChange` subscription pushes the token into
  `lib/api.ts` and updates `session` — no new wiring. `useMemo` deps unchanged (only `supabase`
  is captured, already listed).
- **`shell/auth-menu.tsx`** — the signed-out dropdown now leads with an email + password
  `<form>` (Enter-to-submit, full-width `Action` "Sign in" disabled unless both fields are
  filled), then a divider, then "Email me a magic link" and "Continue with Google". Both fields
  carry explicit `aria-label`s and correct `autoComplete` (`username` / `current-password`). The
  email field is shared with the magic-link button; the `sent` confirmation flow stays scoped to
  magic-link. The signed-in branch and click-outside behaviour are unchanged.

### No-change surface (audited, not edited)

`lib/api.ts` (method-agnostic token attach), `lib/use-identity.ts` (`isAuthed = Boolean(session)`,
rest from `/me`), `app/auth/callback/route.ts` (only magic-link/OAuth reach it — the password
path returns a session synchronously and never touches the open-redirect-hardened callback, so
no new CWE-601 surface), `lib/supabase.ts`, `providers/dev-actor-provider.tsx`, and the entire
`backend/` — all confirmed untouched (grep: no `signInWith*` references in the audited files).

### Out of scope (deliberate)

Self-service sign-up, password-reset / "forgot password" UI, any backend change/test/schema/
migration, server-side rate-limiting (relying on GoTrue's built-in limits), and removal of the
retained magic-link / Google paths.

### Prerequisite (config, not code)

The only non-code step is out of band on the live Supabase project: enable password sign-in on
the Email provider, and **admin-provision** users with passwords (dashboard "Add user" or
`auth.admin.createUser({ email, password, email_confirm: true })`). A magic-link-only user has
no password and keeps using magic-link until an admin sets one.

### Verification (reproduced, not asserted)

- **Frontend:** `npm run typecheck` / `lint` / `build` all green; **6/6** routes generate.
  `git diff --stat` confirms exactly the two intended files changed.
- **Backend:** untouched — no file changed, so the `9 passed, 47 skipped` default DB-free suite
  and the JWT `401`-matrix / JIT-provision coverage remain authoritative and method-agnostic
  (not re-run; nothing to re-run).
- **Not done here:** the live in-browser manual pass (real Supabase + an admin-provisioned
  password user) — the one acceptance step that needs a browser. Detailed in
  `docs/completions/email-password-login.md`.

### Still gating the production push (unchanged from `0.6.3`–`0.6.8`)

- **Redeploy** — Vercel for the new sign-in UI (`NEXT_PUBLIC_*` is baked at build). No Fly
  redeploy is required *for this change* (backend untouched), but the `0.6.3`+ backend changes
  still gate the overall push.
- **Confirm Supabase** — password sign-in enabled on the Email provider; target users
  admin-provisioned with confirmed passwords.

---

## 0.6.8

A post-review hardening pass in the lineage of `0.6.5`/`0.6.6`/`0.6.7`, scoped to the whole
`a70fd8f..HEAD` body (the `0.6.0` auth+funding slice, the `0.6.3` browser project-creation +
auth gate, and the `0.6.4` Kamino redesign). The security- and money-critical backend was read
directly and the frontend covered by parallel reviewers; every verification claim was re-run, not
trusted. The core held: HS256 is algorithm-pinned with `exp`/`sub` required and audience checked;
both `GET` and `POST /actors` are gated in production; funding is native-only + internal-gated with
`stripe`→`422`, positive-amount, single-transaction atomicity; the redesign's "presentation-only /
data-flow byte-for-byte" claim is true and carries no security regression. It surfaced one
shipping-code defect and a cluster of test gaps — all in markup or test harness the by-construction
audits don't reach — fixed here. No features, schema, or migration; backend behavior unchanged.

### Correctness — the `cn`-no-`tailwind-merge` footgun recurred

- **`workspace/branch-bar.tsx` Fork toggle no longer layers conflicting utilities.** The compact
  Fork button used `<ActionGhost className="h-7 px-3 text-[12px]">`, but `ActionGhost` defaults to
  `size="md"`, which already emits `px-[18px] py-2 text-[13px]`. With no `tailwind-merge`, both
  `px-*`/`text-*` pairs emitted and CSS source order silently won for the variant — so the override
  was dropped and the button rendered at full `md` size (and `h-7` fought `py-2`). This is the exact
  bug `0.6.6` fixed in the `Action` primitive and `0.6.7` fixed for the "Fund project" toggle — the
  Fork toggle was missed, so `0.6.7`'s claim that the `size` prop "closed the last footgun" was
  false. Fixed to `<ActionGhost size="sm" className="h-7">`: `sm` resolves to the intended
  `px-3 py-1 text-[12px]` with no double-emit, and the button now renders compact, matching its
  sibling Close control. (Every other `Action` consumer was re-audited and is clean — the remaining
  `className` overrides are `w-full`, which `BASE` never sets.)

### Test-harness safety

- **The conftest prod-wipe guard no longer treats an empty/uppercase host as localhost.**
  `_LOCAL_DB_HOSTS` included `""`, and `make_url(url).host or ""` coerces a host-less (socket-form)
  `DATABASE_URL` to `""` — so such a URL was accepted by the `DROP SCHEMA public CASCADE` fixture.
  The check was also case-sensitive (`LOCALHOST` wrongly rejected). Dropped `""` (an empty host is
  not proof of localhost; it now fails safe) and lowercased the host before the membership test.
  Real Supabase URLs always carry a host, so this closes a narrow hole in a guard whose only job is
  to be airtight. (`tests/conftest.py`.)

### Tests — the security controls are now *defended*, not just present

- **The actor PII-leak gate had no regression test.** The `0.6.1` fix gates `GET /actors` behind
  `auth_dev_header_enabled` because `ActorRead` exposes `external_id` + the verified email + `roles`;
  removing the guard re-opened an anonymous email-harvest — and failed **zero** tests (only `POST`
  was covered, and only in the DB-backed suite that skips without Postgres). New `tests/test_actors.py`
  adds DB-free `GET` and `POST` gate tests that run in the default suite. **Mutation-verified:** with
  the `GET` guard removed the test fails (and, before the hermetic fixture below, returned a live
  `200` actor list — the leak itself).
- **A DB-free auth-gate test for the funding write path.** The funding `401`/`403`/`422` gates lived
  only in `test_funding.py` (DB-skip). Added `test_unauthenticated_funding_create_is_rejected` to the
  default suite (the `403`/`422` gates fire only after the actor + project row resolve, so they stay
  DB-backed — noted, not silently dropped). (`tests/test_projects.py`.)
- **`test_wiring.py` refreshed.** `WRITE_PATHS` gained `/projects` and `/projects/{id}/funding` (the
  two endpoints whose auth gate is new this release), so the header-declaration check now covers them;
  `test_actor_create_is_open` — which asserted the *retired* pre-`0.6.1` open-bootstrap posture — was
  corrected to `test_actor_create_takes_no_acting_actor` with the real rationale (flag-gated, 404 in
  prod). Removes a false-confidence assertion.

### Test isolation — DB-free tests are now hermetic

- **Added a poison-session `dbfree_client` fixture.** The route-level gate tests use a plain
  `TestClient`, which bypasses conftest's `TEST_DATABASE_URL` guard (that only protects the
  `DROP SCHEMA` fixture) and falls through to the app's real `get_db` → `settings.database_url`. In
  this live-verify setup that URL is **production**, so a guard regression would connect there (a
  read, but still). The new fixture overrides `get_db` with an `_UnusableSession` that raises on any
  use, so a regression fails loudly at the session boundary and the tests touch no database at all.
  All four DB-free gate tests route through it. **Mutation-verified:** guard removed → fail at
  `session.execute`, never a connection.

### Considered and deliberately not done

- **Mixed-currency budget summation (`funding.py`)** and the **`payment_reference` append-only trap**
  were re-confirmed as latent `0.7.0` concerns (native/USD-only and no write path today), not fixed
  here — fixing either is in scope for the Stripe-settlement release, not a presentation/test pass.
- **No `alg:none`/algorithm-confusion test** was added: the control is the `algorithms=["HS256"]`
  allowlist (PyJWT rejects `none`/RS256), and the forged-secret case is already in the `401` matrix.

### Verification (reproduced, not asserted)

- **Backend:** `ruff check .` clean; `pytest` → **`9 passed, 47 skipped`** (3 new security tests
  *executing* in the default DB-free suite, up from 6; the DB-backed suite still skips cleanly without
  a configured Postgres, per policy). Both new guards mutation-tested (fail-if-removed, and hermetic).
- **Frontend:** `typecheck` / `lint` / `build` clean; 6/6 routes generate; the `md`-size `Action`
  output is unchanged — only the Fork toggle's emitted classes change (now the intended compact set).

### Still gating the production push (unchanged from `0.6.3`–`0.6.7`)

- **Redeploy both tiers** — Fly (the `POST /projects` auth gate ships in the backend) **and** Vercel
  (the Kamino UI; `NEXT_PUBLIC_*` is baked at build).
- **Confirm Fly secrets** — `SUPABASE_JWT_SECRET` set, `AUTH_DEV_HEADER_ENABLED` unset/false,
  `INTERNAL_ACTOR_EMAILS` populated before internal users first sign in.
- **Live visual pass** — desaturate the deployed preview (grayscale test) and toggle reduced-motion.

---

## 0.6.7

A post-review hardening pass on the `0.6.4` Kamino Console, in the lineage of `0.6.5`/`0.6.6`. An independent re-audit of the entire `adba55a..HEAD` frontend conversion — the **presentation-only / data-flow byte-for-byte** claim diffed component-by-component against the pre-redesign baseline, the **Decision-4** opacity-channel contract re-verified in the *emitted* production CSS (not just a green build), the console primitive library re-checked for the `cn`-no-`tailwind-merge` conflicting-class bug class that `0.6.6` fixed, and the three release gates (honesty/grayscale, signal-seldom, motion/reduced-motion) walked on the real markup — found the slice **sound**: zero data-flow change (every query key, mutation, invalidation, route, and write-gate preserved; `use-identity.ts` and `providers/` literally untouched), the opacity contract holding, the `Action` shape/skin fix correct and not recurring in any other primitive, and signal-seldom + reduced-motion + focus-ring + aria-live all holding. It surfaced a small accessibility/robustness punch-list — all in **bespoke markup** that the "by construction" audits structurally don't reach — fixed here. **No** new features, schema, or migration; backend untouched.

### Accessibility

- **Console fields now carry a real accessible name.** The console UI is deliberately label-less, so most `Input`/`Textarea` controls were *placeholder-only* — and a placeholder is not reliably announced as a control's name and disappears on input. `Input`/`Textarea` now fall back to the visible `placeholder` as their `aria-label` when the caller supplies neither `aria-label` nor `aria-labelledby` (a central fix, zero call-site churn). `Select` has no placeholder to borrow, so the six enum pickers (validation outcome, funding kind, claim kind, evidence relation, fork-from-checkpoint, close-outcome) gained explicit `aria-label`s. (`console/input.tsx` + the six call sites.)
- **The command rail's unavailable zones are reachable by screen reader.** The contextual-off (Workspace / Funding off-project) and inert (Agents → `0.7.0`) zones rendered as a *non-focusable* `<span>`, so a user navigating *by control* skipped past the "coming soon" / "open a project first" reason `0.6.6` had folded into the icon's label. They are now `role="link" aria-disabled="true" tabIndex={0}` with the name on the focusable wrapper (the icon demoted to decorative) — present-and-inactive in the accessibility tree, never actionable (no href/handler). (`shell/command-rail.tsx`.)
- **The selected branch line pill no longer signals selection by colour alone.** `LinePill` distinguished *selected* only by crimson text + a same-width signal border — near-indistinguishable under grayscale and unexposed to assistive tech. It now carries `aria-pressed` and a **non-hue weight cue** (`font-semibold` when selected), so selection survives the §1 grayscale test. (`workspace/branch-bar.tsx`.)

### Correctness / robustness

- **`Action` gained a `size` prop, closing the last `cn`-no-`tailwind-merge` footgun.** The compact "Fund project" toggle overrode the ghost button's padding/text via `className="h-7 px-3 text-[12px]"`, which — with no `tailwind-merge` — *double-emitted* `px-*`/`text-*` against the base and resolved by CSS source order, the same hazard class `0.6.6` fixed in the inert skin, here rendering correctly only by luck. `Action` now takes `size: "sm" | "md"` (default `md`): text-size is pulled out of `BASE` into a per-size token and the per-variant SHAPE is size-keyed, with `sm`/`md` SHAPE mutually exclusive so padding never doubly-emits. The `md` path resolves to a **byte-identical** class set (every existing button visually unchanged); the funding toggle switched to `size="sm"` and dropped the override. (`console/action.tsx`, `workspace/funding-panel.tsx`.)

### Design token

- **`--state-fail` separated from `--signal` by value, not just name.** §9.2 promises the state ramp is independent of the swappable `--signal` so a re-skin "never makes failed ambiguous" — but the *default* `--state-fail` (`201 81 75`) was perceptually almost the same crimson as `--signal` (`201 90 90`). Retuned to `196 64 58` — a deeper, more saturated true-red that separates by saturation **and** luminance (the channel the grayscale gate actually reads), while staying clearly "error red" and distinct from `--state-warn` amber. Independence is now perceptual, not only structural. (`globals.css`.)

### Considered and deliberately not done

- **No runtime "missing accessible name" warning in the field primitives.** A field can be named by a wrapping / `htmlFor` `<label>` the component cannot see, so a runtime check would false-positive on legitimately-labeled fields. The placeholder→`aria-label` fallback plus a JSDoc contract is the robust fix; an unenforceable runtime warning was rejected. (`console/input.tsx`.)
- **`run` and `signal` keep the shared `●` glyph.** They are the one tone pair distinguishable only by colour, but they never render adjacently in product UI (only the dev `/styleguide` legend) — unchanged from the `0.6.6` rationale.
- **The `PanelEmpty` icon-prop removal and the dead "Fund project" index-button removal** (both inherited from the D1–D6 conversion) were reviewed and **kept**: the terse `AwaitingState` one-line readout is the §5.9 treatment, and the removed button never had a handler.

### Verification (reproduced, not asserted)

- **Frontend:** `npm run typecheck` / `lint` clean; `npm run build` success, all 6 routes generate (`/styleguide` → 404 shell in prod). **Decision-4 opacity contract re-verified in the emitted CSS** (`rgb(var(--signal)/.1)`, `rgb(var(--state-ok)/.15)`, `rgb(var(--text)/.7)` all resolve); `--state-fail: 196 64 58` and `--signal: 201 90 90` confirmed separated in the shipped stylesheet; `aria-pressed` present in the client bundle. The `md`-size class set is byte-identical to pre-`0.6.7`, so no existing button changed.
- **Backend:** untouched.
- **Not re-run here:** the DB-backed suite (no backend or test change in this slice) and the live in-browser desaturation + reduced-motion pass (needs a real browser — the one acceptance step no headless build can perform).

### Still gating the production push (unchanged from `0.6.3` / `0.6.4` / `0.6.5` / `0.6.6`)

- **Redeploy both tiers** — Fly (the `0.6.3` `POST /projects` auth gate) **and** Vercel (the Kamino UI; `NEXT_PUBLIC_*` is baked at build).
- **Confirm Fly secrets** — `SUPABASE_JWT_SECRET` set and `AUTH_DEV_HEADER_ENABLED` unset/false.
- **Live visual pass** — desaturate the deployed preview (grayscale test) and toggle reduced-motion.

---

## 0.6.6

A post-review hardening pass on the `0.6.4` Kamino Console **primitive library** (the `console/` component layer added in `4ca8be0`). An independent re-read of the full `adba55a..HEAD` push — the `0.6.3` `POST /projects` auth gate read directly, the ~3,500-line reskin diffed file-by-file against the deployed baseline to confirm the **presentation-only** claim, the channel/opacity token contract checked in the emitted CSS — found the slice sound: zero data-flow changes to any query, mutation, write-gate, or branch-line filter; the auth gate correctly placed in the dependency layer; no legacy tokens or dangling imports. It surfaced one real correctness bug in a shared primitive and one accessibility gap, both fixed here. No new features, no schema change, no migration; backend untouched.

### Correctness — the inert button state was decided by CSS source order

- **`console/action.tsx` no longer layers conflicting Tailwind utilities.** The disabled / pending ("inert") override was appended *after* the per-variant classes, so a disabled button carried both the variant's own colour utilities (`bg-signal` + `text-ground` for `primary`; `border-state-fail` + `text-state-fail` + `hover:bg-state-fail/10` for `destructive`) **and** the inert ones (`bg-transparent` / `text-text-faint` / `hover:bg-transparent`) at once. Because `cn` is plain `clsx` with **no `tailwind-merge`**, which class wins is decided by the order Tailwind emits the rules in the stylesheet — *not* by className order — so the hatched/faint inert look was correct only by luck and could render a disabled button looking enabled. This governs the disabled state of nearly every submit button (Create project, Record checkpoint, Fund, record-validation, …) and the destructive Close-branch button (`branch-bar.tsx`). Fixed by splitting each variant into **`VARIANT_SHAPE`** (padding + border-*presence*, always applied so an inert button never changes size) and **`VARIANT_SKIN`** (colour / border-colour / hover, interactive only); the inert state now selects a single `INERT_SKIN` *instead of* the variant skin via a ternary, so no two conflicting utilities ever coexist. The enabled appearance is byte-identical per variant (same resolved class set) — verified by `build`. This restores the invariant `cn.ts` documents but cannot enforce: *primitives must never produce conflicting Tailwind classes.*

### Accessibility — honest unavailable zones for screen readers

- **`shell/command-rail.tsx` folds the unavailability reason into the accessible name.** The inert `Agents` zone (honest about `0.7.0`) and the contextual-off `Workspace` / `Funding` zones (live only inside a project) signalled "unavailable" only through the `title` tooltip — a sighted-hover affordance that assistive tech does not reliably announce. The zone's accessible name (the `Icon`'s `aria-label`) now carries the reason: `"Agents, coming soon"` / `"Workspace, open a project first"`. Extends the blueprint's §1 honesty surface to SR users, matching what `0.6.5` did for `AwaitingState`. Presentation-layer only; the live zones' names are unchanged.

### Considered and deliberately not done

- **The terser `AwaitingState` empty / error copy is by design, not a regression.** The reskin shortened several panel empty-states (e.g. the checkpoint panel lost its instructional *"Record one after a meaningful move — proposing a hypothesis, attaching evidence, or validating a result…"* second sentence, now just *"No checkpoints on the main line"*). `AwaitingState` (§5.9) is a **one-line mono-uppercase readout**; the old prose cannot fit it and would fight the console language. No data flow changed, so this stays inside the `0.6.4` presentation-only claim — recorded here so the loss of some first-run onboarding guidance is a *decision*, not a silent drop.
- **The `run` and `signal` state tones share the `●` glyph (`console/state.ts`).** Left as-is: the collision only renders in the dev-only `/styleguide` tone showcase. In product the `signal` tone is consumed via `LiveDot` (background) and `ReadoutLabel` (text colour) — its glyph never renders beside a `run` glyph — so the §0 grayscale guarantee is not actually weakened on any shipped surface. Changing `run`'s glyph would alter live UI for marginal gain.
- **A reviewer flag on `MetricReadout`'s `valueClassName ?? "text-text"` was rejected on inspection.** The suggested "merge instead of replace" would, without `tailwind-merge`, emit two conflicting `text-*` utilities; the replace-on-override is the correct pattern for a plain-`cn` setup.

### Verification (reproduced, not asserted)

- **Frontend:** `npm run typecheck` / `lint` / `build` all clean; 6/6 routes generate; enabled-button appearance unchanged (identical resolved class set per variant).
- **Backend:** untouched — `ruff check .` clean, `pytest` → **`6 passed, 47 skipped`** (the default DB-free suite; the `0.6.5` auth-gate test still executing).
- **Not re-run here:** the DB-backed suite against a throwaway Postgres — unchanged since the `0.6.2` / `0.6.3` `52 passed` (this slice edits only two frontend files, no backend or test code), deferred per the no-local-DB policy — and the live visual desaturation pass (needs a browser).

### Still gating the production push (unchanged from `0.6.3` / `0.6.4` / `0.6.5`)

- **Redeploy both tiers** — Fly (the `POST /projects` auth gate) **and** Vercel (the Kamino UI; `NEXT_PUBLIC_*` is baked at build).
- **Confirm Fly secrets** — `SUPABASE_JWT_SECRET` set and `AUTH_DEV_HEADER_ENABLED` unset/false.
- **Live visual pass** — desaturate the deployed preview (grayscale test) and toggle reduced-motion.

---

## 0.6.5

A post-review hardening pass on commit `4ca8be0` — the single commit that bundled two changelog releases: `0.6.3` (browser project-creation + the `ActingActor` gate on `POST /projects`) **and** the entire `0.6.4` Kamino Console redesign (D1–D6). A full read-through of that 56-file diff (the channel-pattern token wiring, every re-skinned surface, the auth gate, and the test bootstrap) found the slice sound — all builds green, the presentation-only claim holding everywhere except the legitimately-documented create-project feature, and the auth gate correctly placed in the route layer — and surfaced three small items, all fixed here. No new features, no schema change, no migration.

### Commit-history note (the bundling)

- **`4ca8be0`'s message describes only `0.6.3`**, but its contents also include all of `0.6.4` (50+ frontend files: `globals.css`, `tailwind.config.ts`, the `console/` primitive library, every workspace-panel re-skin). The two releases are documented separately in this changelog (above), so nothing is *undocumented* — but a reader of `git log` alone would not see the redesign. The message was **not** amended because `4ca8be0` is already published on `origin/main`, and rewriting shared history is more harmful than the mislabel. **This entry is the cross-reference: the Kamino redesign lives in `4ca8be0`, not in a commit of its own.**

### Tests — a direct guard for the `0.6.3` auth gate

- **Added `backend/tests/test_projects.py`** with `test_unauthenticated_project_create_is_rejected`: with the dev-header fallback off (production posture), an unauthenticated `POST /api/v1/projects` returns `401`. This is the deliverable's missing regression test — until now the gate was only covered *transitively*. Every project-creation test goes through a `_project()` helper that **sends** a credential and asserts `201`, and all of them sit behind the DB-backed `client` fixture that **skips** without Postgres; so nothing exercised the *rejection* path, and removing the `ActingActor` dependency from `create_project` would not have failed a single test. The new test uses a plain `TestClient` (not the `client` fixture): the `ActingActor` dependency raises `401` **before** the handler touches the DB (`app/api/deps.py:117`), so it needs no database and **runs in the default suite** (`5 → 6 passed`), where it will catch a regression — including in a CI run with no Postgres.

### Accessibility — the honesty surface for screen-reader users

- **`AwaitingState` now announces state transitions** (`frontend/src/components/console/awaiting-state.tsx`). The error variant carries `role="alert"` (assertive) and the loading variant `role="status"` (polite); the steady empty state gets no live region. `role` implies the matching `aria-live`, so a read transitioning to error/failure is **heard** as well as seen — extending the blueprint's §1 honesty surface (failures as loud as successes) from the visual (glyph + `--state-fail` label, already present) to assistive tech. Pre-existing behaviour had no live region; this is additive and presentation-layer only.

### Correctness & hygiene

- **Fixed a stale version reference in `backend/app/api/routes/projects.py`.** The comment explaining why `create_project` records no `Contribution` pointed the deferred `services/projects.py` extraction at "`0.5.0`" — a version already past. Reworded to "the planned `services/projects.py` extraction (a later release)"; behaviour is unchanged (still no contribution recorded, preserving the unfiltered-`Contribution` test assertions).

### Verification (reproduced, not asserted)

- **Backend:** `uv run ruff check .` clean; `uv run pytest` → **`6 passed, 47 skipped`** (the new gate test *executing*, not skipping; the DB-backed suite still skips cleanly without a configured Postgres, per policy).
- **Frontend:** `npm run typecheck`, `npm run lint`, `npm run build` all clean; 6/6 routes still generate.
- **Not re-run here:** the full DB-backed suite against a throwaway Postgres (`52 passed` in the `0.6.2`/`0.6.3` passes) — unchanged by this slice — and the live visual desaturation + reduced-motion pass against the deployed preview (the one acceptance step needing a browser).

### Still gating the production push (unchanged from `0.6.3`/`0.6.4`)

- **Redeploy both tiers** — Fly (activates the `POST /projects` gate, the security half of `0.6.3`) **and** Vercel (the Kamino UI; `NEXT_PUBLIC_*` is baked at build). This is *not* a Vercel-only push, because the auth gate ships in the backend.
- **Confirm Fly secrets** — `SUPABASE_JWT_SECRET` set and `AUTH_DEV_HEADER_ENABLED` unset/false; project creation now hard-depends on a verified actor.
- **Live visual pass** — desaturate the deployed preview (grayscale test) and toggle reduced-motion; built to pass, confirmed on the artifact.

---

## 0.6.4

The first **non-functional** release: the entire frontend is converted from the old light "marble" posture into the **Kamino Console** design language (`docs/design_blueprint.md`) — a warm-obsidian command bridge of recessed instrument **bays**, registration-bracket precision, IBM Plex Mono readouts over Plex Sans prose, the "square is built / round is alive" shape grammar, hairlines instead of boxes, lit by structure rather than glow, and themed by a single seldom-used crimson `--signal`. This is **presentation-only**: every TanStack Query call, mutation, route, write-gate (`useActingIdentity`), and read schema is unchanged — the diff is tokens, fonts, structure, and the visual grammar of every component. The acceptance bar is the blueprint's §0 **grayscale test** — desaturated, the UI must still read as a measured instrument console, because identity lives in *form* (substrate, proportion, shape, line, type), not colour. Shipped as six deployable phases (`D1`–`D6`); full per-phase detail in `docs/completions/frontend-kamino-console-D1…D6-*.md`, plan in `docs/executing/frontend-kamino-console-redesign.md`. No new runtime dependency, no schema, no migration.

### Substrate + primitive library (D1)

- **Token layer rewired through the channel pattern.** The old palette (`ink`/`paper`/`line`/teal-`signal`/`ember`, `boxShadow.panel`) is gone; colours are stored in `:root` as space-separated RGB **channels** (`--panel: 22 21 19`) and consumed as `rgb(var(--x) / <alpha-value>)`, so every Tailwind `/opacity` modifier (`text-text/70`, `bg-signal/10`) survives (Decision 4 — verified in the emitted CSS, the one thing a green build doesn't prove). Radii become `built`(0)/`alive`(999)/`inset`(2); the state ramp (`ok`/`run`/`warn`/`fail`) is independent of `--signal` so a brand re-skin never makes "failed" ambiguous.
- **The measured field** (8px/64px graph-paper grid + registration crosshairs + ~3% grain + edge vignette) is baked once into `globals.css` and shows through gutters; opaque bays paint over it. **IBM Plex Sans/Mono** load via `next/font` (self-hosted, no FOUT).
- **`src/components/console/`** — the shape grammar defined once: `Bay`/`BayHeader`, `StatusPill` + the shared `STATE_META` (glyph + tone), `ReadoutLabel`, `RegistrationBrackets`/`Band`, `Action`(+`Ghost`/`Text`/`Destructive`), `Input`/`Select`/`Textarea`, `Icon` (a `lucide` wrapper enforcing the line language), `LiveDot`, `BrandMark`, `AwaitingState`, and (added in D4) `MetricReadout`.

### App shell + surfaces (D2–D5)

- **D2 — the app shell:** replaced the centered, header-only column with the full-bleed shell (§4.1): a 6u header (brand lockup + inert restyled search + identity slot) and a left **command rail** adapted to OpenTheory's zones (Projects / Workspace / Funding + a hatched, inert **Agents** zone honest about `0.7.0`). Active zone = a 2px `--signal` edge tick + a pulsing live dot, never a filled block. `site-header.tsx` retired.
- **D3 — project index:** hero demoted to a modest console title; the three tiles → a metric-readout bay; project cards → bracketed `Bay`s with `StatusPill` status; the three panel states → the breathing-mark `AwaitingState`.
- **D4 — workspace frame:** the project header → a chamfered, bracketed `Bay` with a `MetricReadout` count grid; **contradictions float above the counts at equal weight** (the honesty surface, §1); the budget panel → the money/metric showcase; the branch/line bar → round selectable pills + a *marked* (ring, not flooded) destructive close form.
- **D5 — the three instrument bays:** threads, claims + evidence, and the checkpoint timeline (§5.1–5.3), plus the shared validation vocabulary and panel-state helpers. Validation outcomes / evidence relations / claim signal all collapse onto `StatusPill` (glyph + label), so a `failed`/`contradicts`/`contested` state is structurally never dimmer than `passed`. Surface depth ramp: column `Bay` (`--panel`) → row sub-bay (`--panel-2`) → form tray.

### Motion, audits, polish (D6)

- **Liveness motion (§6):** a `bay-enter` fade + 8px lift cascades across grid children via a component-agnostic `.enter-stagger` class (index card grid + workspace instrument grid). Every animation (`anim-pulse`/`anim-breathe`/`menu-pop`/`enter-stagger`, + Tailwind's shimmer) is frozen under `prefers-reduced-motion`.
- **Accessibility:** a global `:focus-visible` ring renders the 2px `--signal` edge on buttons/links (console fields keep their inset focus tick); the mobile gutter steps `px-4 → sm:px-6`.
- **Release gates — pass by construction:** signal-seldom (crimson at rest only on active markers, selected state, the one internal badge, and the primary action per zone), honesty/grayscale (every `state-*` colour rides with a glyph or message text; failure top-floated at equal weight), reduced-motion. A final live devtools desaturation pass is the only step needing a browser.

### Verification

- Backend untouched. Frontend `npm run typecheck` / `lint` / `build` clean; all 6 routes generated (`/` and `/styleguide` static, `/projects/[projectId]` server-rendered on demand). Repo-wide grep confirms **zero** legacy tokens anywhere in `src` outside the dev-only `styleguide`; the Decision-4 opacity contract holds in the emitted CSS.

### Still gating the production push

- **Vercel redeploy only.** The change is entirely frontend; `NEXT_PUBLIC_*` is baked at build, so the live preview updates on a frontend redeploy. **No backend/Fly redeploy, no `alembic` step, no schema/migration.**
- **Interim brand mark.** `BrandMark` draws an original thin-line glyph (in the §7 drawing language) standing in for the real Kamino emblem — a one-file drop-in swap once the asset exists.
- **A live visual desaturation + reduced-motion pass** against the deployed preview is the remaining acceptance confirmation (built to pass; no code blocks it).

---

## 0.6.3

The project index gains the one create flow it never had — a "New project" form — and, in the same pass, project creation is brought under the same auth gate as every other ledger write. Until now `POST /api/v1/projects` took no acting actor: on the live (auth-enforcing) backend it was the **last open, unauthenticated write to the ledger root** — any caller could `POST` a project by direct request. Closing it is what makes "sign in, then create a project as yourself" real. No schema change, no migration.

### Security — closed the last open write path

- **`POST /api/v1/projects` now requires `ActingActor`.** It predated the `0.3.x` dev-actor model and never got the dependency, so on prod (where auth is enforced on threads / claims / evidence / checkpoints / validations / branches / funding) project creation *alone* stayed world-writable — a write-gated button would have been cosmetic over an open endpoint. Added the `ActingActor` dependency: a verified bearer token (or the dev header, local only) is now required; unauthenticated → `401`. (`app/api/routes/projects.py`.)
- **Deliberately *not* recorded as a `create_project` contribution yet.** Attribution-via-contribution is the `0.5.0` `services/projects.py` extraction's job; recording one here would also have broken the several DB-backed tests that assert on the *entire* `Contribution` set (unfiltered `select(Contribution)`). Gating is the security fix; attribution is a separate, planned provenance step. No `created_by` column added (none exists; none needed for the gate).

### Frontend — create a project from the browser

- **First UI to create a project.** `createProject()` + a `ProjectCreate` type added to the typed client; a write-gated "New project" form on the index (title, research question, and a slug that auto-derives from the title — `^[a-z0-9]+(?:-[a-z0-9]+)*$` — and stays editable for the unique-slug case). On success it invalidates the project list and routes to the new project. (`src/lib/api.ts`, `src/types/project.ts`, `src/components/projects/projects-section.tsx`, `src/app/page.tsx`.)
- **Replaced the dead "Fund project" placeholder** (a no-op button) with the working "New project" control; write-gating reuses `useActingIdentity().canWrite`, so an un-signed-in visitor sees the form disabled with the standard sign-in hint.

### Tests

- The seven project-creation helpers (`_project` / `_create_project` across `test_auth`, `test_funding`, `test_checkpoints`, `test_branches`, `test_read_models`, `test_validations`, `test_research_flow`) now bootstrap a dev actor and send `X-Dev-Actor-Id` (the dev path is on process-wide in tests); `test_unauthenticated_funding_rejected` was reordered to create its project *before* disabling the dev header. Coverage unchanged — still `52 passed`.

### Verification

- Backend `ruff` clean; the DB-backed suite executes green (**`52 passed`**, not skipping). Frontend `typecheck` / `lint` / `build` pass; `/` still prerenders static.

### Still gating the production push

- **Reaching prod needs a redeploy** — Fly (backend gate) and Vercel (the new UI; `NEXT_PUBLIC_*` is baked at build).
- **The Supabase login secrets are now load-bearing for the core flow.** Because project creation now requires a verified actor, if Fly's `SUPABASE_JWT_SECRET` or Vercel's `NEXT_PUBLIC_SUPABASE_URL` / `_ANON_KEY` are unset, *no one* can create a project (not even by direct API call). Confirm sign-in works end-to-end — and add the intended creator's email to `INTERNAL_ACTOR_EMAILS` *before* their first login if native funding is also wanted.

---

## 0.6.2

A second pre-production review pass on the `0.6.0`/`0.6.1` auth + funding slice — a full read-through of the working tree with every verification claim **re-run, not trusted**. The single highest-value outcome: the `0.4.0`/`0.6.0` DB-test gate (a suite that had only ever *skipped* in CI for want of a Postgres) was **stood up against a throwaway local Postgres 14 and reproduced green** — turning "the docs say 51 passed" into a watched pass. The review found the slice sound and the `0.6.1` security fixes correctly in place, and surfaced one money-path write gap plus two correctness/hygiene items, all fixed here. No new features, no schema change, no migration.

### Funding — closed an open write path to the public ledger

- **`source=stripe` funding is no longer creatable over the API.** `0.6.0` only gated *native* funding on the `internal` role, so any *authenticated* actor could `POST /projects/{id}/funding` with `source=stripe` and an arbitrary amount (up to `Numeric(12,2)` ≈ 10 billion) — born `pending`, attributed to them as a `fund` `Contribution`, and shown in the **publicly-readable** funding history (`GET /funding`), with **no real Stripe settlement behind it** until `0.7.0`. It was excluded from `funded` so it could not inflate a budget, but it was an open spam/clutter vector into a public read that nothing legitimate exercises (the frontend only ever submits `native`). `create_funding` now accepts only `source=native` and rejects anything else with `422` (`"Only native funding is available in this release; Stripe lands in 0.7.0"`). The `FundingSource.STRIPE` enum value, the `pending` status, and the budget-exclusion logic are all **kept** so `0.7.0` can light up real Checkout/webhooks without a schema change. (`app/services/funding.py`.)

### Correctness & hygiene

- **`DevActorProvider` no longer leaks a stale dev header in production.** The mount effect read `localStorage["opentheory.dev-actor-id"]` and pushed it as `X-Dev-Actor-Id` on every request **unconditionally** — so a browser that had previously run in dev mode would attach the header in a production build. It was *inert* (the backend ignores the header when `auth_dev_header_enabled=False`, and a verified bearer token always takes precedence), but identity providers should not cross the mode boundary. The effect now early-returns when `AUTH_DEV` (`NEXT_PUBLIC_AUTH_DEV`) is off — still marking `hydrated` so write-gating settles, but never reading localStorage or calling `setDevActorId`. (`src/providers/dev-actor-provider.tsx`.)
- **The budget's inferred accounting currency is now deterministic.** `project_budget` derives its `currency` from the last settled allocation it iterates; with no `ORDER BY` that was whatever order the rows came back in. The query now orders `created_at` ascending, so the inferred unit is deterministically the **most recent** settled allocation's currency (last-write-wins). Single-currency funding is unaffected; this only removes nondeterminism under the acknowledged-out-of-scope multi-currency case. (`app/services/funding.py`.)
- **Replaced the deprecated `HTTP_422_UNPROCESSABLE_ENTITY`** with `HTTP_422_UNPROCESSABLE_CONTENT` (Starlette renamed it; the old name emitted `DeprecationWarning`s in the test run) across the three services that raise it. No behavior change — same `422`. (`app/services/checkpoints.py`, `evidence.py`, `validations.py`.)

### Tests

- **Split `test_stripe_funding_is_pending_and_excluded_from_funded`** (which depended on the now-closed API path) into two, so closing the stripe path did **not** shrink coverage: `test_stripe_funding_via_api_is_rejected` (stripe create → `422`, nothing written) and `test_pending_allocation_excluded_from_funded`, which inserts a `pending` allocation **directly via the ORM** (legal — the append-only guard fires on update/delete, not insert) and asserts the budget excludes it from `funded`/`available` while `by_status` still tallies it and `by_source` stays settled-only. Net `+1` test (`51 → 52`). (`tests/test_funding.py`.)

### Considered and deliberately not done

- **A DB-level `CHECK` that a `Contribution` references exactly one of `checkpoint_id` / `funding_allocation_id`** was floated during review and **rejected on inspection**: the `0.3.x` create flows (thread / claim / evidence) record contributions with **both** FKs `NULL` (those creates are not checkpoint- or funding-events), so "exactly one" is the wrong invariant and "at most one" is marginal — and either would need a migration. Kept `0.6.2` migration-free. The xor between the two FKs remains a service-layer property, with append-only as the ORM-enforced backstop.
- **Carried forward unchanged from `0.6.1`'s "left as-is":** HS256 shared-secret JWT verification (`supabase_jwks_url` reserved for the asymmetric-key swap); the `internal` role granted only at JIT provisioning (add internal emails to the allowlist *before* first login); multi-currency budgets summing in one unit; public funding/budget reads exposing amounts + funder *display names* only (`ActorSummary` — no email), acceptable for the preview posture.

### Verification (independently reproduced, not cited)

- **Backend, against a throwaway local Postgres 14:** `uv run pytest` → **`52 passed`** with **no warnings** (the DB-backed `test_auth` / `test_funding` and the previously-skipped ledger suite all *executing*); `ruff check .` clean.
- **Migrations, against a scratch DB:** `0001 → 0005` applies; `alembic current` → `0005 (head)`; downgrade `0005→0004→0003` then re-upgrade round-trips; **`alembic check` → no drift** both before and after the round-trip; `actors.roles` and `funding_allocations.source` land exactly as the ORM declares them.
- **Safety:** confirmed the env-var override resolves Alembic to the local DB before running any DDL (the `.env` points `DATABASE_URL`/`MIGRATION_DATABASE_URL` at the live Supabase DB; exported env vars win over dotenv).
- **Frontend:** `npm run typecheck` and `npm run lint` pass.

### Still gating the production push (operational, not code)

- **`AUTH_DEV_HEADER_ENABLED=false` in production** — the single most important deploy invariant. If it is ever truthy in prod, the `X-Dev-Actor-Id` path reopens and any caller can act as any actor. (The setting defaults to `False`, so it is safe-by-default — never override it on Fly.)
- **Set `SUPABASE_JWT_SECRET` and `INTERNAL_ACTOR_EMAILS`** as Fly secrets (without the secret every token is `401`; without the allowlist no one is `internal`). Add internal emails **before** those users first sign in.
- **`alembic upgrade head` through `0005`** against prod (wired as Fly's `release_command`); Vercel `NEXT_PUBLIC_SUPABASE_URL` / `_ANON_KEY` set with `NEXT_PUBLIC_AUTH_DEV` unset.

---

## 0.6.1

Pre-production review hardening on the `0.6.0` auth + funding slice (mirrors how `0.4.5` hardened `0.4.0`). A full read-through of the `0.6.0` diff — the security- and money-critical backend scrutinized directly, the frontend covered by parallel reviewers, every verification claim re-run — found the design sound but surfaced two real security gaps and a high-blast-radius test-harness footgun, plus a few correctness/UX polishes. No new features, no schema change, no migration. Backend `ruff` clean and `5 passed, 46 skipped` (DB-backed tests safely skip); frontend `typecheck` / `lint` / `build` pass.

### Security

- **Closed an unauthenticated PII leak — `GET /actors`.** `0.6.0` made identity real (JIT provisioning stores the verified email in `actor_metadata` and the IdP subject in `external_id`), but the `0.3.x` actor-list endpoint stayed open and returns `ActorRead` — so an anonymous `GET /api/v1/actors` exposed **every user's email, IdP subject, and roles** (an email-harvesting vector). The leak was in pre-existing, untouched code that only became dangerous once the new feature changed the data it exposes. Gated the list behind `auth_dev_header_enabled` (→ `404` in production), exactly as `POST /actors` already was; the production frontend never calls it (the switcher is `AUTH_DEV`-only). The gate is in the handler, so the route still appears in the OpenAPI spec (the wiring test holds) — only its runtime behavior changes. (`app/api/routes/actors.py`.)
- **Fixed an open redirect (CWE-601) in `/auth/callback`.** The OAuth/magic-link handler redirected to `${origin}${next}` with `next` taken raw from the query string; because `next` need not start with `/`, `?next=.evil.com` → `https://<app>.evil.com` and `?next=@evil.com` → host `evil.com`, and the redirect fired even with no valid `code` — a phishing primitive on the trusted domain. Added `safeNext()`, which accepts only a single-leading-slash same-origin path (rejects `//…`, `/\…`, and non-slash values) and otherwise defaults to `/`. (`src/app/auth/callback/route.ts`.)

### Test-harness safety

- **A stray `DATABASE_URL` can no longer let the schema-reset fixture wipe production.** `conftest` resolved the test DB as `TEST_DATABASE_URL or DATABASE_URL`, and the fixtures run `DROP SCHEMA public CASCADE` per test — so because the live DB's env var is literally `DATABASE_URL`, a single `export DATABASE_URL=<prod>` before `pytest` would have destroyed it. The **implicit** `DATABASE_URL` fallback is now honored only for a local host (`localhost` / `127.0.0.1` / `::1`); an explicit `TEST_DATABASE_URL` is still trusted for any host (a deliberate opt-in). Verified both ways: a remote `…pooler.supabase.com` fallback is refused *before any connection*; a `localhost` fallback is accepted and connected. (`tests/conftest.py`.)

### Frontend correctness & polish

- **`canWrite` now requires a resolved backend actor.** It was `hasCredential` alone, so write controls enabled before — or despite a failed — `GET /me`. It is now `hasCredential && meQuery.isSuccess`, the same source of truth as `isInternal`, and the `hydrated` flag waits for `/me` to settle so the "sign in to contribute" hint never flashes for an already-credentialed user mid-fetch. (The backend was always the real enforcement point; this aligns the UI with it.) (`src/lib/use-identity.ts`.)
- **The callback surfaces exchange failures** instead of bouncing the user onto a page that thinks they're signed in: a failed `exchangeCodeForSession` redirects to `/?auth_error=…`. (`src/app/auth/callback/route.ts`.)
- **Minor:** the funding currency input is bounded (`maxLength={3}` + an `aria-label`); the `NEXT_PUBLIC_AUTH_DEV` note in `.env.example` now states it is inert without the backend's `AUTH_DEV_HEADER_ENABLED`, so the real gate is unambiguous. (`funding-panel.tsx`, `frontend/.env.example`.)

### Reviewed and deliberately left as-is

- **Native funding's `internal` role is granted only at JIT provisioning.** Adding an email to `INTERNAL_ACTOR_EMAILS` *after* a user's first login won't retroactively grant the role (re-evaluating on every login is a `0.7.0` decision). Operational note: add an internal email to the allowlist **before** that person first signs in.
- **HS256 shared-secret JWT verification** — Supabase is steering new projects toward asymmetric signing keys; the legacy shared secret still works and `supabase_jwks_url` is reserved for the swap. Forward-compat only.
- **Multi-currency budgets** sum in one inferred unit (acknowledged out of scope); public funding/budget reads expose amounts + funder display names (`ActorSummary` only — no email), acceptable for the current preview posture.

### Still gating the production push

- **The DB-backed suite (`test_auth` + `test_funding` + the rest) must be run green against a throwaway Postgres.** This pass re-ran lint, the non-DB suite, and the frontend build, but could not reproduce the `0.6.0` "`51 passed` against real Postgres" claim without a test database (the only configured DB is the live one). Run `TEST_DATABASE_URL=<throwaway> uv run pytest` before tagging.
- **Deploy config:** Fly secrets `SUPABASE_JWT_SECRET`, `INTERNAL_ACTOR_EMAILS`, `AUTH_DEV_HEADER_ENABLED=false`; Vercel `NEXT_PUBLIC_SUPABASE_URL` / `_ANON_KEY` with `NEXT_PUBLIC_AUTH_DEV` unset; `alembic upgrade head` through `0005` (wired as Fly's `release_command`).

---

## 0.6.0

Authentication and funding — real verified identity, then the funding write path, in that order. Replaces the unverified `X-Dev-Actor-Id` dev header with a Supabase-issued JWT mapped onto the existing `Actor` model, and activates `FundingAllocation` (the last core primitive with a model but no write path) as a money-stubbed, source-aware, contribution-only ledger write. Full details in `docs/completions/0.6.0-auth-and-funding.md`. Real Stripe settlement and compute *spend* remain deferred to `0.7.0`.

### Prerequisite — closed the `0.4.0` DB-test gate

- Through `0.4.7` the DB-backed suite had only ever *skipped*. Running it against a real Postgres for the first time exposed a latent **test-harness** bug: `Base.metadata.drop_all` cannot topologically sort the `branches`↔`checkpoints` foreign-key cycle (the dual-FK from `0.4.2`), so every teardown errored and leftover rows cascaded into failures. Fixed in `tests/conftest.py` by resetting the schema (`DROP SCHEMA public CASCADE; CREATE SCHEMA public`) in setup + teardown instead of dropping table-by-table. Test-infrastructure only — no app code. The DB-backed suite now executes green; auth/funding are built on a verified service layer.

### Verified identity (`0.6.1`)

- **`actors.roles`** (migration `0004_actor_roles`) — an `ARRAY(String)` queryable-authorization column (server default `'{}'`); an `internal` (Kamino) role gates native funding. A mutable identity attribute, **not** append-only guarded.
- **`app/core/auth.py`** — a swappable verification adapter: verifies a Supabase HS256 JWT (signature/audience/expiry) and returns `(subject, email, display_name)`. Swapping IdP changes only this file + config.
- **`app/api/deps.py`** — `get_acting_actor` now resolves a verified bearer token to one `Actor` by `external_id == sub`, **JIT-provisioning** on first login (idempotent on the unique `external_id`); falls back to the `X-Dev-Actor-Id` path only behind `auth_dev_header_enabled` (local/test). **The `ActingActor` contract and every service are unchanged.** Adds `require_internal`.
- `GET /me` (resolved actor + roles); `POST /actors` retired to `404` in production (kept behind the dev flag). New config: `supabase_jwt_secret`, `supabase_jwt_audience`, `auth_dev_header_enabled`, `internal_actor_emails`. Adds `pyjwt`.

### Frontend auth (`0.6.2`)

- Supabase Auth (`@supabase/ssr`): sign-in/out (OAuth + email magic link), a PKCE `/auth/callback` route, an `AuthProvider` that pushes the verified token into the api client. The acting credential moved module-side, so the `actorId` argument was dropped from every mutation; `request` attaches `Authorization: Bearer` (or `X-Dev-Actor-Id` in dev mode). A unified `useActingIdentity()` hook gates writes and exposes roles; the dev-actor switcher survives only behind `NEXT_PUBLIC_AUTH_DEV`.

### Funding write path (`0.6.3`)

- **`funding_allocations.source`** (migration `0005_funding_source`, new `funding_source` enum `native`/`stripe`). `app/services/funding.py` writes an allocation + a `fund` `Contribution` (`funding_allocation_id` set, `checkpoint_id` NULL) in one transaction — **no checkpoint minted** (Decision #3). Native funding requires the `internal` role (`403`) and is born `settled`; stripe is born `pending` and excluded from `funded`. Routes for create/list/detail/budget; project overview gains a `budget` block (`funded = Σ settled`, `spent = 0`, `available = funded`).

### Frontend funding (`0.6.4`)

- A project budget panel (Funded / Available / Spent-as-0) with a funding-history list and an internal-only native top-up form; copy makes the funder/contributor/validator separation legible.

### Verification

- Backend `51 passed` against a real Postgres (DB-backed tests executing, not skipping); `ruff` clean. Migrations `0004`/`0005` apply, round-trip, and pass `alembic check` (no drift). Frontend `typecheck`/`lint`/`build` pass. End-to-end HTTP smoke against the migrated schema confirmed: internal native funding → `settled` + attributed; non-internal → `403`; budget updates; **0 checkpoints minted** by funding; a real JWT JIT-provisions the actor at `GET /me`, a verified write → `201`, a malformed bearer → `401`.

---

## 0.4.8

First live deployment. Stands up the running product for the first time: the FastAPI backend on Fly.io and the Next.js frontend on Vercel, both pointed at the already-live Supabase database (`0.4.6`). Deployed as an **open preview** — there is no authentication yet (`X-Dev-Actor-Id` is not a credential), so the surface is intentionally world-readable/writable until `0.6.0`. No application code, schema, or migration change — this is deployment scaffolding plus the deploy itself.

### Summary

Through `0.4.7` the apps built clean but had never been deployed — there was zero deployment config in the repo. This phase adds the backend container + Fly configuration, documents the production connection shape, and takes the full stack live against the live DB (empty — no seed data; projects are created through the UI). The Vercel frontend is managed manually via the dashboard.

### Deployment Scaffolding (new)

- `backend/Dockerfile` — uv-based image (`ghcr.io/astral-sh/uv:python3.12-bookworm-slim`); dependencies install from the locked manifest in a cached layer (`uv sync --frozen --no-dev`); production entrypoint `fastapi run app/main.py` on `0.0.0.0:8000`.
- `backend/fly.toml` — app `opentheory-backend`, internal port 8000, `force_https`, a `/api/v1/health` HTTP check, scale-to-zero (`min_machines_running = 0`), and `release_command = "alembic upgrade head"` so migrations run in an ephemeral machine *before* traffic shifts (a bad migration aborts the deploy; the app never races to migrate on boot).
- `backend/.dockerignore` — keeps `.env`/secrets, the local venv, caches, and tests out of the build context/image.

### Configuration

- `backend/.env.example` now documents the production connection shapes: the app over the Supabase **transaction pooler** (`:6543`, `asyncpg`, `ssl=require`), Alembic over the **direct** connection (`:5432`) via `MIGRATION_DATABASE_URL`, and `BACKEND_CORS_ORIGINS` as the deployed frontend origin. Reuses the dual-connection design proven in `0.4.6`; no new settings.

### What Went Live

- **Backend** → Fly.io app `opentheory-backend`: <https://opentheory-backend.fly.dev/api/v1> (region `iad`, single scale-to-zero machine). Secrets (`DATABASE_URL`, `MIGRATION_DATABASE_URL`, `BACKEND_CORS_ORIGINS`) set via `fly secrets`, never committed.
- **Frontend** → Vercel: <https://opentheory.vercel.app> (root directory `frontend/`, `NEXT_PUBLIC_API_BASE_URL` → the Fly backend).
- **Database** → the existing live Supabase Postgres at migration `0003` (unchanged).

### Verification

- Remote Docker build succeeded; the `alembic upgrade head` release step completed against the live DB (a no-op at head — confirms the direct-connection migration path works from Fly).
- Public smoke test: `GET /api/v1/health` → `200 {"status":"ok"}`, `GET /api/v1/projects` → `200 []`.
- Simulated browser preflight from the Vercel origin returns `access-control-allow-origin: https://opentheory.vercel.app` — the CORS loop is closed. (End-to-end frontend page load left to a visual check.)

### Operational Notes / Gotchas

- Fly provisions an **HA pair** on first deploy even with `min_machines_running = 0` (that setting governs how many stay *running* when idle, not how many are *created*); the second machine stuck in `created` made `fly deploy` report a timeout though the service was healthy. Destroyed the extra — one machine is plenty for a scale-to-zero preview.
- `NEXT_PUBLIC_*` is baked at **build** time, so changing the backend URL requires a frontend *redeploy*, not just an env edit.
- `fly secrets import < .env` would clobber `APP_ENV=production` (from `fly.toml [env]`) with the local `.env` value — only the DB/CORS keys are imported.

### Documentation

- `docs/deploy.md` — full runbook (backend → frontend → CORS) with the production connection-string shapes and troubleshooting (IPv6 migration fallback, CORS, prepared-statement errors).
- `docs/design_blueprint.md` and `docs/executing/0.6.0-auth-and-funding.md` also landed in this window — a Kamino console design system, and the `0.6.0` auth + funding implementation plan. These are forward-looking planning/design references, **not** part of this deployment release.

### Still Gating A Production Push (unchanged)

- **The 31 DB-backed tests still have not run green against Postgres** — the standing `0.4.0` Definition-of-Done gate (needs a *separate* `TEST_DATABASE_URL`; the fixture `drop_all`s, so it must never point at the live DB).
- **No authentication/authorization** — `X-Dev-Actor-Id` lets any caller act as any actor; the open preview is world-writable. Deferred to `0.6.0`.

---

## 0.4.7

Developer convenience only — a root `Makefile` so the common workflows have short, memorable names. No application code, schema, or behavior change.

### Tooling

- Added a root `Makefile` wrapping the existing backend (`uv`) and frontend (`npm`) commands as targets: `make dev` (backend dev server), `make fe` (frontend dev server), `make migrate` / `make migration m="…"` / `make downgrade` (Alembic), `make test`, `make lint`, `make sync`, `make fe-install`. Bare `make` (default goal) prints a self-generated target list from each target's `##` comment.
- The targets only *wrap* the canonical commands (each is `cd backend && uv run …` or `cd frontend && npm …`), so every guarantee of `uv run` is preserved — correct `.venv`, locked deps — just behind a shorter name. Nothing previously documented changes.

---

## 0.4.6

First live database. Stands up the chosen managed Postgres (Supabase, per `docs/techstack.md`), applies the existing migrations to a real database for the first time, and hardens the connection configuration for a pooled cloud Postgres. Also fixes two latent configuration bugs that only surface once a populated `.env` exists. No new features, no schema change, no new migration — this closes the **infrastructure half** of the `0.4.0 — Validation And Branching` Definition-of-Done gate.

### Summary

Through `0.4.5` the backend had never connected to a real database: migrations were verified offline and the DB-backed tests skipped. This phase provisions the database, applies `0001 → 0003` against it, and proves both connection paths the app needs (pooled runtime + direct migrations). Bringing up a real `.env` for the first time also flushed out two dormant configuration bugs, both fixed.

### Database

- Applied migrations `0001_baseline → 0002_checkpoint_content → 0003_checkpoint_branch_id` to a live managed Postgres — the first time the schema has been created on a real database. `alembic current` reports `0003` at head and the expected public tables are present.

### Connection Configuration (dual path)

- **App runtime → transaction pooler.** The application engine connects through the connection pooler in transaction mode for connection scalability. asyncpg's prepared-statement cache is disabled (`connect_args={"statement_cache_size": 0}`) so it is safe behind a transaction-mode pooler (which reassigns server connections per transaction). At the platform's current query scale the lost statement caching is negligible, and parameter binding — i.e. injection safety — is unaffected. (`app/db/session.py`.)
- **Migrations → direct connection.** Added an optional `migration_database_url` setting (`MIGRATION_DATABASE_URL`); Alembic prefers it and falls back to `database_url`. DDL and schema introspection run over a stable, non-pooled session — the Prisma `url`/`directUrl` split. (`app/core/config.py`, `alembic/env.py`.)
- **TLS.** Connection URLs carry `?ssl=require`, which the SQLAlchemy asyncpg dialect maps to asyncpg's `ssl` argument (not the psycopg `sslmode`, which asyncpg does not understand). Connection secrets live only in the gitignored `.env`; `.env.example` documents the shape.

### Latent Config Bugs Fixed (surfaced by the first populated `.env`)

- **CORS origins parsing.** `backend_cors_origins` is a `list` field, and pydantic-settings JSON-decodes complex fields *before* validators run — so a plain `BACKEND_CORS_ORIGINS=http://localhost:3000` raised a JSON error at startup. Annotated the field with pydantic-settings' `NoDecode` so the existing comma-splitting validator receives the raw string. Dormant until now because the empty-default path skipped the decode. (`app/core/config.py`.)
- **CORS origin trailing-slash mismatch.** `str(AnyHttpUrl(...))` normalizes to `http://localhost:3000/`, but browsers send the `Origin` header without the trailing slash and Starlette matches origins exactly — so every preflight would have failed. Strip the trailing slash when building `allow_origins`. (`app/main.py`.)

### Tooling And Verification

- `uv run alembic upgrade head` applied all three migrations to the live database; `alembic current` → `0003` (head).
- Verified the app's transaction-pooler path connects and queries with no prepared-statement errors, and that the migrated schema is visible over it.
- In-process smoke test against the live database: `GET /api/v1/health` → `200`, `GET /api/v1/projects` → `200 []` (empty, pre-seed).
- `uv run ruff check .` clean; `uv run pytest` → `5 passed, 31 skipped` (DB-backed tests still skip — see below).

### Still gating a production push

- **The 31 DB-backed tests still need to be run green** against a *separate* test database. The test fixture creates and `drop_all`s the schema per test, so `TEST_DATABASE_URL` must never point at the live/seeded database. This is the remaining half of the `0.4.0` DoD gate; the infrastructure half (DB stood up, migrations applied, both connection modes proven) is now done.
- **No authentication/authorization** — `X-Dev-Actor-Id` lets any caller act as any actor. Deferred to `0.6.0`.

---

## 0.4.5

Review-driven correctness and polish on the completed `0.4.0 — Validation And Branching` slice. No new features, no schema change, no migration — a hardening pass from a full read-through of the `0.4.x` diff against the plan and completion docs.

### Summary

A review of the `0.4.x` implementation found the design sound but surfaced one real correctness bug (the claim signal ignored the *order* of validations), one latent test failure (a `0.3.4` assertion not updated when `0.4.4` widened the counts shape), and a few polish items. All are fixed; the suite, lint, and frontend build stay green.

### Correctness

- **Order-aware claim `signal`.** `compute_signal` now walks the validation history chronologically (oldest first) instead of treating it as an unordered set. Previously, a single `retract` *anywhere* in the history cleared every contradiction — so a `contradicts` recorded *after* a `retract` was wrongly shown as not-contested. Now the latest decisive event wins: `contradicts`/`failed` contests, a later `retract` clears it, a still-later `contradicts` re-contests. The derivation remains a pure display signal (plan Decision #5) — `Claim.status` is still never mutated. (`app/services/claims.py`.)

### Tests

- **Fixed a stale assertion** in `tests/test_read_models.py::test_project_overview_counts`: it asserted `counts == {threads, claims, evidence, checkpoints}`, but `0.4.4` added `validations` and `branches` to `ProjectCounts`. The DB-backed test is skipped offline (no database configured), so this went unnoticed — it would have failed on the first real-DB run. Now asserts the full six-key shape.
- **Added an order-aware signal case** to `test_claim_read_validation_history_and_signal`: `contradicts → retract → contradicts` ends `contested` (locks in the fix above).

### Polish

- **Sealed-branch recording UX.** The checkpoint timeline panel now takes a `lineSealed` flag (derived in `ProjectWorkspace` from the selected branch's status): on a closed/dead-end line it hides the "new checkpoint" affordance and explains that the line is preserved, not extended — instead of offering a form whose submit the backend rejects with `400`. (`project-workspace.tsx`, `checkpoint-timeline-panel.tsx`.)
- **Removed dead frontend exports:** the unused `getBranch` and `listClaimValidations` API-client functions and the `BranchDetail` type (claim validation history has been embedded in the claim read since `0.4.4`; the branch list drives the UI). The backend `GET /branches/{id}` detail endpoint stays — it's a legitimate, tested read for API consumers. (`lib/api.ts`, `types/research.ts`.)
- **Typed the checkpoint ref validator:** `_validate_refs(..., refs: list[CheckpointRefInput])` (was a bare `list` with a comment). (`app/services/checkpoints.py`.)

### Tooling And Verification

- `uv run ruff check .` (clean), `uv run pytest` (`5 passed, 31 skipped` — DB-backed tests still skip without a database), and `npm run typecheck` / `lint` / `build` (all pass).

### Still gating a production push (unchanged from `0.4.4`)

These are not regressions introduced here — they are the standing items before `0.4.0` is truly prod-ready, restated so they aren't lost:

- **The 31 DB-backed tests have never run against Postgres**, and no migration has been applied to a live database. This is the `0.4.0` Definition-of-Done gate: stand up Postgres, `uv run alembic upgrade head`, and get the DB-backed suite green.
- **No authentication/authorization** — `X-Dev-Actor-Id` lets any caller act as any actor. Acceptable for an internal/demo deploy; a blocker for a public one. Deferred to `0.6.0`.

---

## 0.4.4

Read-model enrichment and polish — makes research integrity legible at a glance. Fourth and final phase of `0.4.0 — Validation And Branching`. Backend read models + frontend rendering; no new write paths and no migration. See `docs/completions/0.4.4-read-model-and-polish.md`.

### Summary

Enriches the read side so the workspace shows what's been assessed, what's contested, and which lines are alive vs. abandoned. The claim read now embeds its validation history and a server-derived `signal` (`contested` / `validated` / `none`) computed from that history — without mutating the stored `Claim.status` (plan Decision #5). The project overview gains a validation count, branch-status counts, and a contradictions summary. The branch list carries per-branch checkpoint counts.

### Backend Read Models

- `ClaimRead` now includes `validations` (history, oldest first) and `signal`; the claims service constructs reads explicitly (never via `from_attributes` on the ORM, which would lazy-load the relationship) and batches validation lookups (no N+1, reusing the validations service).
- `GET /projects/{id}/overview` adds `counts.validations`, `counts.branches`, `branch_counts` (open / dead-end / closed), and `contradictions` (contested claims).
- Branch list (`GET /projects/{id}/branches`) returns `BranchSummary` with a per-branch `checkpoint_count` (single grouped outer-join query).
- Shared `compute_signal` lives in the claims service and is reused by the overview's contradictions detection. No schema/migration change.

### Frontend Rendering

- Claim cards render validation history (outcome badges + notes + actor) and a `contested` / `validated` chip from the server `signal`; the claim read's embedded data replaces the separate per-claim validations fetch.
- Workspace header shows six aggregate counts (adds Validations, Branches) and an ember "contested claims" strip listing the contradictions.
- The branch bar shows per-branch checkpoint counts and, for the selected line, its fork point and count.

### Tooling And Verification

- Extended `tests/test_read_models.py` (DB-backed: claim history + signal incl. retract-clears-contradiction, overview branch/validation counts + contradictions, branch `checkpoint_count`).
- Verified with `uv run ruff check .` (clean), `uv run pytest` (`5 passed, 31 skipped`), and `npm run typecheck` / `lint` / `build` (all pass).

### End-To-End Manual Verification Path (the `0.4.0` slice)

Once a database is configured (`DATABASE_URL` set, `uv run alembic upgrade head` applied), the full `0.4.0` flow is reproducible from the UI alone, on top of the `0.3.0` slice:

1. Open a project that already has a thread, a claim, and at least one checkpoint (the `0.3.0` flow), with a dev actor selected (top-right switcher).
2. On a claim, click **Validate**, choose `contradicts`, and submit. The claim shows a **contested** chip and an outcome badge; the header **Validations** count and the **contested claims** strip update; a `validate` checkpoint appears in the timeline.
3. Record another validation on the same claim with `retract` — the **contested** chip clears (history is preserved, oldest first).
4. In the branch bar, **Fork** a branch from a checkpoint (name + reason). It is auto-selected; the **Branches** count and the branch's checkpoint count update.
5. With the branch selected, record a checkpoint — it lands on the branch line (the main-line timeline is unchanged when you switch back to **Main line**).
6. **Close branch** as a dead-end with a reason. The branch chip is struck through and marked `dead end`; `branch_counts.dead_end` increments; the closing reason is preserved (recorded, not deleted).
7. Confirm append-only/provenance: `PUT`/`DELETE` on validations and checkpoints are absent; an ORM update/delete of a `Validation` raises `AppendOnlyError`; recording a checkpoint on the closed branch returns `400`.

This exercises every `0.4.0` primitive end-to-end: validation (recorded through a checkpoint, attributed) and branching (fork → branch checkpoint → close as dead-end), with the contradiction and dead-end states surfaced.

---

## 0.4.3

Frontend validation and branch surfaces. Third phase of `0.4.0 — Validation And Branching`. Frontend only. See `docs/completions/0.4.3-frontend-validation-and-branches.md`.

### Summary

Surfaces the `0.4.1`/`0.4.2` write paths in the research workspace: record validations on claims and checkpoints, fork/close branches, scope the checkpoint timeline to a branch line, and flag contested claims. Built on the existing TanStack Query reads/mutations + query-key invalidation; no new client-state library.

### Product Surface

- Shared validation controls: an outcome→icon/colour vocabulary, an `OutcomeBadge`, and a reusable `RecordValidationForm` used on both claims (with inline history) and checkpoints (record-only — no per-checkpoint history endpoint).
- A branch bar above the panels: a **Main line** chip plus a chip per branch (dead-ends struck through), a **Fork** form anchored on a chosen checkpoint, and a **Close branch** form (dead-end / closed, required reason). Selecting a branch scopes the checkpoint timeline and new-checkpoint `branch_id` to that line; the claims panel stays thread-scoped (branches scope the ledger line, not the claim set, in this model).
- A client-side contradiction indicator on claims (superseded by the server `signal` in `0.4.4`).

### Frontend Structure

- Added `src/components/workspace/validation-controls.tsx` and `branch-bar.tsx`; extended the claim and checkpoint panels and the project workspace; extended `lib/api.ts`, `types/research.ts`, and the query keys with validations and branches.

### Tooling And Verification

- Verified with `npm run typecheck`, `lint`, and `build` (all pass). Live click-through deferred until a database is configured, consistent with the backend phases.

---

## 0.4.2

Branch write path. Second phase of `0.4.0 — Validation And Branching`. Backend + one migration. See `docs/completions/0.4.2-branch-write-path.md`.

### Summary

Activates the `Branch` primitive: fork a parallel line from a checkpoint, record checkpoints on it, and close it as a dead-end/superseded — all recorded through the single checkpoint chokepoint. Merge is deferred (plan Decision #3); `BranchStatus.MERGED` stays reserved.

### Schema

- Added `checkpoints.branch_id` (nullable, FK → `branches.id` `ON DELETE SET NULL`, indexed). `NULL` = the project main line (plan Decision #2); existing checkpoints become main-line. Migration `0003_checkpoint_branch_id` (`down_revision = 0002_checkpoint_content`).
- This is the second FK between `checkpoints` and `branches`, so all relationships spanning the two tables now pin `foreign_keys` explicitly.

### API

- `POST /api/v1/projects/{id}/branches` (fork from a checkpoint), `GET /api/v1/projects/{id}/branches`, `GET /api/v1/branches/{branch_id}` (detail incl. its checkpoints), `POST /api/v1/branches/{branch_id}/close` (outcome `dead_end`/`closed` + reason).
- `CheckpointCreate` accepts an optional `branch_id`; the chokepoint validates it is an in-project, **open** branch before stamping it.

### Service Layer

- Added `app/services/branches.py` (`create_branch`, `close_branch`, `list_branches`, `get_branch`), composing with the checkpoint chokepoint; `create_branch`/`close_branch` actions added to the contributions module. The fork's first checkpoint is recorded on the branch (parented on the fork point); the close checkpoint is main-line and references the branch (atomicity over stamping — see the completion doc).

### Tooling And Verification

- Added `tests/test_branches.py` (DB-backed). Verified with `uv run ruff check .` (clean), `uv run pytest` (DB-backed tests skip until a database is configured), `configure_mappers()` (dual-FK relationships), and offline Alembic checks (`0003` loads as head, renders the expected DDL).

---

## 0.4.1

Validation write path. First phase of `0.4.0 — Validation And Branching`. Backend only; no migration. See `docs/completions/0.4.1-validation-write-path.md`.

### Summary

Activates the `Validation` primitive as a first-class, immutable assessment recorded **through** the checkpoint chokepoint (plan Decision #1): recording a validation writes the `Validation` row and, in the same transaction, mints a checkpoint referencing the validated target (`role=validated`) and the validation (`role=recorded`), attributed by a `validate` contribution.

### API

- `POST /api/v1/projects/{id}/validations` (requires `X-Dev-Actor-Id`), `GET /api/v1/projects/{id}/validations`, `GET /api/v1/claims/{claim_id}/validations`, `GET /api/v1/validations/{validation_id}`. GET/POST only — no mutation methods.
- Targets follow the model: `claim` / `checkpoint` / `branch` / `artifact` (plan Decision #4; `artifact` wired but untested until artifact writes land). No `evidence` target.

### Service Layer

- Added `app/services/validations.py`; extended `CheckpointService.create_checkpoint` minimally (service-supplied `extra_refs` + an optional `contribution_action`) so the validation flow goes through the one chokepoint. Added `validation`/`branch` to the checkpoint-ref vocabulary.

### Append-Only Enforcement

- Added `Validation` to the ORM append-only guard set (`Checkpoint`, `CheckpointRef`, `FundingAllocation`, `Validation`): a re-assessment is a new row, never an edit.

### Tooling And Verification

- Added `tests/test_validations.py` (DB-backed) and extended `tests/test_wiring.py`. Verified with `uv run ruff check .` (clean) and `uv run pytest` (`5 passed`, DB-backed tests skip until a database is configured). No migration (the `validations` table is in the `0001` baseline).

---

## 0.3.4

Makes the checkpoint timeline read like a real research record and surfaces the state of the ledger at a glance. Fourth and final phase of `0.3.0 — Human-Operable Research Ledger`. Backend read models + frontend rendering; no new write paths and no migration (read-model only). See `docs/completions/0.3.4-ledger-read-model.md`.

### Summary

Enriches the read side: a project overview with aggregate counts, per-thread claim counts on the thread list, and a checkpoint read model carrying the creating actor, the contribution kind, and human labels for referenced claims/evidence. The workspace renders all of it — header counts, thread claim-count badges, and a timeline that shows who recorded each checkpoint, what action it was, and which primitives it touched.

### Backend Read Models

- `GET /api/v1/projects/{project_id}/overview` → project detail plus aggregate `counts` (threads, claims, evidence, checkpoints).
- Thread list (`GET /api/v1/projects/{project_id}/threads`) now returns `ThreadSummary` with a per-thread `claim_count` (single grouped outer-join query).
- Checkpoint reads (`list`/`detail`) are enriched with `author` (id, display name, type), `contribution_kind`, and a resolved `label` on each ref (claim statement / evidence/thread title / artifact name), all batched without N+1.
- Added `app/services/projects.py`; extended the thread and checkpoint services and the project/thread route response models. No schema/migration change.

### Frontend Rendering

- Workspace header shows the four aggregate counts (pulsing skeleton while loading); thread list shows a claim-count badge per thread.
- Checkpoint timeline shows the humanized action, the author, and the referenced claims/evidence as `role → label` rows, alongside stage, scope, and parent count; empty-state copy now explains when to record a checkpoint.
- Writes invalidate the overview (and the thread list on claim create) so counts stay live; added the `getProjectOverview` client call and the matching types.

### Tooling And Verification

- Added `tests/test_read_models.py` (DB-backed: overview counts + 404, thread `claim_count` incl. a zero-claim thread, enriched checkpoint author/contribution-kind/ref-labels on detail and list) and extended `tests/test_wiring.py` for the overview path.
- Ran an adversarial multi-agent review of the diff (10 findings → 3 actionable, fixed: render the checkpoint action, counts loading skeleton, richer empty-state copy; the rest were positive confirmations or correctly rejected).
- Verified with `uv run ruff check .` (clean), `uv run pytest` (`5 passed, 18 skipped`), and `npm run typecheck` / `lint` / `build` (all pass).

### End-To-End Manual Verification Path

Once a database is configured (`DATABASE_URL` set, `uv run alembic upgrade head` applied), the full `0.3.0` flow is reproducible from the UI alone:

1. Start the backend (`uv run fastapi dev app/main.py`) and frontend (`npm run dev`); open `http://localhost:3000`.
2. Create a project (via `POST /api/v1/projects` or seed) and open it.
3. In the header dev-actor switcher (top right), create an actor — it is auto-selected and attached as `X-Dev-Actor-Id` on writes.
4. Left panel: create a thread (title + sub-question). It is auto-selected; the header **Threads** count and the thread's claim-count badge update.
5. Center panel: record a claim on the thread (kind + statement). The **Claims** count and the thread badge increment.
6. On that claim, attach evidence (title + source + relation kind: support/weaken/context). It appears under the claim color-coded by relation; the **Evidence** count increments.
7. Right panel: record a checkpoint (summary + optional notes) — scoped to the selected thread. The **Checkpoints** count increments and the timeline shows it newest-first with the action ("create checkpoint"), the author, and the timestamp.
8. Confirm append-only: `PUT`/`DELETE` on `/api/v1/checkpoints/{id}` returns `405`; ORM update/delete raises `AppendOnlyError` (covered by `tests/test_checkpoints.py`).
9. Confirm provenance: each of the four creates recorded a `Contribution` attributing the acting actor (covered by `test_contribution_recorded_for_all_create_flows`).

This exercises every primitive in the human-operable ledger end-to-end: thread → claim → evidence → checkpoint, with attribution and append-only enforcement.

---

## 0.3.3

Surfaces the `0.3.1`/`0.3.2` write paths in the product. Third phase of `0.3.0 — Human-Operable Research Ledger`. Frontend only. See `docs/completions/0.3.3-frontend-research-workspace.md`.

### Summary

Expands `/projects/[projectId]` from a read-only detail page into a three-panel research workspace where a user completes the full research move — thread → claim → evidence → checkpoint — through the UI, with a dev-actor identity attached to every write. Built on TanStack Query for both reads and write mutations with query-key invalidation; no other client-state library.

### Product Surface

- Three-panel workspace: left thread list + create-thread; center claims for the selected thread with per-claim evidence and inline create-claim / attach-evidence; right project checkpoint timeline (newest first) with create-checkpoint scoped to the selected thread.
- Dev-actor switcher in the header: lists actors from `GET /api/v1/actors`, lets the user pick or create one (bootstrap path, no header), persists the selection in `localStorage`, and attaches it as `X-Dev-Actor-Id` on all writes. Replaced by real auth in `0.6.0`.
- Loading, empty, and error states for every panel via a shared `panel-state` helper.
- Minimal create UIs (single-line fields + an optional notes textarea on checkpoints); no rich editors.

### Frontend Structure

- Added `src/types/research.ts` (domain types mirroring the backend read schemas), `src/lib/query-keys.ts` (centralized query keys), `src/providers/dev-actor-provider.tsx`, `src/components/shell/dev-actor-switcher.tsx`, and the `src/components/workspace/` panel set (`panel-state`, `thread-list-panel`, `claim-list-panel`, `checkpoint-timeline-panel`, `project-workspace`).
- Extended `src/lib/api.ts` with all reads, the four create flows, and actor create/list; writes attach `X-Dev-Actor-Id`, and the request helper surfaces the backend `detail` on errors.
- Wrapped the app in `DevActorProvider`; the project route now renders `ProjectWorkspace`; the header hosts the switcher. Removed the superseded `project-detail.tsx`.

### Tooling And Verification

- Ran an adversarial multi-agent review of the diff (8 findings → 3 confirmed, 5 rejected); fixed the confirmed actor/mutation-lifecycle items (capture the acting actor by value at submit, gate the no-actor hint on hydration, guard against double-submit).
- Verified with `npm run typecheck` (clean), `npm run lint` (clean), and `npm run build` (succeeds; `/` static, `/projects/[projectId]` dynamic). A live end-to-end click-through is deferred until a database is configured, consistent with `0.3.1`/`0.3.2`.

---

## 0.3.2

Makes the research ledger real: the checkpoint becomes the only sanctioned way to record a meaningful state change, append-only is enforced at the ORM layer, and every create flow is attributed. Second phase of `0.3.0 — Human-Operable Research Ledger`. Backend only; no frontend changes yet (deferred to `0.3.3`). See `docs/completions/0.3.2-checkpoint-service.md`.

### Summary

Adds `CheckpointService.create_checkpoint` as the single chokepoint for ledger writes, enforces the append-only invariant on `Checkpoint`/`CheckpointRef`/`FundingAllocation` at the ORM layer, and back-fills automatic `Contribution` recording onto the `0.3.1` thread/claim/evidence creates so all four create flows are attributed. Checkpoints are created only by explicit user action — thread/claim/evidence creates do not auto-promote (plan Resolved Decision #3).

### Schema

- Added `checkpoints.content` (`JSON`, NOT NULL) — the free-form JSON payload a user authors on a checkpoint; no structured schema is enforced beyond "valid JSON object".
- Made `checkpoints.stage` nullable — a research-flow `ThreadStage` is optional metadata, not platform law, so a human may record a checkpoint without one.
- Added the second Alembic migration `0002_checkpoint_content` (`down_revision = 0001_baseline`): `ADD COLUMN content`, `ALTER COLUMN stage DROP NOT NULL`. Safe on the empty baseline table; references the existing `thread_stage` enum with `create_type=False`.

### API

- `POST /api/v1/projects/{project_id}/checkpoints` (requires `X-Dev-Actor-Id`) — validates project/thread/parents/refs, writes one `checkpoint_refs` row per ref with a `role`, links parents via `checkpoint_parents`, and auto-records a `create_checkpoint` contribution, all in one transaction.
- `GET /api/v1/projects/{project_id}/checkpoints` (newest first), `GET /api/v1/checkpoints/{checkpoint_id}`.
- No update/delete endpoints exist; the checkpoint paths are GET/POST only.

### Service Layer

- Added `app/services/checkpoints.py` (the sole producer of checkpoints) and `app/services/contributions.py` (`record_contribution` adds to the caller's session without committing, so contributions share the create's transaction).
- Back-filled `threads`/`claims`/`evidence` create services to record a contribution in the same transaction; route handlers now pass the acting actor through.

### Append-Only Enforcement

- Added `app/models/append_only.py`: `AppendOnlyError` plus `before_update`/`before_delete` ORM guards on `Checkpoint`, `CheckpointRef`, and `FundingAllocation`. Registration is idempotent and called explicitly in `create_app()` so the invariant never depends on import order. Enforced even if the route layer is bypassed.

### Tooling And Verification

- Refactored `tests/conftest.py` into shared `db_engine` + `session_factory` + `client` fixtures (one engine, so HTTP writes and direct DB assertions agree).
- Added `tests/test_checkpoints.py` (DB-backed: parents/refs, optional stage, full validation matrix, duplicate-parent dedup, append-only ORM enforcement with a selective negative test, contribution presence for all four flows) and extended `tests/test_wiring.py` (checkpoint paths exist, POST requires the dev-actor header, no mutation methods exposed).
- Ran an adversarial multi-agent review of the diff (19 findings → 6 confirmed, 13 rejected); confirmed items fixed (notably the `FundingAllocation` append-only gap and explicit guard registration).
- Verified with `uv run ruff check .` (clean), `uv run pytest` (`5 passed, 14 skipped`; DB-backed tests skip until a database is configured), and offline Alembic checks (`0002` loads as head, renders valid Postgres DDL, matches `metadata.create_all`).

> Note: a live database has not yet been chosen (Supabase vs. self-hosted). Applying `alembic upgrade head` and running the DB-backed tests are deferred to that step, consistent with `0.3.1`.

---

## 0.3.1

Backend write path for the three primitives that compose a research move. First phase of `0.3.0 — Human-Operable Research Ledger`. Backend + DB only; no checkpoint behavior and no frontend changes yet.

### Summary

Stands up the create/read API surface for threads, claims, and evidence under a project, plus manual dev-actor management and the two relational tables that make the new relations queryable. Establishes the service layer as the home for create logic and the first real Alembic migration. No checkpoint, contribution, or append-only behavior yet (deferred to `0.3.2`).

### Schema

- Added `claim_evidence_links` join table (`app/models/links.py`) — a true many-to-many between claims and evidence with a `relation_kind` `VARCHAR(20)` column (`support` / `weaken` / `context`, validated in the service layer) and a uniqueness guard on `(claim_id, evidence_id, relation_kind)`.
- Added `checkpoint_refs` join table (`app/models/links.py`) — polymorphic `target_type` (`VARCHAR(20)`), `target_id` (UUID, no FK), and `role` (`VARCHAR(40)`). Introduced now though it is consumed in `0.3.2`, to avoid a follow-up migration.
- Added reverse relationships on `Claim`, `Evidence`, and `Checkpoint`; exported both new models from `app/models/__init__.py` for Alembic discovery.
- Added the first real Alembic migration `0001_baseline` covering all `0.1.0` models plus the two join tables. Enum labels are the SQLAlchemy default (the `StrEnum` member names) to match the existing models; no data seeding.

### API

- `POST /api/v1/actors`, `GET /api/v1/actors` — manual dev-actor management (no auto-seeding).
- `POST /api/v1/projects/{project_id}/threads`, `GET /api/v1/projects/{project_id}/threads`, `GET /api/v1/threads/{thread_id}`.
- `POST /api/v1/threads/{thread_id}/claims`, `GET /api/v1/threads/{thread_id}/claims`, `GET /api/v1/claims/{claim_id}` — claims inherit the thread's project; `project_id` is never client-supplied.
- `POST /api/v1/claims/{claim_id}/evidence` (creates the `Evidence` row and its `claim_evidence_links` row in one transaction), `GET /api/v1/claims/{claim_id}/evidence` (joined through the link table, returns `relation_kind`).
- All write endpoints require the acting actor via the `X-Dev-Actor-Id` header, resolved to an existing `Actor`; missing, malformed, or unknown ids are rejected.

### Service Layer

- Added thin create/read services in `app/services/` for actors, threads, claims, and evidence. No checkpoint interaction yet.
- Added `app/api/deps.py` with the shared `DbSession` alias and the `get_acting_actor` dev-identity dependency.

### Tooling And Verification

- Added `tests/conftest.py` with a DB-backed `client` fixture that creates/drops tables per test and skips cleanly when no `TEST_DATABASE_URL`/`DATABASE_URL` is configured.
- Added `tests/test_wiring.py` (DB-free OpenAPI checks) and `tests/test_research_flow.py` (full flow, every relation kind, header enforcement, 404s).
- Verified with `uv run ruff check .` (clean) and `uv run pytest` (green; DB-backed tests skip until a database is configured).
- Verified the migration offline: it loads as the Alembic head, renders valid Postgres DDL via `alembic upgrade head --sql`, and its DDL matches `metadata.create_all` exactly (no spurious constraints/indexes).

> Note: a live database has not yet been chosen (Supabase vs. self-hosted). Applying the migration (`alembic upgrade head`) and running the DB-backed tests are deferred to that step. See `docs/completions/0.3.1-backend-write-path.md`.

---

## 0.2.0

Initial frontend scaffold for OpenTheory.

### Summary

This release establishes the frontend root at `frontend/` as a Next.js application aligned with `docs/techstack.md`. It is intentionally minimal but product-shaped: the first screen is a research project surface that connects to the FastAPI project endpoints instead of a generic starter page.

### Frontend Structure

- Added `frontend/package.json` and `frontend/package-lock.json` configured for Next.js, React, TypeScript, Tailwind CSS, TanStack Query, lucide icons, ESLint, and local scripts.
- Added `frontend/README.md` with local setup and verification commands.
- Added `frontend/.env.example` with `NEXT_PUBLIC_API_BASE_URL` for the FastAPI API prefix.
- Added `frontend/.gitignore` for Next.js build output, dependencies, local env files, and TypeScript build cache files.
- Added Next.js, TypeScript, PostCSS, Tailwind, and ESLint configuration files.
- Added the application source under `frontend/src/` with:
  - `app/` for App Router pages and global styling
  - `components/` for shell and project UI
  - `lib/` for backend API access
  - `providers/` for TanStack Query setup
  - `types/` for shared frontend domain types

### Product Surface

- Added the root project index page.
- Added a project detail route at `/projects/[projectId]`.
- Added typed reads for:
  - `GET /api/v1/projects`
  - `GET /api/v1/projects/{project_id}`
- Added loading, empty, and backend-error states for project reads.

### Tooling And Verification

- Installed frontend dependencies with npm.
- Verified the scaffold with:
  - `npm run typecheck`
  - `npm run lint`
  - `npm run build`

---

## 0.1.0

Initial backend scaffold for OpenTheory.

### Summary

This release establishes the backend root at `backend/` as a FastAPI modular monolith aligned with `docs/techstack.md`, `docs/primitives.md`, and the research-ledger model described in the vision docs. It is intentionally minimal but domain-shaped: the scaffold starts with real OpenTheory primitives instead of generic placeholder resources.

### Backend Structure

- Added `backend/pyproject.toml` configured for Python, FastAPI, Pydantic settings, SQLAlchemy 2.0 async support, Alembic, asyncpg, uv, pytest, and ruff.
- Added `backend/README.md` with local setup, test, lint, and migration commands.
- Added `backend/.env.example` with app, API prefix, database URL, and CORS configuration.
- Added the application package under `backend/app/` with:
  - `api/` for route registration and API modules
  - `core/` for settings/configuration
  - `db/` for SQLAlchemy base classes and async session handling
  - `models/` for database models
  - `schemas/` for Pydantic request/response schemas
  - `services/` as the reserved home for domain service logic

### API Foundation

- Added FastAPI app creation in `backend/app/main.py`.
- Added API router mounting under `/api/v1`.
- Added `GET /api/v1/health` as a smoke-test endpoint.
- Added initial project endpoints:
  - `POST /api/v1/projects`
  - `GET /api/v1/projects`
  - `GET /api/v1/projects/{project_id}`

### Domain Model Foundation

Added SQLAlchemy models for the first-pass OpenTheory primitives:

- `Actor`
- `Project`
- `Thread`
- `Claim`
- `Artifact`
- `Evidence`
- `Checkpoint`
- `Branch`
- `Validation`
- `Contribution`
- `FundingAllocation`

The model layer includes UUID primary keys, timestamp mixins, relationship wiring, and enum-backed states for actors, projects, research stages, threads, claims, funding events, branches, and validations.

### Research Ledger Groundwork

- Added `Checkpoint` as the core immutable research state-change primitive.
- Added `checkpoint_parents` join table to support parent checkpoint DAG relationships.
- Added explicit branch support for parallel research paths, dead ends, and later merge flows.
- Added append-only-friendly primitives for checkpoints and funding allocations.
- Added contribution records as the attribution/provenance substrate for humans, agents, and system actors.

### Database And Migrations

- Added Alembic configuration under `backend/alembic.ini`.
- Added async Alembic environment in `backend/alembic/env.py`.
- Wired Alembic metadata to the SQLAlchemy model registry.
- Added `backend/alembic/versions/.gitkeep` so the migration directory is retained before the first generated revision.

### Tooling And Verification

- Added pytest configuration and a health endpoint smoke test.
- Added ruff lint configuration.
- Verified the scaffold with:
  - `uv run ruff check .`
  - `uv run pytest`
- Confirmed SQLAlchemy metadata loads and registers 12 tables:
  - `actors`
  - `artifacts`
  - `branches`
  - `checkpoint_parents`
  - `checkpoints`
  - `claims`
  - `contributions`
  - `evidence`
  - `funding_allocations`
  - `projects`
  - `threads`
  - `validations`
