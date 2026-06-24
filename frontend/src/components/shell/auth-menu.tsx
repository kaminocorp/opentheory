"use client";

import { useQueryClient } from "@tanstack/react-query";
import { LogOut, Mail, ShieldCheck, UserCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useActingIdentity } from "@/lib/use-identity";
import { useAuth } from "@/providers/auth-provider";

// The real-auth identity surface (0.6.2): signed-in name + roles + sign-out, or a sign-in
// dropdown (email magic-link / Google). Renders nothing when Supabase is not configured —
// in that case local work uses the dev-actor switcher instead.
export function AuthMenu() {
  const { isConfigured, session, loading, signOut, signInWithEmail, signInWithGoogle } = useAuth();
  const { displayName, isInternal } = useActingIdentity();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
    return <span className="px-2 text-sm text-ink/50">…</span>;
  }

  async function handleSignOut() {
    await signOut();
    queryClient.clear(); // drop cached actor-scoped reads on identity change
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

  if (session) {
    return (
      <div className="relative" ref={containerRef}>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex h-10 items-center gap-2 rounded-md border border-line bg-white/70 px-3 text-sm font-medium text-ink/75 hover:text-ink"
          title="Account"
        >
          <UserCircle className="size-4 shrink-0 text-signal" aria-hidden="true" />
          <span className="max-w-32 truncate">{displayName ?? "Account"}</span>
          {isInternal ? (
            <ShieldCheck className="size-4 shrink-0 text-signal" aria-label="Kamino internal" />
          ) : null}
        </button>

        {open ? (
          <div className="absolute right-0 z-20 mt-2 w-64 rounded-md border border-line bg-paper p-2 shadow-panel">
            <div className="px-2 py-1.5">
              <p className="truncate text-sm font-semibold">{displayName ?? "Signed in"}</p>
              <p className="mt-0.5 text-xs text-ink/55">
                {isInternal ? "Kamino internal · can fund" : "Contributor"}
              </p>
            </div>
            <button
              type="button"
              onClick={handleSignOut}
              className="mt-1 flex w-full items-center gap-2 rounded px-2 py-2 text-left text-sm text-ink/75 hover:bg-white/70"
            >
              <LogOut className="size-4" aria-hidden="true" />
              Sign out
            </button>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex h-10 items-center gap-2 rounded-md bg-ink px-3 text-sm font-semibold text-paper hover:bg-ink/90"
      >
        Sign in
      </button>

      {open ? (
        <div className="absolute right-0 z-20 mt-2 w-72 rounded-md border border-line bg-paper p-3 shadow-panel">
          {sent ? (
            <p className="px-1 py-2 text-sm text-ink/70">
              Check your email for a sign-in link.
            </p>
          ) : (
            <>
              <button
                type="button"
                onClick={() => signInWithGoogle()}
                className="mb-3 flex w-full items-center justify-center gap-2 rounded-md border border-line bg-white/80 px-3 py-2 text-sm font-medium hover:bg-white"
              >
                Continue with Google
              </button>
              <p className="mb-2 text-center text-xs text-ink/45">or a magic link</p>
              <form
                className="flex items-center gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (email.trim()) handleEmailSignIn();
                }}
              >
                <input
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@example.com"
                  className="h-9 min-w-0 flex-1 rounded-md border border-line bg-white/80 px-2 text-sm outline-none focus:border-signal"
                />
                <button
                  type="submit"
                  disabled={!email.trim()}
                  className="inline-flex h-9 items-center gap-1 rounded-md bg-ink px-2.5 text-sm font-semibold text-paper disabled:opacity-50"
                >
                  <Mail className="size-4" aria-hidden="true" />
                  Send
                </button>
              </form>
              {error ? <p className="mt-2 text-xs text-ember">{error}</p> : null}
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
