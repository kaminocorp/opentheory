# Auth — Email + Password Sign-In

> Add **email + password** as the primary sign-in method, authenticating directly against
> existing `auth.users` rows (Supabase GoTrue). Magic-link and Google are **kept** as secondary
> options. This is a **frontend-only** change: the backend verifies a Supabase session JWT and is
> blind to *how* that session was obtained, so no backend, schema, API, or migration changes.

## Goal

When a user opens the sign-in menu, the first thing they see is an **email + password** form. A
correct credential signs them in immediately (no email round-trip), the verified token is attached
to every backend request exactly as today, and `GET /me` JIT-provisions / resolves their `Actor`.
Magic-link and "Continue with Google" remain available below the password form for users who prefer
them.

## The load-bearing fact: the backend does not change

`backend/app/core/auth.py::verify_bearer_token` only verifies a bearer JWT's **signature,
audience (`aud="authenticated"`), and expiry**, then reads `sub`/`email`/`user_metadata`. Supabase
issues the **same** HS256-signed session token for *every* sign-in method — magic-link, OAuth, and
`signInWithPassword` are indistinguishable once a session exists. Therefore:

- `core/auth.py`, `api/deps.py`, `models/actor.py`, `api/routes/me.py`, every service — **untouched**.
- No new env var, no migration, no schema change.
- The existing `ActingActor` contract, JIT-provisioning, and `internal`-role logic apply verbatim.

This is the same seam the module docstring advertises ("swapping IdP changes only this file +
config") working in our favour: adding an *authentication method* on the IdP side is invisible to
the verifier.

### Data-model note (for the reader): `Actor` is not `auth.users`

Two identity records in two schemas, linked 1:1 for humans:

| | `auth.users` (Supabase, `auth` schema) | `Actor` (`public.actors`, ours) |
|---|---|---|
| Role | **Authentication** — email, `encrypted_password`, providers | **Domain identity** — provenance / attribution |
| Password check | ✅ here (what this plan logs into) | ❌ never sees a password |
| Link | `auth.users.id` | `Actor.external_id` (= JWT `sub`) |

There is **no `public.users` table** — OpenTheory's "user" *is* `public.actors`. `ActorType` is
`human | agent | system`, so `Actor` is the **superset**: a signed-in human ⇄ one `auth.users` row;
**agents and the system actor are `actors` rows with `external_id = NULL`** and no auth record. This
plan only adds a login method for the *human* subset; it does not touch the agent/system path.

## Decisions (locked before planning)

1. **Password is the primary form; magic-link + Google are retained as secondary.** The signed-out
   dropdown leads with the email + password form (Enter-to-submit), then a divider, then "Email me a
   magic link" and "Continue with Google". Nothing is removed.
2. **Sign-in only — no sign-up, no password-reset UI.** Users are **admin-provisioned** with
   passwords (Supabase dashboard / Admin API). A user with no password simply cannot use the password
   path until an admin sets one; that provisioning is out of band (see *Supabase prerequisites*).
3. **The `/auth/callback` route is left in place, unused by this path.** `signInWithPassword`
   returns a session synchronously — there is no `code` exchange and no redirect — so the password
   flow never touches the open-redirect-hardened callback. Magic-link and Google still use it.
4. **Dev mode is untouched.** The `X-Dev-Actor-Id` switcher (`NEXT_PUBLIC_AUTH_DEV`) and its backend
   flag are unchanged; password sign-in is purely the real-auth (`isSupabaseConfigured`) branch.

## Out of scope (explicitly)

- Self-service **sign-up** (`supabase.auth.signUp`) and any email-confirmation UX.
- **Password reset / "forgot password"** (`resetPasswordForEmail` + update).
- Any **backend** change, new test, schema, or migration.
- Server-side **rate-limiting** of password attempts — Supabase GoTrue enforces auth rate limits;
  we add none of our own.
- Removing magic-link or Google (Decision 1).

## Supabase prerequisites (config, not code — do these first)

These are dashboard/Admin-API steps on the live Supabase project. None are committed in the repo.

1. **Email provider with password sign-in enabled.** Auth → Providers → **Email**: the provider must
   be enabled (it already is — magic-link works) and password-based sign-in allowed. Confirm
   `signInWithPassword` is not disabled at the project level.
2. **Users have passwords and are confirmed.** Create each user via the dashboard ("Add user" with a
   password, which auto-confirms) or the Admin API
   (`auth.admin.createUser({ email, password, email_confirm: true })`). An **unconfirmed** user hits
   `signInWithPassword` → *"Email not confirmed"*; a user created via magic-link only has **no
   password** and cannot use this path until one is set.
3. **(Optional) password policy / leaked-password protection** under Auth settings — orthogonal to
   this change.

> Acceptance for the prereqs: a throwaway test user created with a password can be signed in from the
> Supabase dashboard's own tooling before any UI work begins.

## Implementation

Two files change. Both are in the real-auth branch already gated by `isSupabaseConfigured`.

### Step 1 — `frontend/src/providers/auth-provider.tsx`: expose `signInWithPassword`

Add the method to the context type and implement it. The provider's existing
`onAuthStateChange` subscription already pushes the new token into the api client and updates
`session`, so the method just needs to call Supabase and surface any error.

```ts
// in AuthContextValue
signInWithPassword: (email: string, password: string) => Promise<SignInResult>;
```

```ts
// in the useMemo value, alongside signInWithEmail / signInWithGoogle
signInWithPassword: async (email: string, password: string) => {
  if (!supabase) return { error: "Authentication is not configured" };
  const { error } = await supabase.auth.signInWithPassword({ email, password });
  return { error: error?.message ?? null };
},
```

Notes:
- The `useMemo` dep array (`[supabase, session, loading]`) already covers the only captured value
  (`supabase`); no dep change.
- Unlike magic-link, this resolves a session **in-band** — on success `onAuthStateChange` fires
  synchronously and `setAccessToken`/`setSession` run, so the caller only needs to close the menu.
- Return shape matches the existing `SignInResult` (`{ error: string | null }`) so the menu treats
  all three methods uniformly.

### Step 2 — `frontend/src/components/shell/auth-menu.tsx`: password form as the primary path

Currently the signed-out dropdown's primary `<form>` does magic-link (`handleEmailSignIn`) and shows
Google above it. Reorder so **email + password** is the primary form; demote magic-link to a button.

State + hook additions:
```ts
const { /* … */ signInWithEmail, signInWithGoogle, signInWithPassword } = useAuth();
const [password, setPassword] = useState("");
```

New handler (mirrors `handleEmailSignIn`'s error handling):
```ts
async function handlePasswordSignIn() {
  setError(null);
  const { error: signInError } = await signInWithPassword(email.trim(), password);
  if (signInError) {
    setError(signInError);     // e.g. "Invalid login credentials" / "Email not confirmed"
    return;
  }
  setOpen(false);              // session arrives via onAuthStateChange; queries refetch under the new credential
}
```

Dropdown structure (signed-out), top to bottom:
1. **Primary `<form onSubmit>`** → `handlePasswordSignIn`:
   - Email `Input`: `type="email"`, `autoComplete="username"`, `aria-label="Email"`, existing value/onChange.
   - Password `Input`: `type="password"`, `autoComplete="current-password"`, `aria-label="Password"`,
     `value={password}` / `onChange`. (The `0.6.7` placeholder→`aria-label` fallback covers naming,
     but set `aria-label` explicitly since a password field's placeholder is easy to omit.)
   - Submit button "Sign in", disabled unless `email.trim() && password`.
2. **Divider** ("or").
3. **"Email me a magic link"** button → calls `handleEmailSignIn` (keep the existing `sent` state and
   its "Check your email for a sign-in link." confirmation copy).
4. **"Continue with Google"** button → `signInWithGoogle()` (unchanged).
5. **Error line**: reuse the existing `{error ? … : null}` `text-state-fail` row beneath the form.

Keep the click-outside `useEffect`, the `containerRef`, and the signed-in branch (name + roles +
sign out) exactly as-is. The `sent` flow stays scoped to the magic-link button only — a password
attempt never sets `sent`.

### Step 3 — Confirm the no-change surface (audit, no edits)

Verify these need **no** change (they don't, but confirm during the pass):
- `lib/api.ts` — token attach is method-agnostic (`setAccessToken` / `Authorization: Bearer`).
- `lib/use-identity.ts` — `isAuthed = Boolean(session)`; `canWrite`/`isInternal`/`displayName` are
  derived from `/me`, all independent of sign-in method.
- `app/auth/callback/route.ts` — only magic-link/OAuth reach it (Decision 3).
- `lib/supabase.ts`, `providers/dev-actor-provider.tsx` — untouched.
- **Entire `backend/`** — untouched.

## Verification

- **Frontend build gates:** `npm run typecheck`, `npm run lint`, `npm run build` all green; the 6
  existing routes still generate.
- **Manual (real auth configured):**
  1. Admin-create a confirmed user with a password (prereq 2).
  2. Open the menu → password form is primary. Enter credentials → signed in without leaving the
     page; menu shows the display name; `internal` shield appears iff the email is in
     `INTERNAL_ACTOR_EMAILS`; write actions (New project, record checkpoint, …) become enabled,
     confirming `/me` provisioned/resolved the `Actor`.
  3. **Wrong password** → "Invalid login credentials" surfaced in the error line; not signed in.
  4. **Sign out** clears the session and cached actor-scoped reads (`queryClient.clear()` already
     wired).
  5. **Magic-link** and **Google** still work (regression check of the retained paths).
- **Backend:** unchanged — no new tests. The JWT verification path (`401` matrix, JIT-provision) is
  already covered and is method-agnostic, so the existing suite remains authoritative
  (`pytest` unchanged; DB-backed tests skip per policy without a configured Postgres).

## Risks & watch-items

- **Unconfirmed user → "Email not confirmed".** Mitigation: admin-create with `email_confirm: true`
  (prereq 2). Surface the raw Supabase message so the cause is legible.
- **Password sign-in disabled at the Supabase project level** → Supabase returns an error like
  "Email logins are disabled". Caught by prereq 1; the error line shows it rather than failing
  silently.
- **Magic-link-only users have no password.** Expected (Decision 2): they keep using magic-link until
  an admin sets a password. Not a bug.
- **No new redirect surface.** The password path doesn't touch `/auth/callback`, so it introduces no
  CWE-601 exposure; the existing `safeNext` hardening still guards the magic-link/OAuth paths.
- **Brute-force / enumeration.** Relying on Supabase GoTrue's built-in auth rate limits; we add none.
  Out of scope, noted so it's a decision, not an oversight.

## Changelog / versioning

Small, additive, frontend-only **feature** (a new sign-in method) → propose **`0.6.9`**. On
completion, add a `docs/changelog.md` entry noting: password sign-in primary, magic-link + Google
retained, **no** backend/schema/migration, the Supabase prereqs as the only non-code step, and the
build gates reproduced. Backend behavior and the `9 passed, 47 skipped` default suite are unchanged.
