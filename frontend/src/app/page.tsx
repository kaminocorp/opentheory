import { CircleDollarSign, GitBranch, ShieldCheck } from "lucide-react";

import { ProjectList } from "@/components/projects/project-list";
import { SiteHeader } from "@/components/shell/site-header";

const metrics = [
  {
    label: "Active Threads",
    value: "Parallel",
    icon: GitBranch,
  },
  {
    label: "Validation",
    value: "Provenance",
    icon: ShieldCheck,
  },
  {
    label: "Budgeting",
    value: "Token-bound",
    icon: CircleDollarSign,
  },
];

export default function Home() {
  return (
    <main className="min-h-screen">
      <SiteHeader />

      <section className="mx-auto grid max-w-7xl gap-8 px-4 py-8 sm:px-6 lg:px-8">
        <div className="grid gap-6 lg:grid-cols-[1fr_360px] lg:items-end">
          <div className="max-w-3xl">
            <p className="mb-3 text-sm font-semibold uppercase tracking-[0.14em] text-signal">
              Research Ledger
            </p>
            <h1 className="text-balance text-4xl font-semibold leading-tight sm:text-5xl">
              Continuous agent-driven research with public state, claims, and evidence.
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-ink/70">
              OpenTheory turns funded research questions into structured projects: threads,
              checkpoints, claims, artifacts, validations, and contributor provenance.
            </p>
          </div>

          <div className="grid gap-3 rounded-lg border border-line bg-white/70 p-4 shadow-panel">
            {metrics.map((metric) => (
              <div
                className="flex items-center justify-between gap-4 border-b border-line pb-3 last:border-0 last:pb-0"
                key={metric.label}
              >
                <span className="flex min-w-0 items-center gap-3 text-sm text-ink/70">
                  <metric.icon className="size-4 shrink-0 text-signal" aria-hidden="true" />
                  <span className="truncate">{metric.label}</span>
                </span>
                <span className="shrink-0 text-sm font-semibold">{metric.value}</span>
              </div>
            ))}
          </div>
        </div>

        <section className="grid gap-4">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-2xl font-semibold">Projects</h2>
              <p className="mt-1 text-sm text-ink/65">Live research surfaces backed by the FastAPI ledger.</p>
            </div>
            <button
              type="button"
              className="inline-flex h-10 items-center gap-2 rounded-md bg-ink px-4 text-sm font-semibold text-paper hover:bg-ink/90"
            >
              <CircleDollarSign className="size-4" aria-hidden="true" />
              Fund project
            </button>
          </div>

          <ProjectList />
        </section>
      </section>
    </main>
  );
}
