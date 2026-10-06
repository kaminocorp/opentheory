"use client";

import { useQuery } from "@tanstack/react-query";
import { Gauge } from "lucide-react";

import { Bay, BayHeader, Icon, MetricReadout, ReadoutLabel, StatusPill } from "@/components/console";
import { getProjectOps } from "@/lib/api";
import {
  budgetStateLabel,
  budgetStateTone,
  dailyCapLine,
  dailyCapTone,
  formatOpsMoney,
  holdIdLabel,
  holdStatusLabel,
  lastTurnLine,
  lastTurnTone,
  loopLine,
  opsSpendByAgent,
  spendByAgentLine,
  turnActorLabel,
  turnKindLabel,
  unknownProcessLine,
} from "@/lib/ops";
import { queryKeys } from "@/lib/query-keys";
import type { OpsActorSpendRead, OpsHoldRead, OpsTurnRead, ProjectOpsRead } from "@/types/ops";

import { PanelError, PanelLoading } from "./panel-state";

type OpsDashboardBayProps = {
  projectId: string;
};

function formatWhen(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toISOString().replace("T", " ").replace(/\.\d+Z$/, " UTC");
}

function HoldRow({ hold }: { hold: OpsHoldRead }) {
  return (
    <li className="grid gap-0.5 py-2" style={{ borderTop: "1px solid var(--hairline)" }}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <StatusPill
          tone={hold.status === "open" ? "warn" : "mute"}
          label={holdStatusLabel(hold.status, hold.stale)}
        />
        <span className="font-mono text-[12px] text-text-soft">{hold.tokens.toLocaleString()} tok</span>
        <span className="font-mono text-[11px] text-text-faint">{holdIdLabel(hold)}</span>
      </div>
      {hold.note ? <p className="text-[12px] text-text-faint">{hold.note}</p> : null}
    </li>
  );
}

function SpendByAgentRow({ row }: { row: OpsActorSpendRead }) {
  return (
    <li className="grid gap-0.5 py-2" style={{ borderTop: "1px solid var(--hairline)" }}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-[12px] font-medium text-text-soft">
          {spendByAgentLine(row.tokens_used, row.actor_display_name)}
        </span>
        <span className="font-mono text-[11px] text-text-faint">
          {row.turn_count} turn{row.turn_count === 1 ? "" : "s"}
        </span>
      </div>
    </li>
  );
}

function TurnRow({ turn }: { turn: OpsTurnRead }) {
  return (
    <li className="grid gap-0.5 py-2" style={{ borderTop: "1px solid var(--hairline)" }}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-[12px] font-medium text-text-mute">{turnKindLabel(turn.kind)}</span>
        <span className="font-mono text-[12px] text-text-soft">
          {turn.tokens_used.toLocaleString()} tok
        </span>
        <span className="text-[12px] text-text-faint">{formatWhen(turn.created_at)}</span>
        <span className="text-[12px] text-text-faint">{turnActorLabel(turn)}</span>
      </div>
      {turn.notes ? (
        <p className="truncate font-mono text-[11px] text-text-faint">{turn.notes}</p>
      ) : null}
    </li>
  );
}

function OpsBody({ data }: { data: ProjectOpsRead }) {
  const {
    budget,
    daily_cap: cap,
    holds,
    recent_turns: turns,
    last_turn: lastTurn,
    refusals,
    enablement,
  } = data;
  const spendByAgent = opsSpendByAgent(data);
  const currency = budget.snapshot.currency;

  return (
    <div className="grid gap-4 px-4 pb-4 pt-3">
      <p className="text-[12px] leading-5 text-text-mute">
        Read-only. Numbers are Σ append-only <span className="font-mono">ComputeDebit</span>{" "}
        rows whose notes start with{" "}
        <span className="font-mono">{data.notes_prefix}</span>, plus settled funding.
        Refused starts mint nothing. As of {formatWhen(data.as_of)}.
      </p>

      <div className="grid gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <ReadoutLabel as="h3">Project pot</ReadoutLabel>
          <StatusPill tone={budgetStateTone(budget.state)} label={budgetStateLabel(budget.state)} />
        </div>
        <p className="text-[12px] leading-5 text-text-faint">{budget.note}</p>
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetricReadout label="Funded" value={formatOpsMoney(budget.snapshot.funded, currency)} />
          <MetricReadout
            label="Spent"
            title="Σ ComputeDebit amounts"
            value={formatOpsMoney(budget.snapshot.spent, currency)}
          />
          <MetricReadout
            label="Reserved"
            title="In-flight agent-pass holds"
            value={formatOpsMoney(budget.snapshot.reserved ?? "0", currency)}
          />
          <MetricReadout
            label="Available"
            value={formatOpsMoney(budget.snapshot.available, currency)}
          />
        </dl>
      </div>

      <div className="grid gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <ReadoutLabel as="h3">Harness daily cap</ReadoutLabel>
          <StatusPill
            tone={dailyCapTone(cap)}
            label={cap.exhausted ? "Cap exhausted" : cap.exhausted === null ? "Cap unknown" : "Room"}
          />
        </div>
        <p className="font-mono text-[13px] text-text-soft">{dailyCapLine(cap)}</p>
        <p className="text-[12px] leading-5 text-text-faint">{cap.note}</p>
        <p className="text-[12px] text-text-faint">UTC day {cap.utc_day}</p>
      </div>

      <div className="grid gap-2">
        <ReadoutLabel as="h3">Last turn</ReadoutLabel>
        {lastTurn ? (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill
                tone={lastTurnTone(lastTurn)}
                label={lastTurn.overshoot && lastTurn.overshoot > 0 ? "Overshoot" : "Recorded"}
              />
              <span className="font-mono text-[13px] text-text-soft">{lastTurnLine(lastTurn)}</span>
            </div>
            <p className="text-[12px] leading-5 text-text-faint">{lastTurn.note}</p>
          </>
        ) : (
          <p className="text-[13px] text-text-faint">No billed harness spend yet.</p>
        )}
      </div>

      <div className="grid gap-2">
        <ReadoutLabel as="h3">Holds</ReadoutLabel>
        {holds.length === 0 ? (
          <p className="text-[13px] text-text-faint">No remaining-room holds on today&apos;s ledger.</p>
        ) : (
          <ul>
            {holds.map((hold, index) => (
              <HoldRow key={hold.hold_id ?? `legacy-${index}`} hold={hold} />
            ))}
          </ul>
        )}
      </div>

      <div className="grid gap-2">
        <ReadoutLabel as="h3">Spend by agent</ReadoutLabel>
        {spendByAgent.length === 0 ? (
          <p className="text-[13px] text-text-faint">
            No billed harness spend attributed yet. Pre-identity rows stay unknown.
          </p>
        ) : (
          <ul>
            {spendByAgent.map((row, index) => (
              <SpendByAgentRow key={row.actor_id ?? `unknown-${index}`} row={row} />
            ))}
          </ul>
        )}
      </div>

      <div className="grid gap-2">
        <ReadoutLabel as="h3">Recent harness rows</ReadoutLabel>
        {turns.length === 0 ? (
          <p className="text-[13px] text-text-faint">No harness_session_turn rows yet.</p>
        ) : (
          <ul>
            {turns.map((turn) => (
              <TurnRow key={turn.id} turn={turn} />
            ))}
          </ul>
        )}
      </div>

      <div className="grid gap-2">
        <ReadoutLabel as="h3">Refusals</ReadoutLabel>
        <p className="text-[13px] leading-5 text-text-soft">{refusals.note}</p>
      </div>

      <div className="grid gap-2">
        <ReadoutLabel as="h3">Enablement</ReadoutLabel>
        <div className="flex flex-wrap gap-2">
          <StatusPill
            tone={enablement.loop.enabled ? "warn" : "mute"}
            label={loopLine(enablement)}
          />
          <StatusPill tone="faint" label={unknownProcessLine("Gateway", enablement.gateway.enabled)} />
          <StatusPill
            tone="faint"
            label={unknownProcessLine("MCP child", enablement.mcp_child.enabled)}
          />
        </div>
        <p className="text-[12px] leading-5 text-text-faint">{enablement.gateway.note}</p>
        <p className="text-[12px] leading-5 text-text-faint">{enablement.mcp_child.note}</p>
      </div>
    </div>
  );
}

/**
 * Quiet operator snapshot on Overview. Read-only — never funds, never
 * commissions a pass, never writes the ledger.
 */
export function OpsDashboardBay({ projectId }: OpsDashboardBayProps) {
  const opsQuery = useQuery({
    queryKey: queryKeys.ops(projectId),
    queryFn: () => getProjectOps(projectId),
  });

  return (
    <Bay density="none" className="flex flex-col">
      <BayHeader
        label={
          <span className="inline-flex items-center gap-1.5">
            <Icon icon={Gauge} size={14} />
            Perpetual ops
          </span>
        }
        divider
      />
      {opsQuery.isLoading ? (
        <div className="px-4 py-4">
          <PanelLoading label="Loading ops" />
        </div>
      ) : opsQuery.isError || !opsQuery.data ? (
        <div className="px-4 py-4">
          <PanelError label="Could not load ops" />
        </div>
      ) : (
        <OpsBody data={opsQuery.data} />
      )}
    </Bay>
  );
}
