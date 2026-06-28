"use client";

import { useQueryClient } from "@tanstack/react-query";
import { LogOut, Mail, ShieldCheck, UserCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Action, Icon, Input } from "@/components/console";
import { useActingIdentity } from "@/lib/use-identity";
import { useAuth } from "@/providers/auth-provider";

// The real-auth identity surface (0.6.2): signed-in name + roles + sign-out, or a sign-in
// dropdown. Renders nothing when Supabase is not configured — in that case local work uses
// the dev-actor switcher instead.
//
// 0.6.9: email + password is now the primary sign-in path (resolves a session in-band, no
// email round-trip); magic-link and Google are retained as secondary options below it. The
// backend is blind to *how* the session was obtained, so this is presentation-only.
export function AuthMenu() {
  const { isConfigured, session, loading, signOut, signInWithEmail, signInWithPassword, signInWithGoogle } =
    useAuth();
  const { displayName, isInternal } = useActingIdentity();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

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

  // Without Supabase configured there is no real auth to show; dev mode uses DevActorSwitcher.
  if (!isConfigured) return null;
  if (loading) {
    return <span className="px-2 text-[13px] text-text-mute">…</span>;
  }

  async function handleSignOut() {
    await signOut();
    queryClient.clear(); // drop cached actor-scoped reads on identity change
    setPassword(""); // never retain the secret in component state across an identity change
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
              <p className="mt-0.5 text-xs text-text-mute">
                {isInternal ? "Kamino internal · can fund" : "Contributor"}
              </p>
            </div>
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
