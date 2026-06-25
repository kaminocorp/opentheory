import { CircleDollarSign, GitBranch, ShieldCheck } from "lucide-react";

import { Bay, Icon, ReadoutLabel } from "@/components/console";
import { ProjectsSection } from "@/components/projects/projects-section";
import { AppShell } from "@/components/shell/app-shell";

const metrics = [
  { label: "Active Threads", value: "Parallel", icon: GitBranch },
  { label: "Validation", value: "Provenance", icon: ShieldCheck },
  { label: "Budgeting", value: "Token-bound", icon: CircleDollarSign },
];

export default function Home() {
  return (
    <AppShell>
      <section className="grid gap-8">
        <div className="grid gap-6 lg:grid-cols-[1fr_360px] lg:items-end">
          <div className="max-w-3xl">
            {/* Modest console title — weight + the field carry hierarchy, not size (§3.2). */}
            <ReadoutLabel>Research Ledger</ReadoutLabel>
            <h1 className="mt-2 text-balance text-[22px] font-medium leading-snug tracking-[-0.01em] text-text sm:text-2xl">
              Continuous agent-driven research with public state, claims, and evidence.
            </h1>
            <p className="mt-4 max-w-2xl text-[14px] leading-[1.55] text-text-soft">
              OpenTheory turns funded research questions into structured projects: threads,
              checkpoints, claims, artifacts, validations, and contributor provenance.
            </p>
          </div>

          {/* A small bay of metric readouts: mono readout label + mono value (§5.5). */}
          <Bay bracketed density="none" className="self-stretch lg:self-end">
            {metrics.map((metric, index) => (
              <div
                key={metric.label}
                className="flex items-center justify-between gap-3 px-4 py-3"
                style={index > 0 ? { borderTop: "0.5px solid var(--hairline)" } : undefined}
              >
                <span className="flex min-w-0 items-center gap-2 text-text-mute">
                  <Icon icon={metric.icon} size={14} />
                  <ReadoutLabel>{metric.label}</ReadoutLabel>
                </span>
                <span className="shrink-0 font-mono text-[13px] text-text">{metric.value}</span>
              </div>
            ))}
          </Bay>
        </div>

        <ProjectsSection />
      </section>
    </AppShell>
  );
}
