"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Coins, Plus, Wallet, X } from "lucide-react";
import { useState } from "react";

import { createFunding, getProjectBudget, listFunding } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useActingIdentity } from "@/lib/use-identity";
import type { FundingKind, FundingSource, FundingStatus } from "@/types/research";

// Native funding kinds offered in the top-up UI (refund/adjustment are corrections, not here).
const FUNDING_KINDS: FundingKind[] = ["top_up", "grant"];

function formatMoney(amount: string, currency: string): string {
  const value = Number(amount);
  if (Number.isNaN(value)) return `${amount} ${currency}`;
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(value);
  } catch {
    return `${value.toFixed(2)} ${currency}`;
  }
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

const SOURCE_LABEL: Record<FundingSource, string> = { native: "Kamino", stripe: "external" };
const STATUS_CLASS: Record<FundingStatus, string> = {
  settled: "bg-signal/10 text-signal",
  pending: "bg-paper text-ink/55",
  failed: "bg-ember/10 text-ember",
  refunded: "bg-paper text-ink/45",
};

export function FundingPanel({ projectId }: { projectId: string }) {
  const { canWrite, isInternal } = useActingIdentity();
  const queryClient = useQueryClient();
  const [funding, setFunding] = useState(false);
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [kind, setKind] = useState<FundingKind>("top_up");

  const budgetQuery = useQuery({
    queryKey: queryKeys.budget(projectId),
    queryFn: () => getProjectBudget(projectId),
  });
  const historyQuery = useQuery({
    queryKey: queryKeys.funding(projectId),
    queryFn: () => listFunding(projectId),
  });

  const fundMutation = useMutation({
    mutationFn: () =>
      createFunding(projectId, {
        amount: amount.trim(),
        currency: currency.trim() || "USD",
        kind,
        source: "native",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.budget(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.funding(projectId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.overview(projectId) });
      setAmount("");
      setFunding(false);
    },
  });

  const budget = budgetQuery.data;
  const history = historyQuery.data ?? [];
  // Native funding requires the internal role and a positive amount.
  const canFund = canWrite && isInternal && Number(amount) > 0;

  return (
    <section className="grid gap-3 rounded-lg border border-line bg-white/75 p-4 shadow-panel">
      <header className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.1em] text-ink/70">
          <Wallet className="size-4 text-signal" aria-hidden="true" />
          Budget
        </h2>
        {isInternal ? (
          <button
            type="button"
            onClick={() => setFunding((v) => !v)}
            className="inline-flex items-center gap-1 rounded-md border border-line px-2 py-1 text-xs font-medium text-ink/65 hover:text-ink"
          >
            {funding ? <X className="size-3.5" aria-hidden="true" /> : <Coins className="size-3.5" aria-hidden="true" />}
            {funding ? "Cancel" : "Fund project"}
          </button>
        ) : null}
      </header>

      {/* Budget summary: funded / available / spent. */}
      <dl className="grid grid-cols-3 gap-3">
        <div className="rounded-md border border-line bg-paper/60 px-3 py-2">
          <dt className="text-[11px] font-semibold uppercase tracking-[0.1em] text-ink/50">Funded</dt>
          <dd className="mt-0.5 text-lg font-semibold tabular-nums">
            {budget ? formatMoney(budget.funded, budget.currency) : "—"}
          </dd>
        </div>
        <div className="rounded-md border border-line bg-paper/60 px-3 py-2">
          <dt className="text-[11px] font-semibold uppercase tracking-[0.1em] text-ink/50">Available</dt>
          <dd className="mt-0.5 text-lg font-semibold tabular-nums">
            {budget ? formatMoney(budget.available, budget.currency) : "—"}
          </dd>
        </div>
        <div className="rounded-md border border-line bg-paper/60 px-3 py-2">
          <dt className="text-[11px] font-semibold uppercase tracking-[0.1em] text-ink/50">Spent</dt>
          <dd className="mt-0.5 text-lg font-semibold tabular-nums text-ink/55" title="Compute spend begins when agents execute (0.7.0)">
            {budget ? formatMoney(budget.spent, budget.currency) : "—"}
          </dd>
        </div>
      </dl>

      {/* Role separation: funding is a budget action, distinct from contributing or validating. */}
      <p className="text-[11px] leading-5 text-ink/50">
        Funding grants budget only — it confers no authorship or validation. Compute spend begins
        when agents execute.
      </p>

      {funding && isInternal ? (
        <form
          className="grid gap-2 rounded-md border border-line bg-paper/60 p-3 sm:grid-cols-[1fr_auto_auto_auto]"
          onSubmit={(event) => {
            event.preventDefault();
            if (canFund && !fundMutation.isPending) fundMutation.mutate();
          }}
        >
          <input
            type="number"
            min="0"
            step="0.01"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            placeholder="Amount"
            className="h-9 rounded-md border border-line bg-white/80 px-2 text-sm outline-none focus:border-signal"
          />
          <input
            value={currency}
            onChange={(event) => setCurrency(event.target.value.toUpperCase().slice(0, 3))}
            placeholder="USD"
            maxLength={3}
            aria-label="Currency (ISO 4217)"
            className="h-9 w-16 rounded-md border border-line bg-white/80 px-2 text-sm uppercase outline-none focus:border-signal"
          />
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value as FundingKind)}
            className="h-9 rounded-md border border-line bg-white/80 px-2 text-sm capitalize outline-none focus:border-signal"
          >
            {FUNDING_KINDS.map((k) => (
              <option key={k} value={k}>
                {k.replace("_", " ")}
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={!canFund || fundMutation.isPending}
            className="inline-flex h-9 items-center justify-center gap-1 rounded-md bg-ink px-3 text-sm font-semibold text-paper disabled:opacity-50"
          >
            <Plus className="size-4" aria-hidden="true" />
            {fundMutation.isPending ? "Funding…" : "Fund (native)"}
          </button>
          {fundMutation.isError ? (
            <p className="text-xs text-ember sm:col-span-4">{(fundMutation.error as Error).message}</p>
          ) : null}
        </form>
      ) : null}

      {/* Funding history. */}
      <div className="border-t border-line pt-3">
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.1em] text-ink/50">History</p>
        {historyQuery.isLoading ? (
          <p className="text-xs text-ink/50">Loading funding…</p>
        ) : historyQuery.isError ? (
          <p className="text-xs text-ember">Could not load funding history.</p>
        ) : history.length === 0 ? (
          <p className="text-xs text-ink/45">
            No funding yet.{isInternal ? " Fund this project to grant it budget." : ""}
          </p>
        ) : (
          <ul className="grid gap-1.5">
            {history.map((item) => (
              <li key={item.id} className="flex items-center justify-between gap-2 text-xs">
                <span className="min-w-0 truncate">
                  <span className="font-semibold tabular-nums">
                    {formatMoney(item.amount, item.currency)}
                  </span>
                  <span className="ml-1.5 text-ink/45">
                    {SOURCE_LABEL[item.source]} · {item.kind.replace("_", " ")}
                  </span>
                  {item.actor ? <span className="ml-1.5 text-ink/40">{item.actor.display_name}</span> : null}
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  <span className={`rounded px-1.5 py-0.5 font-semibold ${STATUS_CLASS[item.status]}`}>
                    {item.status}
                  </span>
                  <span className="text-ink/40">{formatDate(item.created_at)}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
