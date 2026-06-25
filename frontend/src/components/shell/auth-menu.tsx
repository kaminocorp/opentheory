"use client";

import { useQueryClient } from "@tanstack/react-query";
import { LogOut, Mail, ShieldCheck, UserCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Action, Icon, Input } from "@/components/console";
import { useActingIdentity } from "@/lib/use-identity";
import { useAuth } from "@/providers/auth-provider";

// The real-auth identity surface (0.6.2): signed-in name + roles + sign-out, or a sign-in
// dropdown (email magic-link / Google). Renders nothing when Supabase is not configured —
// in that case local work uses the dev-actor switcher instead.
//
// D2 re-skin: console tokens + primitives only. Every hook, handler, effect, and conditional
// return below is unchanged from 0.6.2 — this is presentation, not behaviour.
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
    return <span className="px-2 text-[13px] text-text-mute">…</span>;
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
              <button
                type="button"
                onClick={() => signInWithGoogle()}
                className="mb-3 flex w-full items-center justify-center gap-2 rounded-full px-3 py-2 text-[13px] font-medium text-text transition-colors hover:border-text"
                style={{ border: "0.5px solid var(--hairline-strong)" }}
              >
                Continue with Google
              </button>
              <p className="mb-2 text-center text-[11px] text-text-faint">or a magic link</p>
              <form
                className="flex items-center gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (email.trim()) handleEmailSignIn();
                }}
              >
                <Input
                  mono
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@example.com"
                  className="h-9 min-w-0 flex-1"
                />
                <button
                  type="submit"
                  disabled={!email.trim()}
                  className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full bg-signal px-3 text-[13px] font-medium text-ground transition-colors hover:bg-signal-strong disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <Icon icon={Mail} size={16} />
                  Send
                </button>
              </form>
              {error ? <p className="mt-2 text-[11px] text-state-fail">{error}</p> : null}
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
