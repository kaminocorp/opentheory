"use client";

import type { Session } from "@supabase/supabase-js";
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { setAccessToken } from "@/lib/api";
import { getSupabaseBrowserClient, isSupabaseConfigured } from "@/lib/supabase";

// Real identity (0.6.2): Supabase Auth issues the session JWT; this provider tracks the
// session and pushes its access token into the api client (lib/api.ts) so every request
// carries `Authorization: Bearer <token>`. When Supabase is not configured the provider is
// inert (session stays null) and the app runs in dev mode (NEXT_PUBLIC_AUTH_DEV).

type SignInResult = { error: string | null };

type AuthContextValue = {
  session: Session | null;
  loading: boolean;
  isConfigured: boolean;
  signInWithEmail: (email: string) => Promise<SignInResult>;
  signInWithPassword: (email: string, password: string) => Promise<SignInResult>;
  signInWithGoogle: () => Promise<SignInResult>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function callbackUrl(): string | undefined {
  return typeof window !== "undefined" ? `${window.location.origin}/auth/callback` : undefined;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const supabase = getSupabaseBrowserClient();
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!supabase) {
      setLoading(false);
      return;
    }
    let active = true;
    supabase.auth.getSession().then(({ data }) => {
      if (!active) return;
      // Set the token before the session state so the next render's queries see it.
      setAccessToken(data.session?.access_token ?? null);
      setSession(data.session);
      setLoading(false);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setAccessToken(nextSession?.access_token ?? null);
      setSession(nextSession);
    });
    return () => {
      active = false;
      sub.subscription.unsubscribe();
    };
  }, [supabase]);

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      loading,
      isConfigured: isSupabaseConfigured,
      signInWithEmail: async (email: string) => {
        if (!supabase) return { error: "Authentication is not configured" };
        const { error } = await supabase.auth.signInWithOtp({
          email,
          options: { emailRedirectTo: callbackUrl() },
        });
        return { error: error?.message ?? null };
      },
      // Password sign-in (0.6.9): resolves a session *in-band* (no email round-trip,
      // no redirect) — on success `onAuthStateChange` above fires synchronously and
      // pushes the token into the api client, so the caller only closes the menu.
      // Supabase issues the same session JWT here as for magic-link/OAuth, so the
      // backend verifier and the whole ActingActor path are untouched.
      signInWithPassword: async (email: string, password: string) => {
        if (!supabase) return { error: "Authentication is not configured" };
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        return { error: error?.message ?? null };
      },
      signInWithGoogle: async () => {
        if (!supabase) return { error: "Authentication is not configured" };
        const { error } = await supabase.auth.signInWithOAuth({
          provider: "google",
          options: { redirectTo: callbackUrl() },
        });
        return { error: error?.message ?? null };
      },
      signOut: async () => {
        if (supabase) await supabase.auth.signOut();
        setAccessToken(null);
        setSession(null);
      },
    }),
    [supabase, session, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
