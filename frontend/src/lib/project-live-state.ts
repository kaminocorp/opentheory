"use client";

import { useSyncExternalStore } from "react";

/**
 * Cross-tab "a pass is running" chrome (0.31.0). The workspace already polls
 * the newest keep-alive `AgentRun` for the Instruments badge — this store
 * republishes that boolean so the CommandRail can show the same live tick
 * without a second fetch. Off-project / unmount → idle.
 */

type Listener = () => void;

let passRunning = false;
const listeners = new Set<Listener>();

function emit() {
  for (const listener of listeners) listener();
}

export function setProjectPassRunning(next: boolean) {
  if (passRunning === next) return;
  passRunning = next;
  emit();
}

export function getProjectPassRunning() {
  return passRunning;
}

export function subscribeProjectPassRunning(listener: Listener) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useProjectPassRunning() {
  return useSyncExternalStore(subscribeProjectPassRunning, getProjectPassRunning, () => false);
}
