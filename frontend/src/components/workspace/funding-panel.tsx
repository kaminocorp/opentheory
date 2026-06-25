"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Coins, Plus, Wallet, X } from "lucide-react";
import { useState } from "react";

import {
  Action,
  ActionGhost,
  Bay,
  Icon,
  Input,
  MetricReadout,
  ReadoutLabel,
  Select,
  StatusPill,
  type StateTone,
} from "@/components/console";
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

// Funding status → a state tone. settled = healthy, pending = in motion (awaiting
// settlement), failed = error, refunded = ambient/closed.
const fundingStatusTone: Record<FundingStatus, StateTone> = {
  settled: "ok",
  pending: "run",
  failed: "fail",
  refunded: "faint",
};

// D4 re-skin: console tokens + primitives only. Every hook, the fund mutation, the
// money/date formatters, and the role-gating (canFund) below are unchanged.
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
    // id="funding" is the target of the command rail's Funding zone (D2).
    <Bay id="funding" density="narrative" className="grid gap-3">
      <header className="flex items-center justify-between">
        <span className="flex items-center gap-2 text-text-mute">
          <Icon icon={Wallet} size={16} />
          <ReadoutLabel>Budget</ReadoutLabel>
        </span>
        {isInternal ? (
          <ActionGhost onClick={() => setFunding((v) => !v)} className="h-7 px-3 text-[12px]">
            <Icon icon={funding ? X : Coins} size={14} />
            {funding ? "Cancel" : "Fund project"}
          </ActionGhost>
        ) : null}
      </header>

      {/* Budget summary: funded / available / spent. */}
      <dl className="grid grid-cols-3 gap-3">
        <MetricReadout label="Funded" value={budget ? formatMoney(budget.funded, budget.currency) : "—"} />
        <MetricReadout
          label="Available"
          value={budget ? formatMoney(budget.available, budget.currency) : "—"}
        />
        <MetricReadout
          label="Spent"
          title="Compute spend begins when agents execute (0.7.0)"
          valueClassName="text-text-mute"
          value={budget ? formatMoney(budget.spent, budget.currency) : "—"}
        />
      </dl>

      {/* Role separation: funding is a budget action, distinct from contributing or validating. */}
      <p className="text-[11px] leading-5 text-text-mute">
        Funding grants budget only — it confers no authorship or validation. Compute spend begins when
        agents execute.
      </p>

      {funding && isInternal ? (
        <form
          className="grid gap-2 rounded-built bg-panel-2 p-3 sm:grid-cols-[1fr_auto_auto_auto]"
          style={{ border: "0.5px solid var(--hairline)" }}
          onSubmit={(event) => {
            event.preventDefault();
            if (canFund && !fundMutation.isPending) fundMutation.mutate();
          }}
        >
          <Input
            mono
            type="number"
            min="0"
            step="0.01"
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            placeholder="Amount"
          />
          <Input
            mono
            value={currency}
            onChange={(event) => setCurrency(event.target.value.toUpperCase().slice(0, 3))}
            placeholder="USD"
            maxLength={3}
            aria-label="Currency (ISO 4217)"
            className="!w-16 uppercase"
          />
          <Select
            value={kind}
            onChange={(event) => setKind(event.target.value as FundingKind)}
            className="capitalize"
          >
            {FUNDING_KINDS.map((k) => (
              <option key={k} value={k}>
                {k.replace("_", " ")}
              </option>
            ))}
          </Select>
          <Action type="submit" disabled={!canFund || fundMutation.isPending} pending={fundMutation.isPending}>
            <Icon icon={Plus} size={16} />
            {fundMutation.isPending ? "Funding…" : "Fund (native)"}
          </Action>
          {fundMutation.isError ? (
            <p className="text-[12px] text-state-fail sm:col-span-4">{(fundMutation.error as Error).message}</p>
          ) : null}
        </form>
      ) : null}

      {/* Funding history. */}
      <div className="pt-3" style={{ borderTop: "0.5px solid var(--hairline)" }}>
        <ReadoutLabel as="p" className="mb-2">
          History
        </ReadoutLabel>
        {historyQuery.isLoading ? (
          <p className="text-[12px] text-text-mute">Loading funding…</p>
        ) : historyQuery.isError ? (
          <p className="text-[12px] text-state-fail">Could not load funding history.</p>
        ) : history.length === 0 ? (
          <p className="text-[12px] text-text-faint">
            No funding yet.{isInternal ? " Fund this project to grant it budget." : ""}
          </p>
        ) : (
          <ul className="grid gap-1.5">
            {history.map((item) => (
              <li key={item.id} className="flex items-center justify-between gap-2 text-[12px]">
                <span className="min-w-0 truncate">
                  <span className="font-mono font-medium tabular-nums text-text">
                    {formatMoney(item.amount, item.currency)}
                  </span>
                  <span className="ml-1.5 font-mono text-text-mute">
                    {SOURCE_LABEL[item.source]} · {item.kind.replace("_", " ")}
                  </span>
                  {item.actor ? <span className="ml-1.5 text-text-mute">{item.actor.display_name}</span> : null}
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  <StatusPill tone={fundingStatusTone[item.status]} label={item.status} />
                  <span className="font-mono text-text-faint">{formatDate(item.created_at)}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Bay>
  );
}
