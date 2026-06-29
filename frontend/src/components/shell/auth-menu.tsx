"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AtSign, LogOut, Mail, ShieldCheck, UserCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Action, Icon, Input } from "@/components/console";
import { updateMe } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useActingIdentity } from "@/lib/use-identity";
import { usernameError } from "@/lib/username";
import { useAuth } from "@/providers/auth-provider";

// The real-auth identity surface (0.6.2): signed-in name + roles + sign-out, or a sign-in
// dropdown. Renders nothing when Supabase is not configured — the app is then a public,
// read-only view (Supabase sign-in is the only write credential).
//
// 0.6.9: email + password is now the primary sign-in path (resolves a session in-band, no
// email round-trip); magic-link and Google are retained as secondary options below it. The
// backend is blind to *how* the session was obtained, so this is presentation-only.
export function AuthMenu() {
  const { isConfigured, session, loading, signOut, signInWithEmail, signInWithPassword, signInWithGoogle } =
    useAuth();
  const { displayName, isInternal, me } = useActingIdentity();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Inline `@username` editor (0.8.3). The handle lives on the owning account; PATCH /me renames it.
  const username = me?.account?.username ?? null;
  const [editingHandle, setEditingHandle] = useState(false);
  const [handleDraft, setHandleDraft] = useState("");
  const [handleError, setHandleError] = useState<string | null>(null);

  const renameMutation = useMutation({
    mutationFn: (nextUsername: string) => updateMe({ username: nextUsername }),
    onSuccess: () => {
      // useActingIdentity keys /me as ["me", credentialKey]; invalidating the ["me"] prefix
      // refetches it so the new handle shows immediately.
      queryClient.invalidateQueries({ queryKey: queryKeys.me });
      setEditingHandle(false);
      setHandleError(null);
    },
    // request() throws Error("409: That username is already taken"); strip the status prefix.
    onError: (err: unknown) =>
      setHandleError(
        err instanceof Error ? err.message.replace(/^\d+:\s*/, "") : "Could not update username",
      ),
  });

  function startEditHandle() {
    setHandleDraft(username ?? "");
    setHandleError(null);
    setEditingHandle(true);
  }

  function submitHandle() {
    if (renameMutation.isPending) return; // guard a double-submit (Enter) while a rename is in flight
    const next = handleDraft.trim().toLowerCase();
    if (!next || next === username) {
      setEditingHandle(false); // no-op rename — just close
      return;
    }
    // Validate against the backend rules client-side: gives a legible message (not the server's raw
    // 422 body) and skips a round-trip for obviously-bad input. The DB uniqueness 409 still comes
    // from the server.
    const invalid = usernameError(next);
    if (invalid) {
      setHandleError(invalid);
      return;
    }
    renameMutation.mutate(next);
  }

  useEffect(() => {
    if (!open) return;
    function onClick(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  // Without Supabase configured there is no sign-in to show; the app stays read-only.
  if (!isConfigured) return null;
  if (loading) {
    return <span className="px-2 text-[13px] text-text-mute">…</span>;
  }

  async function handleSignOut() {
    await signOut();
    queryClient.clear(); // drop cached actor-scoped reads on identity change
    setPassword(""); // never retain the secret in component state across an identity change
    setEditingHandle(false); // reset the handle editor for the next principal
    setOpen(false);
  }

  async function handleEmailSignIn() {
    setError(null);
    const { error: signInError } = await signInWithEmail(email.trim());
    if (signInError) {
      setError(signInError);
      return;
    }
    setSent(true);
  }

  async function handlePasswordSignIn() {
    if (submitting) return; // guard against double-submit while a request is in flight
    setError(null);
    setSubmitting(true);
    try {
      const { error: signInError } = await signInWithPassword(email.trim(), password);
      if (signInError) {
        setError(signInError); // e.g. "Invalid login credentials" / "Email not confirmed"
        return;
      }
      setPassword(""); // don't leave the secret in component state after a successful sign-in
      setOpen(false); // session arrives via onAuthStateChange; queries refetch under the new credential
    } finally {
      setSubmitting(false);
    }
  }

  if (session) {
    return (
      <div className="relative" ref={containerRef}>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex h-9 items-center gap-2 rounded-full px-3 text-[13px] font-medium text-text transition-colors hover:border-text"
          style={{ border: "0.5px solid var(--hairline-strong)" }}
          title="Account"
        >
          <Icon icon={UserCircle} size={16} className="text-text-mute" />
          <span className="max-w-32 truncate">{displayName ?? "Account"}</span>
          {isInternal ? (
            <Icon icon={ShieldCheck} size={16} className="text-signal" aria-label="Kamino internal" />
          ) : null}
        </button>

        {open ? (
          <div className="menu menu-pop absolute right-0 z-40 mt-2 w-64 p-2">
            <div className="px-2 py-1.5">
              <p className="truncate text-[13px] font-medium text-text">{displayName ?? "Signed in"}</p>
              {username && !editingHandle ? (
                <button
                  type="button"
                  onClick={startEditHandle}
                  className="mt-0.5 flex items-center gap-1 text-xs text-text-mute transition-colors hover:text-text"
                  title="Edit username"
                >
                  <Icon icon={AtSign} size={12} />
                  <span className="truncate">{username}</span>
                </button>
              ) : null}
              <p className="mt-0.5 text-xs text-text-mute">
                {isInternal ? "Kamino internal · can fund" : "Contributor"}
              </p>
            </div>

            {editingHandle ? (
              <form
                className="px-2 py-1.5"
                onSubmit={(event) => {
                  event.preventDefault();
                  submitHandle();
                }}
              >
                <Input
                  mono
                  autoFocus
                  value={handleDraft}
                  onChange={(event) => setHandleDraft(event.target.value)}
                  placeholder="username"
                  aria-label="Username"
                  spellCheck={false}
                  autoComplete="off"
                  className="h-8"
                />
                <div className="mt-1.5 flex items-center gap-2">
                  <Action type="submit" size="sm" pending={renameMutation.isPending}>
                    Save
                  </Action>
                  <button
                    type="button"
                    onClick={() => setEditingHandle(false)}
                    className="text-xs text-text-mute transition-colors hover:text-text"
                  >
                    Cancel
                  </button>
                </div>
                {handleError ? (
                  <p role="alert" className="mt-1 text-[11px] text-state-fail">
                    {handleError}
                  </p>
                ) : null}
              </form>
            ) : null}

            <button
              type="button"
              onClick={handleSignOut}
              className="mt-1 flex w-full items-center gap-2 rounded-built px-2 py-2 text-left text-[13px] text-text-soft transition-colors hover:bg-panel-2"
            >
              <Icon icon={LogOut} size={16} />
              Sign out
            </button>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="relative" ref={containerRef}>
      <Action onClick={() => setOpen((v) => !v)}>Sign in</Action>

      {open ? (
        <div className="menu menu-pop absolute right-0 z-40 mt-2 w-72 p-3">
          {sent ? (
            <p className="px-1 py-2 text-[13px] text-text-soft">Check your email for a sign-in link.</p>
          ) : (
            <>
              {/* Primary path: email + password, resolves a session in-band. */}
              <form
                className="flex flex-col gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (email.trim() && password) handlePasswordSignIn();
                }}
              >
                <Input
                  mono
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@example.com"
                  aria-label="Email"
                  autoComplete="username"
                  className="h-9"
                />
                <Input
                  mono
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Password"
                  aria-label="Password"
                  autoComplete="current-password"
                  className="h-9"
                />
                <Action
                  type="submit"
                  pending={submitting}
                  disabled={!email.trim() || !password}
                  className="w-full"
                >
                  Sign in
                </Action>
              </form>

              {/* Secondary paths: magic-link + Google (retained, demoted below the divider). */}
              <p className="my-3 text-center text-[11px] text-text-faint">or</p>
              <button
                type="button"
                onClick={handleEmailSignIn}
                disabled={!email.trim()}
                className="mb-2 flex w-full items-center justify-center gap-2 rounded-full px-3 py-2 text-[13px] font-medium text-text transition-colors hover:border-text disabled:cursor-not-allowed disabled:opacity-50"
                style={{ border: "0.5px solid var(--hairline-strong)" }}
              >
                <Icon icon={Mail} size={16} />
                Email me a magic link
              </button>
              <button
                type="button"
                onClick={() => signInWithGoogle()}
                className="flex w-full items-center justify-center gap-2 rounded-full px-3 py-2 text-[13px] font-medium text-text transition-colors hover:border-text"
                style={{ border: "0.5px solid var(--hairline-strong)" }}
              >
                Continue with Google
              </button>
              {error ? (
                <p role="alert" className="mt-2 text-[11px] text-state-fail">
                  {error}
                </p>
              ) : null}
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
