"use client";

import { useQuery } from "@tanstack/react-query";

import { getMe } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useAuth } from "@/providers/auth-provider";
import { useDevActor } from "@/providers/dev-actor-provider";
import type { Me } from "@/types/research";

// Public dev flag: when set, the X-Dev-Actor-Id path + actor switcher are available for local
// work. In production it is unset and only real (Supabase) sign-in grants write access.
export const AUTH_DEV = process.env.NEXT_PUBLIC_AUTH_DEV === "true";

export type ActingIdentity = {
  hydrated: boolean;
  canWrite: boolean;
  isAuthed: boolean;
  isDev: boolean;
  me: Me | null;
  roles: string[];
  isInternal: boolean;
  displayName: string | null;
  signInHint: string;
};

/**
 * The single source of "who is acting" for the UI. Combines the verified Supabase session and
 * the dev-actor selection into one credential, resolves the backend actor via GET /me (which
 * works for both paths), and exposes write-gating + role flags. `me` is keyed by the active
 * credential so switching identity refetches the right actor.
 */
export function useActingIdentity(): ActingIdentity {
  const { session, loading: authLoading } = useAuth();
  const { actorId, hydrated: devHydrated } = useDevActor();

  const isAuthed = Boolean(session);
  const isDev = AUTH_DEV && Boolean(actorId);
  const hasCredential = isAuthed || isDev;

  const credentialKey = isAuthed
    ? `auth:${session?.user.id}`
    : isDev
      ? `dev:${actorId}`
      : "none";

  const meQuery = useQuery<Me>({
    queryKey: [...queryKeys.me, credentialKey],
    queryFn: getMe,
    enabled: hasCredential,
    staleTime: 60_000,
  });
  const me = meQuery.data ?? null;
  const roles = me?.roles ?? [];

  // Identity is "settled" once auth + dev hydration finish and — when a credential is present —
  // the backend actor has resolved (success or error). Gating the sign-in hint on this avoids a
  // flash of "sign in to contribute" while /me is still in flight for an already-credentialed user.
  const identitySettled = !authLoading && devHydrated && (!hasCredential || !meQuery.isPending);

  return {
    hydrated: identitySettled,
    // Require a *resolved* backend actor — the same source of truth as isInternal — so the UI
    // never enables a write before /me confirms the identity (or after that resolution fails).
    canWrite: hasCredential && meQuery.isSuccess,
    isAuthed,
    isDev,
    me,
    roles,
    isInternal: roles.includes("internal"),
    displayName: me?.display_name ?? session?.user.email ?? null,
    signInHint: AUTH_DEV ? "Select a dev actor to contribute" : "Sign in to contribute",
  };
}
