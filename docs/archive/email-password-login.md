# Auth — Email + Password Sign-In — Completion

> Implements `docs/executing/email-password-login.md`: **email + password** becomes the
> primary sign-in method (authenticating directly against existing `auth.users` rows via
> Supabase GoTrue), with magic-link and Google **retained** as secondary options. A correct
> credential signs the user in **in-band** — no email round-trip, no redirect. This is a
> **frontend-only** change: the backend verifies a Supabase session JWT and is blind to *how*
> the session was obtained, so there is **no** backend, schema, API, or migration change.

**Status:** complete. Frontend `typecheck` / `lint` / `build` all green; all 6 routes still
generate. Backend untouched (not re-run — no backend file changed). The one remaining step is
the live manual pass (real Supabase + an admin-provisioned password user), which needs a
browser and is noted under *Verification*.

**Version:** ships as **`0.6.9`** — a small, additive, frontend-only feature in the `0.6.x`
line. The release entry is in `docs/changelog.md`; this doc is the implementation-scoped detail.

**Scope of change (git diff --stat):**
- `frontend/src/providers/auth-provider.tsx` — +11 lines (expose `signInWithPassword`).
- `frontend/src/components/shell/auth-menu.tsx` — restructured signed-out dropdown.
- Nothing else. No backend, no test, no schema, no migration.

---

## Why this is frontend-only (the load-bearing fact)

`backend/app/core/auth.py::verify_bearer_token` verifies only a bearer JWT's **signature,
audience (`aud="authenticated"`), and expiry**, then reads `sub`/`email`/`user_metadata`.
Supabase issues the **same** HS256-signed session token for *every* sign-in method —
`signInWithOtp` (magic-link), `signInWithOAuth` (Google), and `signInWithPassword` are
indistinguishable once a session exists. Adding an authentication *method* on the IdP side is
therefore invisible to the verifier, and the entire `ActingActor` contract, JIT-provisioning,
and `internal`-role logic apply verbatim. (This is the seam the `core/auth.py` docstring
advertises — "swapping IdP changes only this file + config" — working in our favour.)

`Actor` (`public.actors`) is **not** `auth.users`: the Supabase row holds the
`encrypted_password` and does the password check; the `Actor` row never sees a password and
exists for provenance/attribution, linked 1:1 by `Actor.external_id = auth.users.id` (the JWT
`sub`). This change only adds a login method for the *human* subset; the agent/system actor
path (`external_id = NULL`, no auth record) is untouched.

---

## What landed, where, and why

### 1. `providers/auth-provider.tsx` — expose `signInWithPassword`

- Added `signInWithPassword: (email, password) => Promise<SignInResult>` to the
  `AuthContextValue` type, and implemented it in the `useMemo` context value alongside
  `signInWithEmail` / `signInWithGoogle`:

  ```ts
  signInWithPassword: async (email, password) => {
    if (!supabase) return { error: "Authentication is not configured" };
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    return { error: error?.message ?? null };
  },
  ```

- **Return shape** is the existing `SignInResult` (`{ error: string | null }`), so the menu
  treats all three methods uniformly.
- **`useMemo` dep array unchanged** (`[supabase, session, loading]`): the new method closes
  over only `supabase`, which is already a dependency. (Adding a method that captured a
  fresher value without listing it would create a stale-closure bug — confirmed not the case
  here.)
- **In-band session resolution:** unlike magic-link, this resolves a session synchronously on
  success. The provider's existing `onAuthStateChange` subscription then fires, calls
  `setAccessToken(...)` (pushing the bearer token into `lib/api.ts`) and `setSession(...)`,
  so the caller only needs to close the menu — no new wiring.

### 2. `components/shell/auth-menu.tsx` — password form as the primary path

- **New state:** `const [password, setPassword] = useState("")`; pulled `signInWithPassword`
  out of `useAuth()` alongside the existing methods.
- **New handler** `handlePasswordSignIn` mirrors `handleEmailSignIn`'s error handling, but on
  success closes the menu (`setOpen(false)`) instead of setting `sent` — the session arrives
  via `onAuthStateChange` and TanStack Query refetches under the new credential:

  ```ts
  async function handlePasswordSignIn() {
    setError(null);
    const { error: signInError } = await signInWithPassword(email.trim(), password);
    if (signInError) { setError(signInError); return; } // "Invalid login credentials" / "Email not confirmed"
    setOpen(false);
  }
  ```

- **Restructured signed-out dropdown** (top → bottom), inside the existing `!sent` branch:
  1. **Primary `<form>`** → `handlePasswordSignIn`: an **email** `Input`
     (`type="email"`, `autoComplete="username"`, `aria-label="Email"`) over a **password**
     `Input` (`type="password"`, `autoComplete="current-password"`, `aria-label="Password"`),
     then a full-width **`Action` "Sign in"** submit, disabled unless `email.trim() && password`.
     Enter-to-submit works (the form's `onSubmit` guards the same condition).
  2. **Divider** — a centered `"or"`.
  3. **"Email me a magic link"** button → `handleEmailSignIn` (the existing magic-link flow;
     keeps the `sent` state and its "Check your email for a sign-in link." confirmation). It is
     disabled until an email is present, since the email field is now shared with the password
     form.
  4. **"Continue with Google"** button → `signInWithGoogle()` (unchanged).
  5. **Error line** — the existing `{error ? … : null}` `text-state-fail` row, reused for all
     methods.
- **Unchanged:** the click-outside `useEffect` + `containerRef`, the `loading`/`!isConfigured`
  early returns, and the entire **signed-in** branch (name + roles + sign-out). The `sent`
  confirmation flow stays scoped to the magic-link button — a password attempt never sets `sent`.

#### Design-language notes (Kamino Console)

- The **"Sign in"** submit uses the `Action` primitive (primary variant) with
  `className="w-full"`. This is safe under the codebase's plain-`clsx` `cn` (no
  `tailwind-merge`) because `Action`'s `BASE`/`SHAPE` never set `width`, so `w-full` cannot
  conflict / double-emit. I deliberately did **not** override padding or text size via
  `className` (that is exactly the `cn`-no-`tailwind-merge` footgun the `0.6.6`–`0.6.8`
  hardening passes closed); `Action` has a `size` prop for that, and the default `md` is right
  here.
- Field naming: `Input` already falls back to its `placeholder` as `aria-label` (added in
  `0.6.7`), but per the plan I set `aria-label` **explicitly** on both fields — a password
  field's placeholder is easy to omit, and an explicit name is the robust choice.

### 3. No-change surface — audited, not edited

Confirmed (grep: no `signInWith*` references) that these derive everything from `session` /
`GET /me`, independent of *how* the session was obtained, so they needed no change:

- `lib/api.ts` — token attach is method-agnostic (`setAccessToken` → `Authorization: Bearer`).
- `lib/use-identity.ts` — `isAuthed = Boolean(session)`; `canWrite` / `isInternal` /
  `displayName` come from `/me`.
- `app/auth/callback/route.ts` — only magic-link / OAuth reach it; `signInWithPassword` returns
  a session synchronously with no `code` exchange, so the password path **never** touches the
  open-redirect-hardened callback (no new CWE-601 surface).
- `lib/supabase.ts`, `providers/dev-actor-provider.tsx` — untouched. Dev mode
  (`NEXT_PUBLIC_AUTH_DEV` + `X-Dev-Actor-Id`) is purely the non-`isSupabaseConfigured` branch
  and is unaffected.
- **Entire `backend/`** — untouched.

---

## Supabase prerequisites (config, not code — out of band)

These are dashboard / Admin-API steps on the live Supabase project; **none are in the repo**
and none are required for the build to pass, but they gate the *manual* acceptance:

1. **Email provider with password sign-in enabled** (Auth → Providers → Email). Already enabled
   for magic-link; confirm `signInWithPassword` is not disabled at the project level.
2. **Users have passwords and are confirmed** — created via the dashboard "Add user" (with a
   password, which auto-confirms) or the Admin API
   (`auth.admin.createUser({ email, password, email_confirm: true })`). A magic-link-only user
   has **no** password and cannot use this path until an admin sets one; an **unconfirmed** user
   hits "Email not confirmed".
3. *(Optional)* password policy / leaked-password protection — orthogonal.

---

## Verification

- **Frontend build gates (reproduced):**
  - `npm run typecheck` → clean (`tsc --noEmit`, no output).
  - `npm run lint` → clean (`eslint .`, no output).
  - `npm run build` → success; **6/6** routes generate (`/`, `/_not-found`, `/auth/callback`,
    `/projects/[projectId]`, `/styleguide`, root).
- **Scope check:** `git diff --stat` shows exactly the two intended files; the no-change
  surface has zero `signInWith*` references.
- **Backend:** unchanged — no backend file touched, so the existing `9 passed, 47 skipped`
  default DB-free suite and the JWT `401`-matrix / JIT-provision coverage remain authoritative
  and method-agnostic. Not re-run here (nothing to re-run).
- **Manual (needs a real browser + configured Supabase) — not yet performed:**
  1. Admin-create a confirmed password user (prereq 2).
  2. Open the menu → password form is primary; enter credentials → signed in without leaving
     the page; the menu shows the display name; the `internal` shield appears iff the email is
     in `INTERNAL_ACTOR_EMAILS`; write actions (New project, record checkpoint, …) become
     enabled — confirming `/me` JIT-provisioned / resolved the `Actor`.
  3. Wrong password → "Invalid login credentials" in the error line; not signed in.
  4. Sign out clears the session and cached actor-scoped reads (`queryClient.clear()`).
  5. Magic-link and Google still work (regression check of the retained paths).

---

## Risks & watch-items (carried from the plan)

- **Unconfirmed user → "Email not confirmed".** Mitigation: admin-create with
  `email_confirm: true`. The raw Supabase message is surfaced so the cause is legible.
- **Password sign-in disabled at the project level** → Supabase returns e.g. "Email logins are
  disabled"; the error line shows it rather than failing silently.
- **Magic-link-only users have no password** — expected; they keep using magic-link until an
  admin sets one. Not a bug.
- **Brute-force / enumeration** — relying on Supabase GoTrue's built-in auth rate limits; we
  add none of our own. Out of scope, recorded as a decision.

## Out of scope (explicitly, per the plan)

Self-service sign-up, password-reset / "forgot password" UI, any backend change / new test /
schema / migration, server-side rate-limiting, and removal of magic-link or Google.
