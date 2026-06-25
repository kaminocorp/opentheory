import { AwaitingState } from "@/components/console";

// Shared loading / error / empty states for every instrument panel (plan 0.3.3
// exit criterion). D5 re-skin: thin wrappers over the §5.9 AwaitingState — "the
// mark holds the frame". Loading breathes; error/empty hold steady (read
// "stopped", not "loading"), and error renders at full --state-fail weight (§1).
// Call signatures stay drop-in (a single string), so the panels need no logic change.

export function PanelLoading({ label }: { label: string }) {
  return <AwaitingState variant="loading" label={label} />;
}

export function PanelError({ label }: { label: string }) {
  return <AwaitingState variant="error" label={label} />;
}

export function PanelEmpty({ children }: { children: string }) {
  return <AwaitingState variant="empty" label={children} />;
}
