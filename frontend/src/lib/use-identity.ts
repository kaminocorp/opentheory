"use client";

import { useQuery } from "@tanstack/react-query";

import { getMe } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useAuth } from "@/providers/auth-provider";
import type { Me } from "@/types/research";

export type ActingIdentity = {
  hydrated: boolean;
  canWrite: boolean;
  isAuthed: boolean;
  me: Me | null;
  roles: string[];
  isInternal: boolean;
  displayName: string | null;
  signInHint: string;
};

/**
 * The single source of "who is acting" for the UI. A verified Supabase session is the only
 * write credential (the legacy dev-actor path was removed); this resolves the backend actor via
 * GET /me and exposes write-gating + role flags. `me` is keyed by the session user so signing in
 * or out refetches the right actor. Without a session the app is fully readable but read-only.
 */
export function useActingIdentity(): ActingIdentity {
  const { session, loading: authLoading } = useAuth();

  const isAuthed = Boolean(session);
  const credentialKey = isAuthed ? `auth:${session?.user.id}` : "none";

  const meQuery = useQuery<Me>({
    queryKey: [...queryKeys.me, credentialKey],
    queryFn: getMe,
    enabled: isAuthed,
    staleTime: 60_000,
  });
  const me = meQuery.data ?? null;
  // Roles live on the owning account now (0.7.0, Account-owns-Actor); /me nests it. The hook's
  // public shape ({ roles, isInternal, ... }) is unchanged, so consumers don't change.
  const roles = me?.account?.roles ?? [];

  // Identity is "settled" once auth finishes and — when signed in — the backend actor has
  // resolved (success or error). Gating the sign-in hint on this avoids a flash of "sign in to
  // contribute" while /me is still in flight for an already-authenticated user.
  const identitySettled = !authLoading && (!isAuthed || !meQuery.isPending);

  return {
    hydrated: identitySettled,
    // Require a *resolved* backend actor — the same source of truth as isInternal — so the UI
    // never enables a write before /me confirms the identity (or after that resolution fails).
    canWrite: isAuthed && meQuery.isSuccess,
    isAuthed,
    me,
    roles,
    isInternal: roles.includes("internal"),
    displayName: me?.display_name ?? session?.user.email ?? null,
    signInHint: "Sign in to contribute",
  };
}
