"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

// Dev identity for 0.3.x: there is no auth. The selected actor's id is attached as the
// X-Dev-Actor-Id header on every write. The selection persists in localStorage so it
// survives reloads. Replaced by real auth in 0.6.0.

const STORAGE_KEY = "opentheory.dev-actor-id";

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
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored) {
        setActorIdState(stored);
      }
    } catch {
      // localStorage unavailable (private mode, SSR) — fall back to in-memory only
    }
    setHydrated(true);
  }, []);

  const setActorId = useCallback((next: string | null) => {
    setActorIdState(next);
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
