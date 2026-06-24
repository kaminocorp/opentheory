"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { setDevActorId } from "@/lib/api";

// Dev identity: when NEXT_PUBLIC_AUTH_DEV is set there is no IdP, and the selected actor's id
// is attached as the X-Dev-Actor-Id header on every request. The selection persists in
// localStorage so it survives reloads. In production this is retired in favour of real auth
// (AuthProvider); the provider stays mounted but the switcher is only shown in dev mode.

const STORAGE_KEY = "opentheory.dev-actor-id";

// Defined locally (not imported from use-identity, which imports this module) to avoid a cycle.
// In production this is false, so the dev-actor path is fully inert.
const AUTH_DEV = process.env.NEXT_PUBLIC_AUTH_DEV === "true";

type DevActorContextValue = {
  actorId: string | null;
  setActorId: (actorId: string | null) => void;
  hydrated: boolean;
};

const DevActorContext = createContext<DevActorContextValue | null>(null);

export function DevActorProvider({ children }: { children: ReactNode }) {
  const [actorId, setActorIdState] = useState<string | null>(null);
  // Avoid a hydration mismatch: read localStorage only after mount.
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    // In production (AUTH_DEV off) there is no dev actor: skip reading localStorage and never
    // push X-Dev-Actor-Id, so a stale id from a prior dev session in this browser can't leak
    // onto real requests. Still mark hydrated so identity gating settles.
    if (!AUTH_DEV) {
      setHydrated(true);
      return;
    }
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored) {
        setActorIdState(stored);
        setDevActorId(stored); // sync the api client before any write fires
      }
    } catch {
      // localStorage unavailable (private mode, SSR) — fall back to in-memory only
    }
    setHydrated(true);
  }, []);

  const setActorId = useCallback((next: string | null) => {
    setActorIdState(next);
    // Sync the api client synchronously so the next request carries the right header
    // (no effect-ordering race against TanStack refetching /me on the credential change).
    setDevActorId(next);
    try {
      if (next) {
        window.localStorage.setItem(STORAGE_KEY, next);
      } else {
        window.localStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      // ignore persistence failures
    }
  }, []);

  const value = useMemo(
    () => ({ actorId, setActorId, hydrated }),
    [actorId, setActorId, hydrated],
  );

  return <DevActorContext.Provider value={value}>{children}</DevActorContext.Provider>;
}

export function useDevActor(): DevActorContextValue {
  const ctx = useContext(DevActorContext);
  if (!ctx) {
    throw new Error("useDevActor must be used within a DevActorProvider");
  }
  return ctx;
}
