import { Activity, AlertCircle } from "lucide-react";
import type { ReactNode } from "react";

// Shared loading / error / empty placeholders so every panel renders the three states
// the same way (plan 0.3.3 exit criterion).

export function PanelLoading({ label }: { label: string }) {
  return (
    <div className="grid min-h-32 place-items-center rounded-md border border-line bg-white/60 p-4">
      <div className="flex items-center gap-2 text-sm text-ink/65">
        <Activity className="size-4 animate-pulse text-signal" aria-hidden="true" />
        {label}
      </div>
    </div>
  );
}

export function PanelError({ label }: { label: string }) {
  return (
    <div className="grid min-h-32 place-items-center rounded-md border border-ember/30 bg-white/70 p-4 text-center">
      <div className="flex items-center gap-2 text-sm text-ink/70">
        <AlertCircle className="size-4 text-ember" aria-hidden="true" />
        {label}
      </div>
    </div>
  );
}

export function PanelEmpty({ icon, children }: { icon?: ReactNode; children: ReactNode }) {
  return (
    <div className="grid min-h-32 place-items-center rounded-md border border-dashed border-line bg-white/50 p-4 text-center">
      <div className="max-w-xs text-sm leading-6 text-ink/60">
        {icon ? <div className="mb-2 grid place-items-center text-signal">{icon}</div> : null}
        {children}
      </div>
    </div>
  );
}
